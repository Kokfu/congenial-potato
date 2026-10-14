from contextlib import contextmanager
from datetime import timedelta
import json
from pathlib import Path
import secrets
import socket
import struct
import time
from threading import Thread

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.local_read_experiment import ReadDenied
from workforce.models import ExternalReadObservation, ReadEffectAttempt, now
from workforce.read_broker_contract import BrokerOutcomeUnknown, sign_ticket
from workforce.read_broker_mediator import accept_broker_reply, authorize_broker_fetch
import workforce.read_broker_rpc as rpc
from test_local_read_experiment import local_server
from test_network_policy import answers
from test_read_broker_contract import ticket
from test_read_broker_result import issued
from test_read_effect_experiment import change, transport


@pytest.fixture
def journal(tmp_path):
    path=tmp_path/'rpc-journal'
    path.mkdir(mode=0o700)
    return path


@contextmanager
def server(key,journal,port,**kwargs):
    instance=rpc.make_broker_server(('127.0.0.1',0),key=key,journal=journal,
        resolver=kwargs.pop('resolver',answers('8.8.8.8')),connection_factory=transport(port),
        experiment_enabled=True,**kwargs)
    thread=Thread(target=instance.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start()
    try:
        yield instance.server_address
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=12)
        assert not thread.is_alive()


def exchange(address,envelope,key,authorize=lambda _:None):
    return rpc.broker_exchange(address,envelope,key=key,authorize=authorize,experiment_enabled=True)


def test_rpc_fences_before_fresh_authority_then_returns_authenticated_reply(journal):
    from workforce.read_broker_result import verify_broker_reply
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    with local_server() as (port,seen), server(key,journal,port) as address:
        def authorize(value):
            assert value==envelope and seen==[]
            paths=list(journal.iterdir())
            assert len(paths)==1 and len(paths[0].read_bytes())==65
        signed=exchange(address,envelope,key,authorize)
        assert verify_broker_reply(signed,envelope,key=key).text=='A synthetic source claim'
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key)
        assert seen==['/source']


@pytest.mark.parametrize('host', ['8.8.8.8','169.254.169.254','0.0.0.0','224.0.0.1','example.test','::1'])
def test_client_rejects_nonfixture_or_hostname_channels(host):
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    with pytest.raises(ValueError):
        exchange((host,1234),envelope,key)


def test_defaults_wrong_key_and_invalid_ticket_never_dispatch(journal):
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    with local_server() as (port,seen):
        with pytest.raises(ReadDenied,match='disabled'):
            rpc.make_broker_server(('127.0.0.1',0),key=key,journal=journal,
                resolver=answers('8.8.8.8'),connection_factory=transport(port))
        with server(key,journal,port) as address:
            with pytest.raises(ReadDenied,match='disabled'):
                rpc.broker_exchange(address,envelope,key=key,authorize=lambda _:None)
            with pytest.raises(ReadDenied):
                exchange(address,envelope,secrets.token_bytes(32))
            parsed=json.loads(envelope)
            parsed['ticket']['url']='https://other.test/source'
            with pytest.raises(ReadDenied):
                exchange(address,json.dumps(parsed),key)
        assert seen==[] and list(journal.iterdir())==[]


@pytest.mark.parametrize('kind', ['nonce','ticket','signature','expired','future','long','unknown'])
def test_invalid_permit_after_challenge_consumes_without_fetch(journal,kind):
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    with local_server() as (port,seen), server(key,journal,port) as address:
        with socket.create_connection(address,timeout=2) as connection:
            deadline=time.monotonic()+2
            rpc._write_frame(connection,envelope,16384,deadline)
            challenge=rpc._verify(rpc._read_frame(connection,4096,deadline),rpc._Challenge,
                                  key,rpc._CHALLENGE_DOMAIN)
            at=now()
            data=dict(nonce=challenge.nonce,ticket_hash=challenge.ticket_hash,
                      checked_at=at,expires_at=at+timedelta(seconds=.5))
            if kind=='nonce': data['nonce']='0'*64
            if kind=='ticket': data['ticket_hash']='0'*64
            if kind=='expired': data.update(checked_at=at-timedelta(seconds=2),expires_at=at-timedelta(seconds=1.5))
            if kind=='future': data.update(checked_at=at+timedelta(seconds=.2),expires_at=at+timedelta(seconds=.5))
            permit=rpc._Permit(**data)
            signed=json.loads(rpc._sign(permit,key,rpc._PERMIT_DOMAIN))
            if kind=='signature': signed['signature']='0'*64
            if kind=='unknown': signed['message']['headers']={'Authorization':'forbidden'}
            if kind=='long': signed['message']['expires_at']=(at+timedelta(seconds=2)).isoformat()
            rpc._write_frame(connection,json.dumps(signed),4096,deadline)
            assert connection.recv(1)==b''
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key)
        assert seen==[] and len(list(journal.iterdir()))==1


@pytest.mark.parametrize('value', [b'CONNECT example.test:443 HTTP/1.1\r\n\r\n',struct.pack('!I',16385),
                                  struct.pack('!I',1)+b'\xff',struct.pack('!I',2)+b'{}'])
def test_bad_frames_proxy_requests_and_nonutf8_never_reach_origin(journal,value):
    key=secrets.token_bytes(32)
    with local_server() as (port,seen), server(key,journal,port) as address:
        with socket.create_connection(address,timeout=2) as connection:
            connection.sendall(value)
            try:
                assert connection.recv(1)==b''
            except ConnectionResetError:
                pass
        assert seen==[] and list(journal.iterdir())==[]


def test_absolute_rpc_deadline_stops_body_trickling_and_recovers(journal,monkeypatch):
    monkeypatch.setattr(rpc,'RPC_DEADLINE_SECONDS',.2)
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    with local_server() as (port,seen), server(key,journal,port) as address:
        started=time.monotonic()
        with socket.create_connection(address,timeout=1) as connection:
            connection.sendall(struct.pack('!I',100))
            for _ in range(20):
                try:
                    connection.sendall(b' ')
                    time.sleep(.04)
                except (BrokenPipeError,ConnectionResetError):
                    break
            assert connection.recv(1)==b''
        assert time.monotonic()-started < .7
        assert seen==[] and list(journal.iterdir())==[]
        assert exchange(address,envelope,key)
        assert seen==['/source']


@pytest.mark.parametrize('kind', ['cancel','grant','policy','budget'])
def test_rpc_checks_actual_database_before_permit_and_after_reply(authenticated,journal,kind):
    invocation_id,source_id,key,envelope=issued(authenticated)
    def authorize(value):
        change(authenticated,invocation_id,source_id,kind)
        authorize_broker_fetch(value,key=key,experiment_enabled=True)
    with local_server() as (port,seen), server(key,journal,port) as address:
        with pytest.raises(ReadDenied):
            exchange(address,envelope,key,authorize)
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key)
        assert seen==[]
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status=='discarded'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_rpc_success_then_changed_grant_discards_authenticated_body(authenticated,journal):
    invocation_id,source_id,key,envelope=issued(authenticated)
    with local_server() as (port,seen), server(key,journal,port) as address:
        signed=exchange(address,envelope,key,lambda value:authorize_broker_fetch(
            value,key=key,experiment_enabled=True))
        change(authenticated,invocation_id,source_id,'grant')
        assert accept_broker_reply(envelope,signed,key=key,experiment_enabled=True)=='discarded'
        assert seen==['/source']
    with session_factory()() as db:
        assert db.scalar(select(ExternalReadObservation)) is None


def test_lost_authorizer_closes_channel_without_fetch(journal):
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    def lost(_):
        raise RuntimeError('synthetic caller loss')
    with local_server() as (port,seen), server(key,journal,port) as address:
        with pytest.raises(RuntimeError):
            exchange(address,envelope,key,lost)
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key)
        assert seen==[] and len(list(journal.iterdir()))==1


def test_broker_process_restart_after_fetch_never_repeats(authenticated,journal,tmp_path):
    import subprocess
    import sys
    invocation_id,_,key,envelope=issued(authenticated)
    key_path=tmp_path/'key'
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    program='''
import os,socket,sys
from pathlib import Path
from workforce.network_policy import PinnedHTTPConnection
from workforce.read_broker_rpc import make_broker_server
assert 'APP_DATABASE_URL' not in os.environ
assert 'workforce.db' not in sys.modules

def resolve(host,port,*,type):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',port))]
def factory(host,port,ip,*,timeout):
    assert (host,port,ip)==('example.test',443,'8.8.8.8')
    return PinnedHTTPConnection(host,int(sys.argv[3]),'127.0.0.1',timeout=timeout)
server=make_broker_server(('127.0.0.1',0),key=Path(sys.argv[1]).read_bytes(),
    journal=Path(sys.argv[2]),resolver=resolve,connection_factory=factory,
    experiment_enabled=True,after_fetch=(lambda:os._exit(73)) if sys.argv[4]=='crash' else None)
print(server.server_address[1],flush=True)
server.serve_forever()
'''
    with local_server() as (port,seen):
        for phase in ('crash','restart'):
            process=subprocess.Popen([sys.executable,'-u','-c',program,str(key_path),str(journal),str(port),phase],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                env={'PATH':'/usr/bin:/bin','PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')})
            try:
                address=('127.0.0.1',int(process.stdout.readline()))
                with pytest.raises(BrokerOutcomeUnknown):
                    exchange(address,envelope,key,lambda value:authorize_broker_fetch(
                        value,key=key,experiment_enabled=True))
                if phase=='crash':
                    assert process.wait(timeout=5)==73
                assert seen==['/source']
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=5)
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status=='unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


@pytest.mark.parametrize('kind',['signature','ticket','duplicate'])
def test_client_rejects_challenge_before_authorizing(kind):
    key=secrets.token_bytes(32)
    envelope=sign_ticket(ticket(),key=key)
    called=[]
    errors=[]
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen(1)
    listener.settimeout(3)
    def pretend_broker():
        try:
            with listener.accept()[0] as connection:
                deadline=time.monotonic()+2
                assert rpc._read_frame(connection,16384,deadline)==envelope
                challenge=rpc._Challenge(ticket_hash=rpc.ticket_digest(envelope),nonce='a'*64)
                if kind=='ticket':
                    challenge=challenge.model_copy(update={'ticket_hash':'0'*64})
                signed=rpc._sign(challenge,secrets.token_bytes(32) if kind=='signature' else key,
                                 rpc._CHALLENGE_DOMAIN)
                if kind=='duplicate':
                    signed=signed[:-1]+',"signature":"'+'0'*64+'"}'
                rpc._write_frame(connection,signed,4096,deadline)
                assert connection.recv(1)==b''
        except BaseException as exc:
            errors.append(exc)
    thread=Thread(target=pretend_broker,daemon=True)
    thread.start()
    try:
        with pytest.raises(ReadDenied):
            exchange(listener.getsockname(),envelope,key,lambda _:called.append(True))
    finally:
        thread.join(timeout=5)
        listener.close()
    assert not thread.is_alive() and not errors and called==[]


def test_rpc_database_success_persists_one_cited_claim(authenticated,journal):
    invocation_id,_,key,envelope=issued(authenticated)
    with local_server() as (port,seen), server(key,journal,port) as address:
        signed=exchange(address,envelope,key,lambda value:authorize_broker_fetch(
            value,key=key,experiment_enabled=True))
        assert accept_broker_reply(envelope,signed,key=key,experiment_enabled=True)=='succeeded'
        assert seen==['/source']
    with session_factory()() as db:
        row=db.get(ReadEffectAttempt,invocation_id)
        observation=db.get(ExternalReadObservation,row.observation_id)
        assert row.status=='succeeded' and observation.trust_origin=='external_claim'
        assert observation.source_url=='https://example.test/source'


@pytest.mark.parametrize('kind',['rebind','redirect'])
def test_rpc_transport_denial_preserves_unknown_without_provenance(authenticated,journal,kind):
    path='/redirect' if kind=='redirect' else '/source'
    invocation_id,_,key,envelope=issued(authenticated,path)
    resolver=answers('169.254.169.254' if kind=='rebind' else '8.8.8.8')
    with local_server() as (port,seen), server(key,journal,port,resolver=resolver) as address:
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key,lambda value:authorize_broker_fetch(
                value,key=key,experiment_enabled=True))
        with pytest.raises(BrokerOutcomeUnknown):
            exchange(address,envelope,key)
        assert seen==([] if kind=='rebind' else ['/redirect'])
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status=='unknown'
        assert db.scalar(select(ExternalReadObservation)) is None
