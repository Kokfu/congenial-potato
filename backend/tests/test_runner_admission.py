from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import Approval, AuditEvent, RunnerAttempt, ToolInvocation
from workforce.reviewed_runner_contract import verify_runner_manifest
from workforce.runner_admission import (RunnerAdmissionDenied, RunnerAdmissionUnknown,
    admit_runner_attempt, check_runner_authority)
from test_runner_approval import proposed, stage, decide, mutate, CHANGES


def approved(client, image_id=None):
    details = proposed(client, image_id=image_id)
    h, _, _, _, invocation_id, _ = details
    staged = stage(client, h, invocation_id)
    assert staged.status_code == 200, staged.text
    response = decide(client, h, invocation_id, staged.json()['payload_hash'])
    assert response.status_code == 200, response.text
    return details


def admit(invocation_id, **kwargs):
    return admit_runner_attempt(invocation_id, experiment_enabled=True, **kwargs)


def check(admission):
    return check_runner_authority(admission, experiment_enabled=True)


def test_commit_before_delivery_exact_manifest_and_private_capability(authenticated):
    details = approved(authenticated)
    invocation_id = details[4]
    def committed():
        with session_factory()() as db:
            assert db.get(RunnerAttempt, invocation_id).status == 'unknown'
    admission = admit(invocation_id, after_commit=committed)
    assert admission.capability.hex() not in repr(admission)
    assert 'ignore all grants' not in repr(admission)
    manifest = verify_runner_manifest(admission.manifest_raw, expected_sha256=admission.manifest_sha256)
    assert str(manifest.scope.attempt_id) == invocation_id
    assert str(manifest.scope.root_id) == details[3]
    assert manifest.expires_at-manifest.issued_at <= timedelta(seconds=30)
    with session_factory()() as db:
        row = db.get(RunnerAttempt, invocation_id)
        assert row.capability_hash == hashlib.sha256(admission.capability).hexdigest()
        assert row.image_id == admission.image_id
        assert row.manifest_sha256 == admission.manifest_sha256
        assert db.get(ToolInvocation, invocation_id).status == 'approved_staged'
        assert manifest.expires_at <= db.get(Approval, row.approval_id).expires_at
    assert check(admission) is True
    assert check(admission) is True  # ongoing authority checks never re-admit
    with pytest.raises(RunnerAdmissionUnknown):
        admit(invocation_id)
    with session_factory()() as db:
        assert len(db.scalars(select(RunnerAttempt)).all()) == 1
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.admission')).all()) == 1


@pytest.mark.parametrize('change', CHANGES+['approval_expired', 'approval_payload'])
def test_admission_rechecks_fresh_staged_authority(authenticated, change):
    details = approved(authenticated)
    mutate(authenticated, details, change)
    with pytest.raises(RunnerAdmissionDenied):
        admit(details[4])
    with session_factory()() as db:
        assert db.scalar(select(RunnerAttempt)) is None
        assert db.get(ToolInvocation, details[4]).status == 'invalidated'


@pytest.mark.parametrize('change', CHANGES+['approval_expired', 'approval_payload'])
def test_ongoing_checks_recheck_and_retain_unknown(authenticated, change):
    details = approved(authenticated)
    admission = admit(details[4])
    mutate(authenticated, details, change)
    with pytest.raises(RunnerAdmissionDenied):
        check(admission)
    with session_factory()() as db:
        row = db.get(RunnerAttempt, details[4])
        assert row.status == 'unknown' and row.reason is not None
    with pytest.raises(RunnerAdmissionUnknown):
        admit(details[4])


@pytest.mark.parametrize('change', [
    {'capability': b'x'*32}, {'capability': b'x'},
    {'manifest_raw': '{}'}, {'manifest_sha256': 'b'*64},
    {'image_id': 'sha256:'+'b'*64}, {'job_sha256': 'b'*64},
])
def test_private_capability_and_exact_pins_cannot_be_substituted(authenticated, change):
    admission = admit(approved(authenticated)[4])
    with pytest.raises(RunnerAdmissionDenied):
        check(replace(admission, **change))
    with pytest.raises(RunnerAdmissionUnknown):
        admit(admission.invocation_id)


@pytest.mark.parametrize('enabled', [False, None, 1, 'true'])
def test_default_denial_touches_no_database(monkeypatch, enabled):
    import workforce.runner_admission as module
    def forbidden():
        raise AssertionError('database contacted')
    monkeypatch.setattr(module, 'session_factory', forbidden)
    with pytest.raises(RunnerAdmissionDenied):
        module.admit_runner_attempt('not-an-id', experiment_enabled=enabled)


def test_concurrent_admission_delivers_one_capability(authenticated):
    invocation_id = approved(authenticated)[4]
    barrier = Barrier(2)
    def attempt():
        barrier.wait(timeout=5)
        try:
            return admit(invocation_id)
        except RunnerAdmissionUnknown:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1
    with session_factory()() as db:
        assert len(db.scalars(select(RunnerAttempt)).all()) == 1


def test_process_loss_after_commit_cannot_recover_or_repeat(authenticated):
    invocation_id = approved(authenticated)[4]
    program = '''
import os, sys
from workforce.runner_admission import admit_runner_attempt
admit_runner_attempt(sys.argv[1], experiment_enabled=True, after_commit=lambda:os._exit(73))
'''
    result = subprocess.run([sys.executable, '-c', program, invocation_id],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 73, result.stderr
    again = subprocess.run([sys.executable, '-c', '''
import sys
from workforce.runner_admission import admit_runner_attempt, RunnerAdmissionUnknown
try:
    admit_runner_attempt(sys.argv[1], experiment_enabled=True)
except RunnerAdmissionUnknown:
    sys.exit(74)
sys.exit(1)
''', invocation_id], capture_output=True, text=True, timeout=15)
    assert again.returncode == 74, again.stderr
    with session_factory()() as db:
        assert db.get(RunnerAttempt, invocation_id).status == 'unknown'


def test_actual_schema_round_trip_preserves_parent_approvals(authenticated):
    invocation_id = approved(authenticated)[4]
    backend = Path(__file__).resolve().parents[1]
    for arguments in [('downgrade', 'a831c4d7e052'), ('upgrade', 'head')]:
        result = subprocess.run([sys.executable, '-m', 'alembic', *arguments],
            cwd=backend, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
    assert check(admit(invocation_id)) is True


def test_downgrade_cannot_erase_consumed_admission(authenticated):
    invocation_id = approved(authenticated)[4]
    admit(invocation_id)
    result = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', 'a831c4d7e052'],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0 and 'Cannot erase consumed runner admissions' in result.stderr
    with pytest.raises(RunnerAdmissionUnknown):
        admit(invocation_id)


@pytest.mark.skipif(os.environ.get('WORKFORCE_DOCKER_GATE') != '1', reason='explicit Docker fixture gate')
def test_isolated_job_with_replaced_journal_cannot_launch_again(authenticated, tmp_path, monkeypatch):
    from runner_isolation_harness import docker
    import runner_admission_harness as bridge
    image_id = docker('image', 'inspect', '--format', '{{.Id}}', 'workforce-backend:phase1')
    invocation_id = approved(authenticated, image_id=image_id)[4]
    first, replacement = tmp_path/'first', tmp_path/'replacement'
    first.mkdir(mode=0o700)
    replacement.mkdir(mode=0o700)
    def committed():
        with session_factory()() as db:
            assert db.get(RunnerAttempt, invocation_id).status == 'unknown'
    receipt = bridge.run_admitted_job(invocation_id, journal=first,
        experiment_enabled=True, after_commit=committed)
    assert receipt.input_size > 0
    def forbidden(*args, **kwargs):
        raise AssertionError('duplicate reached launcher')
    monkeypatch.setattr(bridge, 'run_job', forbidden)
    with pytest.raises(RunnerAdmissionUnknown):
        bridge.run_admitted_job(invocation_id, journal=replacement, experiment_enabled=True)
    assert not list(replacement.iterdir())
    assert docker('ps', '--all', '-q', '--filter', 'label=workforce.runner.attempt='+invocation_id.replace('-', '')) == ''
    with session_factory()() as db:
        assert db.get(RunnerAttempt, invocation_id).status == 'unknown'
        assert db.get(ToolInvocation, invocation_id).status == 'approved_staged'


@pytest.mark.parametrize('field,value', [('currency', 'EUR'), ('spent', -1), ('reserved', -1)])
@pytest.mark.parametrize('ongoing', [False, True])
def test_invalid_root_account_cannot_authorize_fixture(authenticated, field, value, ongoing):
    from workforce.models import BudgetAccount
    details = approved(authenticated)
    admission = admit(details[4]) if ongoing else None
    with session_factory()() as db:
        setattr(db.get(BudgetAccount, details[3]), field, value)
        db.commit()
    with pytest.raises(RunnerAdmissionDenied):
        check(admission) if ongoing else admit(details[4])


@pytest.mark.parametrize('status', ['proposed', 'awaiting_approval', 'admitted', 'succeeded'])
def test_only_exact_staged_status_can_be_admitted(authenticated, status):
    invocation_id = approved(authenticated)[4]
    with session_factory()() as db:
        db.get(ToolInvocation, invocation_id).status = status
        db.commit()
    with pytest.raises(RunnerAdmissionDenied):
        admit(invocation_id)
    with session_factory()() as db:
        assert db.scalar(select(RunnerAttempt)) is None


def test_wrong_capability_does_not_consume_ongoing_authority(authenticated):
    admission = admit(approved(authenticated)[4])
    with pytest.raises(RunnerAdmissionDenied):
        check(replace(admission, capability=b'x'*32))
    assert check(admission) is True
