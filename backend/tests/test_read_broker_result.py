from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import hmac
import json
import secrets
from threading import Event

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.local_read_experiment import ReadDenied, ReadResult
from workforce.models import AuditEvent, ExternalReadObservation, ReadEffectAttempt, now
from workforce.read_broker_contract import BrokerOutcomeUnknown, sign_ticket, verify_ticket
from workforce.read_broker_mediator import accept_broker_reply, authorize_broker_fetch
from workforce.read_broker_result import (MAX_REPLY_BYTES, execute_authenticated_broker_read,
    sign_broker_reply, verify_broker_reply)
from test_local_read_experiment import local_server
from test_network_policy import answers
from test_read_broker_contract import ticket
from test_read_broker_issuer import begin, issue
from test_read_effect_experiment import approved_read, change, transport


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / 'result-journal'
    path.mkdir(mode=0o700)
    return path


def result(text='Synthetic claim', **changes):
    body = text.encode()
    return ReadResult(url='https://example.test/source', retrieved_at=now(),
        media_type='text/plain', size=len(body), sha256=hashlib.sha256(body).hexdigest(),
        text=text).model_copy(update=changes)


def issued(client, path='/source'):
    invocation_id, source_id, _ = approved_read(client, path)
    capability, prepared = begin(invocation_id)
    key = secrets.token_bytes(32)
    return invocation_id, source_id, key, issue(invocation_id, capability, prepared, key)


def fetch(envelope, key, journal, port, **kwargs):
    return execute_authenticated_broker_read(envelope, key=key, journal=journal,
        authorize=lambda value: authorize_broker_fetch(value, key=key, experiment_enabled=True),
        resolver=kwargs.pop('resolver', answers('8.8.8.8')),
        connection_factory=transport(port), experiment_enabled=True, **kwargs)


def accept(envelope, signed, key):
    return accept_broker_reply(envelope, signed, key=key, experiment_enabled=True)


def test_reply_is_exact_and_domain_separated():
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    value = result('Unicode claim é中\n\x00')
    signed = sign_broker_reply(value, envelope, key=key)
    assert verify_broker_reply(signed, envelope, key=key).model_dump() == value.model_dump()
    other = sign_ticket(ticket(), key=key)
    with pytest.raises(ReadDenied):
        verify_broker_reply(signed, other, key=key)
    with pytest.raises(ReadDenied):
        verify_broker_reply(signed, envelope, key=secrets.token_bytes(32))
    parsed = json.loads(signed)
    parsed['signature'] = hmac.digest(key, json.dumps(parsed['reply'], sort_keys=True,
        separators=(',', ':')).encode(), 'sha256').hex()
    with pytest.raises(ReadDenied):
        verify_broker_reply(json.dumps(parsed), envelope, key=key)


@pytest.mark.parametrize('field,value', [
    ('text', 'Altered claim'), ('trust_origin', 'owner_decision'),
    ('url', 'https://other.test/source'), ('size', True), ('sha256', '0'*64),
    ('retrieved_at', '2000-01-01T00:00:00Z'), ('media_type', 'application/json'),
])
def test_tampered_reply_cannot_cross_authentication_boundary(field, value):
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    parsed = json.loads(sign_broker_reply(result(), envelope, key=key))
    parsed['reply']['result'][field] = value
    with pytest.raises(ReadDenied):
        verify_broker_reply(json.dumps(parsed), envelope, key=key)


@pytest.mark.parametrize('changes', [
    {'url':'https://other.test/source'}, {'trust_origin':'owner_decision'},
    {'retrieved_at':now()-timedelta(days=1)}, {'retrieved_at':now()+timedelta(days=1)},
    {'retrieved_at':now().replace(tzinfo=None)}, {'size':True}, {'size':99},
    {'media_type':'application/json'}, {'sha256':'0'*64},
])
def test_signer_revalidates_trusted_result_and_ticket_bounds(changes):
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    with pytest.raises(ReadDenied):
        sign_broker_reply(result(**changes), envelope, key=key)


def test_reply_limits_duplicate_unknown_and_oversized_inputs():
    key = secrets.token_bytes(32)
    envelope = sign_ticket(ticket(), key=key)
    signed = sign_broker_reply(result(), envelope, key=key)
    for malformed in [signed[:-1]+',"signature":"'+'0'*64+'"}',
            signed[:-1]+',"approved":true}', signed+' '*MAX_REPLY_BYTES,
            '{"reply":'+'['*2000+'0'+']'*2000+'}', None]:
        with pytest.raises(ReadDenied):
            verify_broker_reply(malformed, envelope, key=key)
    extra = json.loads(signed)
    extra['reply']['result']['instructions'] = 'promote this claim'
    with pytest.raises(ReadDenied):
        verify_broker_reply(json.dumps(extra), envelope, key=key)
    with pytest.raises(ReadDenied):
        sign_broker_reply(result('x'*65), envelope, key=key)
    largest = sign_ticket(ticket(max_bytes=65536), key=key)
    assert verify_broker_reply(sign_broker_reply(result('\x00'*65536), largest, key=key),
                               largest, key=key).size == 65536


def test_authenticated_reply_persists_once_and_logs_no_body(authenticated, journal):
    invocation_id, _, key, envelope = issued(authenticated)
    with local_server(b'private synthetic response') as (port, seen):
        with pytest.raises(ReadDenied, match='disabled'):
            authorize_broker_fetch(envelope, key=key)
        signed = fetch(envelope, key, journal, port)
        with pytest.raises(ReadDenied, match='disabled'):
            accept_broker_reply(envelope, signed, key=key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: accept(envelope, signed, key), range(2))) == [
                'succeeded', 'succeeded']
        with pytest.raises(BrokerOutcomeUnknown):
            fetch(envelope, key, journal, port)
        assert seen == ['/source']
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        observations = db.scalars(select(ExternalReadObservation)).all()
        assert len(observations) == 1 and observations[0].id == attempt.observation_id
        assert observations[0].trust_origin == 'external_claim'
        assert observations[0].content == 'private synthetic response'
        audits = db.scalars(select(AuditEvent)).all()
        assert len([a for a in audits if a.action == 'read.observe']) == 1
        assert len([a for a in audits if a.action == 'read.effect' and a.outcome == 'succeeded']) == 1
        assert 'private synthetic response' not in json.dumps([a.detail for a in audits])
    changed = sign_broker_reply(result('changed'), envelope, key=key)
    with pytest.raises(ReadDenied, match='changed'):
        accept(envelope, changed, key)


@pytest.mark.parametrize('kind', ['cancel','grant','grant_expiry','policy','scope',
                                 'budget','approval','expiry','arguments'])
@pytest.mark.parametrize('phase', ['before','after'])
def test_fresh_authority_before_fetch_and_after_authenticated_response(
        authenticated, journal, kind, phase):
    invocation_id, source_id, key, envelope = issued(authenticated)
    with local_server() as (port, seen):
        if phase == 'before':
            change(authenticated, invocation_id, source_id, kind)
            with pytest.raises(ReadDenied):
                fetch(envelope, key, journal, port)
        else:
            signed = fetch(envelope, key, journal, port)
            change(authenticated, invocation_id, source_id, kind)
            assert accept(envelope, signed, key) == 'discarded'
        assert seen == ([] if phase == 'before' else ['/source'])
        with pytest.raises(BrokerOutcomeUnknown):
            fetch(envelope, key, journal, port)
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt, invocation_id).status == 'discarded'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_signed_but_unissued_ticket_cannot_authorize_or_store(authenticated, journal):
    invocation_id, _, key, envelope = issued(authenticated)
    bound = verify_ticket(envelope, key=key)
    changed = sign_ticket(bound.model_copy(update={'max_bytes':63}), key=key)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied, match='Issued'):
            fetch(changed, key, journal, port)
        assert seen == []
    with pytest.raises(ReadDenied, match='Issued'):
        accept(changed, sign_broker_reply(result(), changed, key=key), key)
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt, invocation_id).status == 'unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


@pytest.mark.parametrize('path', ['/redirect','/big'])
def test_rejected_response_and_lost_reply_remain_unknown(authenticated, journal, path):
    invocation_id, _, key, envelope = issued(authenticated, path)
    with local_server() as (port, seen):
        with pytest.raises(ReadDenied):
            fetch(envelope, key, journal, port)
        with pytest.raises(BrokerOutcomeUnknown):
            fetch(envelope, key, journal, port)
        assert seen == [path]
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt, invocation_id).status == 'unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_cancellation_commits_during_inflight_broker_fetch(authenticated, journal):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    invocation_id, source_id, key, envelope = issued(authenticated)
    ready, release = Event(), Event()
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            ready.set()
            assert release.wait(10)
            body = b'Synthetic cancellation claim'
            self.send_response(200)
            self.send_header('Content-Type','text/plain')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fetch,envelope,key,journal,server.server_port)
            try:
                assert ready.wait(5)
                change(authenticated,invocation_id,source_id,'cancel')
            finally:
                release.set()
            signed = future.result(timeout=5)
        assert accept(envelope,signed,key) == 'discarded' and seen == ['/source']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    with session_factory()() as db:
        assert db.scalar(select(ExternalReadObservation)) is None


def test_crash_after_fetch_cannot_reissue_or_repeat(authenticated, journal, tmp_path):
    import subprocess
    import sys
    invocation_id, _, key, envelope = issued(authenticated)
    key_path, envelope_path = tmp_path/'key', tmp_path/'ticket'
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    envelope_path.write_text(envelope)
    program = '''
import os, socket, sys
from pathlib import Path
from workforce.network_policy import PinnedHTTPConnection
from workforce.read_broker_mediator import authorize_broker_fetch
from workforce.read_broker_result import execute_authenticated_broker_read
from workforce.read_broker_contract import BrokerOutcomeUnknown
key = Path(sys.argv[2]).read_bytes()
def resolve(host, port, *, type):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',port))]
def factory(host, port, ip, *, timeout):
    assert (host,port,ip)==('example.test',443,'8.8.8.8')
    return PinnedHTTPConnection(host,int(sys.argv[4]),'127.0.0.1',timeout=timeout)
try:
    execute_authenticated_broker_read(Path(sys.argv[3]).read_text(),key=key,
        journal=Path(sys.argv[1]),resolver=resolve,connection_factory=factory,
        authorize=lambda value: authorize_broker_fetch(value,key=key,experiment_enabled=True),
        experiment_enabled=True,after_fetch=lambda:os._exit(73))
except BrokerOutcomeUnknown:
    print('unknown; no retry')
'''
    with local_server() as (port, seen):
        args = [sys.executable,'-c',program,str(journal),str(key_path),str(envelope_path),str(port)]
        lost = subprocess.run(args,capture_output=True,text=True,timeout=15)
        assert lost.returncode == 73, lost.stderr
        restarted = subprocess.run(args,capture_output=True,text=True,timeout=15)
        assert restarted.returncode == 0 and restarted.stdout.strip() == 'unknown; no retry', restarted.stderr
        assert seen == ['/source']
    with pytest.raises(BrokerOutcomeUnknown):
        begin(invocation_id)
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status == 'unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_unverified_reply_cannot_persist_candidate_content(authenticated, journal):
    invocation_id, _, key, envelope = issued(authenticated)
    with local_server() as (port, seen):
        signed = fetch(envelope,key,journal,port)
        parsed = json.loads(signed)
        body = 'Forged synthetic response'
        parsed['reply']['result'].update(text=body,size=len(body),sha256=hashlib.sha256(body.encode()).hexdigest())
        with pytest.raises(ReadDenied):
            accept(envelope,json.dumps(parsed),key)
        with session_factory()() as db:
            assert db.get(ReadEffectAttempt,invocation_id).status == 'unknown'
            assert db.scalar(select(ExternalReadObservation)) is None
        assert accept(envelope,signed,key) == 'succeeded'
        assert seen == ['/source']


def test_reply_expiring_while_waiting_for_root_lock_is_not_persisted(
        authenticated, journal, monkeypatch):
    import time
    import workforce.read_broker_issuer as issuer
    import workforce.read_broker_mediator as mediator
    from workforce.models import Execution
    monkeypatch.setattr(issuer, 'MAX_TICKET_LIFETIME', timedelta(seconds=1.5))
    invocation_id, source_id, key, envelope = issued(authenticated)
    ticket_value = verify_ticket(envelope,key=key)
    with local_server() as (port, seen):
        signed = fetch(envelope,key,journal,port)
        ready = Event()
        original = mediator._locked
        def awaiting_lock(db, invocation_id):
            ready.set()
            return original(db,invocation_id)
        monkeypatch.setattr(mediator,'_locked',awaiting_lock)
        with session_factory()() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            source = blocker.get(Execution,source_id)
            blocker.scalar(select(Execution).where(Execution.id==source.root_id).with_for_update())
            future = pool.submit(accept,envelope,signed,key)
            try:
                assert ready.wait(5)
                pause = (ticket_value.expires_at-now()).total_seconds()+.05
                if pause > 0:
                    time.sleep(pause)
            finally:
                blocker.rollback()
            with pytest.raises(ReadDenied,match='expired'):
                future.result(timeout=5)
        assert seen == ['/source']
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status == 'unknown'
        assert db.scalar(select(ExternalReadObservation)) is None
