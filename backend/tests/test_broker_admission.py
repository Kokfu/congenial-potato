import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import ExternalReadObservation, ReadEffectAttempt
from test_local_read_experiment import local_server
from test_read_broker_result import issued,fetch


def test_empty_replacement_journal_cannot_repeat_unknown_fetch(authenticated,tmp_path):
    invocation_id,_,key,envelope=issued(authenticated)
    first,second=tmp_path/'original',tmp_path/'replacement'
    first.mkdir(mode=0o700); second.mkdir(mode=0o700)
    def crash():
        raise RuntimeError('lost reply after fetch')
    from workforce.read_broker_contract import BrokerOutcomeUnknown
    with local_server() as (port,seen):
        with pytest.raises(RuntimeError):
            fetch(envelope,key,first,port,after_fetch=crash)
        try:
            fetch(envelope,key,second,port)
        except BrokerOutcomeUnknown:
            pass
        assert seen==['/source'], 'an unknown fetch repeated through a fresh journal'
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).status=='unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_concurrent_admission_commits_once_before_any_permit(authenticated):
    from concurrent.futures import ThreadPoolExecutor
    from workforce.models import AuditEvent
    from workforce.read_broker_contract import BrokerOutcomeUnknown
    from workforce.read_broker_mediator import authorize_broker_fetch
    invocation_id,_,key,envelope=issued(authenticated)
    def admit(_):
        try:
            authorize_broker_fetch(envelope,key=key,experiment_enabled=True)
            return 'admitted'
        except BrokerOutcomeUnknown:
            return 'unknown'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(admit,range(2)))==['admitted','unknown']
    with session_factory()() as db:
        assert db.get(ReadEffectAttempt,invocation_id).broker_permit_consumed
        audits=db.scalars(select(AuditEvent).where(AuditEvent.action=='read.broker.admit')).all()
        assert len(audits)==1 and audits[0].outcome=='unknown'
        assert db.scalar(select(ExternalReadObservation)) is None


def test_valid_reply_without_admission_cannot_create_provenance(authenticated):
    from workforce.local_read_experiment import ReadDenied
    from workforce.read_broker_mediator import accept_broker_reply
    from workforce.read_broker_result import sign_broker_reply
    from test_read_broker_result import result
    invocation_id,_,key,envelope=issued(authenticated)
    signed=sign_broker_reply(result(),envelope,key=key)
    with pytest.raises(ReadDenied,match='admission'):
        accept_broker_reply(envelope,signed,key=key,experiment_enabled=True)
    with session_factory()() as db:
        row=db.get(ReadEffectAttempt,invocation_id)
        assert row.status=='unknown' and not row.broker_permit_consumed
        assert db.scalar(select(ExternalReadObservation)) is None


def test_process_loss_after_admission_cannot_release_another_permit(authenticated,tmp_path):
    import subprocess
    import sys
    from workforce.read_broker_contract import BrokerOutcomeUnknown
    from workforce.read_broker_mediator import authorize_broker_fetch
    invocation_id,_,key,envelope=issued(authenticated)
    key_path,ticket_path=tmp_path/'key',tmp_path/'ticket'
    key_path.write_bytes(key); key_path.chmod(0o600); ticket_path.write_text(envelope)
    program='''
import os,sys
from pathlib import Path
from workforce.read_broker_mediator import authorize_broker_fetch
authorize_broker_fetch(Path(sys.argv[2]).read_text(),key=Path(sys.argv[1]).read_bytes(),experiment_enabled=True)
os._exit(73)
'''
    lost=subprocess.run([sys.executable,'-c',program,str(key_path),str(ticket_path)],
                        capture_output=True,text=True,timeout=15)
    assert lost.returncode==73,lost.stderr
    with pytest.raises(BrokerOutcomeUnknown):
        authorize_broker_fetch(envelope,key=key,experiment_enabled=True)
    journal=tmp_path/'new-broker'; journal.mkdir(mode=0o700)
    with local_server() as (port,seen):
        with pytest.raises(BrokerOutcomeUnknown): fetch(envelope,key,journal,port)
        assert seen==[]
    with session_factory()() as db:
        row=db.get(ReadEffectAttempt,invocation_id)
        assert row.status=='unknown' and row.broker_permit_consumed
        assert db.scalar(select(ExternalReadObservation)) is None


@pytest.mark.parametrize('kind',['issued','prepared','local'])
def test_actual_migration_conservatively_fences_existing_issued_attempts(authenticated,tmp_path,kind):
    from pathlib import Path
    import secrets
    import subprocess
    import sys
    from workforce.read_broker_contract import BrokerOutcomeUnknown
    from workforce.read_broker_mediator import authorize_broker_fetch
    from test_read_broker_issuer import begin,issue
    from test_read_effect_experiment import approved_read,run
    key=secrets.token_bytes(32)
    if kind=='issued':
        invocation_id,_,key,envelope=issued(authenticated)
    else:
        invocation_id,_,_=approved_read(authenticated)
        if kind=='prepared':
            capability,prepared=begin(invocation_id)
        else:
            def crash(): raise RuntimeError('lost local reply')
            with local_server() as (port,seen):
                with pytest.raises(RuntimeError): run(invocation_id,port,after_fetch=crash)
                assert seen==['/source']
    backend=Path(__file__).resolve().parents[1]
    # Exercise the real old schema and migration against the disposable test DB.
    # All application/fixture sessions are closed during this sequential round trip.
    for arguments in [('downgrade','e9a4c13f6d82'),('upgrade','head')]:
        result=subprocess.run([sys.executable,'-m','alembic','-c','alembic.ini',*arguments],
            cwd=backend,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
    with session_factory()() as db:
        row=db.get(ReadEffectAttempt,invocation_id)
        assert row.status=='unknown' and row.broker_permit_consumed==(kind=='issued')
    if kind=='issued':
        with pytest.raises(BrokerOutcomeUnknown):
            authorize_broker_fetch(envelope,key=key,experiment_enabled=True)
    elif kind=='prepared':
        envelope=issue(invocation_id,capability,prepared,key)
        authorize_broker_fetch(envelope,key=key,experiment_enabled=True)
        with pytest.raises(BrokerOutcomeUnknown):
            authorize_broker_fetch(envelope,key=key,experiment_enabled=True)
    else:
        with pytest.raises(BrokerOutcomeUnknown): begin(invocation_id)
