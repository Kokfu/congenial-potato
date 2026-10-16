from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Event

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (AuditEvent, ProjectActivity, RunnerAttempt, RunnerResult,
                              ToolInvocation)
from workforce.reviewed_runner_contract import RunnerContractError
from workforce.runner_admission import RunnerAdmissionUnknown, check_runner_authority
from workforce.runner_fixture_job import canonical_receipt, execute_fixture_job
from workforce.runner_result_contract import (pinned_runner_result, sign_runner_result,
                                               verify_runner_result)
from workforce.runner_result_acceptance import accept_runner_result, RunnerResultDenied
from test_runner_admission import approved, admit
from test_runner_approval import mutate, CHANGES

KEY = b'r'*32


def candidate(client):
    details = approved(client)
    admission = admit(details[4])
    receipt = execute_fixture_job(admission.manifest_raw,
        expected_manifest_sha256=admission.manifest_sha256, expected_job_sha256=admission.job_sha256)
    envelope = sign_runner_result(canonical_receipt(receipt), admission, key=KEY, experiment_enabled=True)
    return details, admission, envelope


def accept(admission, envelope, **kwargs):
    return accept_runner_result(admission, envelope, key=KEY, experiment_enabled=True, **kwargs)


def test_one_immutable_metadata_record_and_no_new_execution(authenticated):
    details, admission, envelope = candidate(authenticated)
    result = accept(admission, envelope)
    assert accept(admission, envelope) == result
    assert result.trust_origin == 'synthetic_runner' and result.input_size > 0
    assert result.invocation_id == details[4]
    with session_factory()() as db:
        row = db.get(RunnerResult, details[4])
        attempt = db.get(RunnerAttempt, details[4])
        assert row.payload_hash == attempt.accepted_result_hash == result.payload_hash
        assert row.project_id == details[1] and row.agent_id == details[2]
        assert attempt.status == 'accepted' and attempt.reason is None
        assert db.get(ToolInvocation, details[4]).status == 'runner_result_accepted'
        assert len(db.scalars(select(RunnerResult)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.result')).all()) == 1
        assert len(db.scalars(select(ProjectActivity).where(ProjectActivity.action == 'runner.result')).all()) == 1
        wire = json.dumps(row.payload)
        assert admission.capability.hex() not in wire and KEY.hex() not in wire
        assert 'ignore all grants' not in wire
    from workforce.tool_effects import apply_admitted_tools
    assert apply_admitted_tools() == 0
    with pytest.raises(RunnerAdmissionUnknown):
        admit(details[4])
    with pytest.raises(RunnerAdmissionUnknown):
        check_runner_authority(admission, experiment_enabled=True)
    # Revocation after acceptance does not rewrite a historical record.
    mutate(authenticated, details, 'grant_revision')
    assert accept(admission, envelope) == result


@pytest.mark.parametrize('change', CHANGES+['approval_expired', 'approval_payload'])
def test_delivery_requires_fresh_exact_authority(authenticated, change):
    details, admission, envelope = candidate(authenticated)
    mutate(authenticated, details, change)
    with pytest.raises(RunnerContractError):
        accept(admission, envelope)
    with session_factory()() as db:
        assert db.get(RunnerResult, details[4]) is None
        attempt = db.get(RunnerAttempt, details[4])
        assert attempt.status == 'unknown' and attempt.reason
    with pytest.raises(RunnerAdmissionUnknown):
        admit(details[4])


def test_bad_signature_or_capability_does_not_burn_valid_delivery(authenticated):
    details, admission, envelope = candidate(authenticated)
    document = json.loads(envelope)
    document['signature'] = '0'*64
    for wrong_admission, wrong_envelope in [
        (replace(admission, capability=b'x'*32), envelope), (admission, json.dumps(document))]:
        with pytest.raises(RunnerContractError):
            accept(wrong_admission, wrong_envelope)
    with session_factory()() as db:
        assert db.get(RunnerAttempt, details[4]).reason is None
    assert accept(admission, envelope).invocation_id == details[4]


def test_exact_duplicate_is_historical_after_real_expiry(authenticated, monkeypatch):
    import workforce.runner_admission as module
    monkeypatch.setattr(module, 'MAX_MANIFEST_LIFETIME', timedelta(seconds=1))
    _, admission, envelope = candidate(authenticated)
    result = accept(admission, envelope)
    Event().wait(1.05)
    with pytest.raises(RunnerContractError):
        verify_runner_result(envelope, admission, key=KEY)
    assert pinned_runner_result(envelope, admission, key=KEY)
    assert accept(admission, envelope) == result
    with session_factory()() as db:
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.result')).all()) == 1


def test_expired_first_delivery_cannot_create_record(authenticated, monkeypatch):
    import workforce.runner_admission as module
    monkeypatch.setattr(module, 'MAX_MANIFEST_LIFETIME', timedelta(seconds=1))
    details, admission, envelope = candidate(authenticated)
    Event().wait(1.05)
    with pytest.raises(RunnerResultDenied):
        accept(admission, envelope)
    with session_factory()() as db:
        assert db.get(RunnerResult, details[4]) is None
        assert db.get(RunnerAttempt, details[4]).status == 'unknown'


def test_concurrent_delivery_is_one_result_audit_and_activity(authenticated):
    _, admission, envelope = candidate(authenticated)
    barrier = Barrier(2)
    def deliver():
        barrier.wait(timeout=5)
        return accept(admission, envelope)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: deliver(), range(2)))
    assert results[0] == results[1]
    with session_factory()() as db:
        assert len(db.scalars(select(RunnerResult)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.result')).all()) == 1
        assert len(db.scalars(select(ProjectActivity).where(ProjectActivity.action == 'runner.result')).all()) == 1


def test_loss_after_result_commit_is_replayed_without_launch(authenticated, tmp_path):
    details, admission, envelope = candidate(authenticated)
    private = tmp_path/'delivery.json'
    private.write_text(json.dumps({'admission': asdict(admission) | {'capability': admission.capability.hex()},
                                   'envelope': envelope, 'key': KEY.hex()}))
    private.chmod(0o600)
    program = '''
import json, os, sys
from pathlib import Path
from workforce.runner_admission import RunnerAdmission
from workforce.runner_result_acceptance import accept_runner_result
p=json.loads(Path(sys.argv[1]).read_text())
a=p['admission']; a['capability']=bytes.fromhex(a['capability'])
accept_runner_result(RunnerAdmission(**a),p['envelope'],key=bytes.fromhex(p['key']),
 experiment_enabled=True,after_commit=lambda:os._exit(73))
'''
    lost = subprocess.run([sys.executable, '-c', program, str(private)], capture_output=True, text=True, timeout=15)
    assert lost.returncode == 73, lost.stderr
    replay = program.replace('after_commit=lambda:os._exit(73)', 'after_commit=None')
    replayed = subprocess.run([sys.executable, '-c', replay, str(private)], capture_output=True, text=True, timeout=15)
    assert replayed.returncode == 0, replayed.stderr
    assert accept(admission, envelope).invocation_id == details[4]
    with pytest.raises(RunnerAdmissionUnknown):
        admit(details[4])


def test_corrupt_record_or_changed_signed_delivery_never_overwrites_history(authenticated):
    _, admission, envelope = candidate(authenticated)
    original = accept(admission, envelope)
    altered = json.loads(envelope)
    import hmac
    altered['result']['completed_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    altered['signature'] = hmac.digest(KEY, b'workforce.runner.result.v1\0'+json.dumps(
        altered['result'], sort_keys=True, separators=(',', ':')).encode(), 'sha256').hex()
    with pytest.raises(RunnerResultDenied):
        accept(admission, json.dumps(altered))
    assert accept(admission, envelope) == original
    with session_factory()() as db:
        row = db.get(RunnerResult, admission.invocation_id)
        row.payload = row.payload | {'image_id': 'sha256:'+'b'*64}
        db.commit()
    with pytest.raises(RunnerResultDenied):
        accept(admission, envelope)


@pytest.mark.parametrize('enabled', [False, None, 1, 'true'])
def test_default_disabled_touches_no_database(monkeypatch, enabled):
    import workforce.runner_result_acceptance as module
    def forbidden():
        raise AssertionError('database contacted')
    monkeypatch.setattr(module, 'session_factory', forbidden)
    with pytest.raises(RunnerContractError):
        module.accept_runner_result(None, '', key=KEY, experiment_enabled=enabled)


def migration(*arguments):
    result = subprocess.run([sys.executable, '-m', 'alembic', *arguments],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
    return result


def test_data_bearing_migration_preserves_unknown_fence(authenticated):
    details, admission, _ = candidate(authenticated)
    for arguments in [('downgrade', 'b942d5e8f163'), ('upgrade', 'head')]:
        result = migration(*arguments)
        assert result.returncode == 0, result.stderr
    assert check_runner_authority(admission, experiment_enabled=True)
    with session_factory()() as db:
        assert db.get(RunnerAttempt, details[4]).accepted_result_hash is None


def test_accepted_result_cannot_be_erased_by_downgrade(authenticated):
    _, admission, envelope = candidate(authenticated)
    accepted = accept(admission, envelope)
    result = migration('downgrade', 'b942d5e8f163')
    assert result.returncode != 0 and 'Cannot erase accepted runner results' in result.stderr
    assert accept(admission, envelope) == accepted


def test_authority_expiring_during_real_activity_lock_wait_is_denied(authenticated):
    from sqlalchemy import event, text
    from workforce.db import engine
    from workforce.models import Approval, ProjectActivityCursor
    details, admission, envelope = candidate(authenticated)
    deadline = datetime.now(timezone.utc)+timedelta(seconds=2)
    with session_factory()() as db:
        db.scalar(select(Approval)).expires_at = deadline
        db.commit()
    waiting = Event()
    worker_pid = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if 'FROM project_activity_cursors' in statement and 'FOR UPDATE' in statement:
            worker_pid.append(conn.connection.driver_connection.info.backend_pid)
            waiting.set()
    with session_factory()() as holder:
        holder.scalar(select(ProjectActivityCursor).where(
            ProjectActivityCursor.project_id == details[1]).with_for_update())
        event.listen(engine(), 'before_cursor_execute', observe)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(accept, admission, envelope)
                try:
                    assert waiting.wait(5)
                    for _ in range(100):
                        blocked = holder.scalar(text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {'pid': worker_pid[0]})
                        holder.execute(text('SELECT pg_stat_clear_snapshot()'))
                        if blocked == 'Lock':
                            break
                        Event().wait(.02)
                    assert blocked == 'Lock'
                    Event().wait(max(0, (deadline-datetime.now(timezone.utc)).total_seconds())+.05)
                finally:
                    holder.rollback()
                with pytest.raises(RunnerResultDenied):
                    future.result(timeout=10)
        finally:
            event.remove(engine(), 'before_cursor_execute', observe)
    with session_factory()() as db:
        assert db.get(RunnerResult, details[4]) is None
        assert db.get(RunnerAttempt, details[4]).status == 'unknown'
        assert db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.result')).one().outcome == 'denied'


def test_owner_project_lock_precedes_grant_lock_without_deadlock(authenticated):
    from sqlalchemy import event, text
    from workforce.db import engine
    from workforce.models import Project, RunnerProfileGrant
    details, admission, envelope = candidate(authenticated)
    waiting = Event()
    worker_pid = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if 'FROM projects' in statement and 'FOR KEY SHARE' in statement:
            worker_pid.append(conn.connection.driver_connection.info.backend_pid)
            waiting.set()
    with session_factory()() as holder:
        holder.scalar(select(Project).where(Project.id == details[1]).with_for_update())
        event.listen(engine(), 'before_cursor_execute', observe)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(accept, admission, envelope)
                try:
                    assert waiting.wait(5)
                    for _ in range(100):
                        blocked = holder.scalar(text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"),
                            {'pid': worker_pid[0]})
                        holder.execute(text('SELECT pg_stat_clear_snapshot()'))
                        if blocked == 'Lock':
                            break
                        Event().wait(.02)
                    assert blocked == 'Lock'
                    grant = holder.scalar(select(RunnerProfileGrant).with_for_update(nowait=True))
                    grant.revision += 1
                    holder.commit()
                finally:
                    holder.rollback()
                with pytest.raises(RunnerResultDenied):
                    future.result(timeout=10)
        finally:
            event.remove(engine(), 'before_cursor_execute', observe)
    with session_factory()() as db:
        assert db.get(RunnerResult, details[4]) is None
        assert db.get(RunnerAttempt, details[4]).status == 'unknown'


@pytest.mark.skipif(os.environ.get('WORKFORCE_DOCKER_GATE') != '1', reason='explicit Docker fixture gate')
@pytest.mark.parametrize('stage,change', [(None, None)]+[
    (stage, change) for stage in ['after_job', 'after_receipt']
    for change in ['grant_revision', 'cancelled', 'approval_expired']])
def test_isolated_job_delivery_and_inflight_authority(authenticated, tmp_path, stage, change):
    import secrets
    from runner_isolation_harness import docker
    from runner_admission_harness import run_admitted_job
    image = docker('image', 'inspect', '--format', '{{.Id}}', 'workforce-backend:phase1')
    details = approved(authenticated, image_id=image)
    invocation = details[4]
    journal = tmp_path/'journal'
    journal.mkdir(mode=0o700)
    hooks = {stage: lambda *_: mutate(authenticated, details, change)} if stage else {}
    def run():
        return run_admitted_job(invocation, journal=journal, experiment_enabled=True,
            result_key=secrets.token_bytes(32), accept_result=True, **hooks)
    if stage:
        with pytest.raises(RunnerContractError):
            run()
    else:
        assert run().invocation_id == invocation
    with session_factory()() as db:
        assert (db.get(RunnerResult, invocation) is not None) == (stage is None)
        assert db.get(RunnerAttempt, invocation).status == ('accepted' if stage is None else 'unknown')
    replacement = tmp_path/'replacement'
    replacement.mkdir(mode=0o700)
    with pytest.raises(RunnerAdmissionUnknown):
        run_admitted_job(invocation, journal=replacement, experiment_enabled=True)
    assert list(replacement.iterdir()) == []
    assert docker('ps', '--all', '-q', '--filter',
        'label=workforce.runner.attempt='+invocation.replace('-', '')) == ''
