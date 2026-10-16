"""Synthetic process-loss/authentication regressions, not stale-restore proof."""
from dataclasses import asdict
import json
import subprocess
import sys

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import AuditEvent, ProjectActivity, RunnerAttempt, RunnerResult, ToolInvocation
from workforce.runner_admission import RunnerAdmissionUnknown
from test_runner_admission import admit
from test_runner_result_acceptance import KEY, accept, candidate

LOAD = '''
import json, sys
from pathlib import Path
from workforce.runner_admission import RunnerAdmission
from workforce.runner_result_acceptance import accept_runner_result
p=json.loads(Path(sys.argv[1]).read_text())
a=p['admission']; a['capability']=bytes.fromhex(a['capability'])
a=RunnerAdmission(**a)
key=bytes.fromhex(p['key'])
'''


def private_delivery(tmp_path, admission, envelope):
    path = tmp_path/'private-delivery.json'
    path.write_text(json.dumps({'admission': asdict(admission) | {
        'capability': admission.capability.hex()}, 'envelope': envelope, 'key': KEY.hex()}))
    path.chmod(0o600)
    return path


def interpreter(program, path):
    return subprocess.run([sys.executable, '-c', LOAD+program, str(path)],
        capture_output=True, text=True, timeout=15)


def state(invocation):
    with session_factory()() as db:
        attempt = db.get(RunnerAttempt, invocation)
        result = db.get(RunnerResult, invocation)
        return (attempt.status, attempt.accepted_result_hash, attempt.reason,
            db.get(ToolInvocation, invocation).status, result.payload_hash if result else None,
            len(db.scalars(select(AuditEvent).where(AuditEvent.action == 'runner.result')).all()),
            len(db.scalars(select(ProjectActivity).where(ProjectActivity.action == 'runner.result')).all()))


def test_process_exit_after_flush_before_commit_preserves_consumed_unknown(authenticated, tmp_path):
    _, admission, envelope = candidate(authenticated)
    original = state(admission.invocation_id)
    path = private_delivery(tmp_path, admission, envelope)
    result = interpreter('''
import os
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from workforce.models import AuditEvent, ProjectActivity, RunnerAttempt, RunnerResult, ToolInvocation

def crash(db):
    db.flush()
    result=db.get(RunnerResult, a.invocation_id)
    assert result is not None
    attempt=db.get(RunnerAttempt, a.invocation_id)
    assert attempt.status=='accepted' and attempt.accepted_result_hash==result.payload_hash
    assert db.get(ToolInvocation, a.invocation_id).status=='runner_result_accepted'
    assert db.scalars(select(AuditEvent).where(AuditEvent.action=='runner.result')).one().outcome=='accepted'
    assert db.scalars(select(ProjectActivity).where(ProjectActivity.action=='runner.result')).one().outcome=='accepted'
    os._exit(74)
event.listen(Session, 'before_commit', crash)
accept_runner_result(a,p['envelope'],key=key,experiment_enabled=True)
''', path)
    assert result.returncode == 74, result.stderr
    assert state(admission.invocation_id) == original
    assert original == ('unknown', None, None, 'approved_staged', None, 0, 0)
    with pytest.raises(RunnerAdmissionUnknown):
        admit(admission.invocation_id)
    # A retained authenticated receipt can be delivered, never recomputed.
    accepted = accept(admission, envelope)
    assert accept(admission, envelope) == accepted
    assert state(admission.invocation_id)[-2:] == (1, 1)


@pytest.mark.parametrize('already_accepted', [False, True])
@pytest.mark.parametrize('missing', ['key_lost', 'key_wrong', 'capability_lost', 'capability_wrong'])
def test_unavailable_authentication_in_fresh_process_never_changes_history(
        authenticated, tmp_path, already_accepted, missing):
    _, admission, envelope = candidate(authenticated)
    accepted = accept(admission, envelope) if already_accepted else None
    original = state(admission.invocation_id)
    path = private_delivery(tmp_path, admission, envelope)
    program = '''
from dataclasses import replace
from workforce.reviewed_runner_contract import RunnerContractError
'''+{
        'key_lost': 'key=None\n',
        'key_wrong': "key=b'x'*32\n",
        'capability_lost': 'a=replace(a,capability=None)\n',
        'capability_wrong': "a=replace(a,capability=b'x'*32)\n",
    }[missing]+'''
try:
    accept_runner_result(a,p['envelope'],key=key,experiment_enabled=True)
except RunnerContractError:
    pass
else:
    raise AssertionError('Unavailable private identity accepted')
'''
    refused = interpreter(program, path)
    assert refused.returncode == 0, refused.stderr
    assert state(admission.invocation_id) == original
    with pytest.raises(RunnerAdmissionUnknown):
        admit(admission.invocation_id)
    retained = interpreter('''
r=accept_runner_result(a,p['envelope'],key=key,experiment_enabled=True)
print(r.payload_hash)
''', path)
    assert retained.returncode == 0, retained.stderr
    replay = accept(admission, envelope)
    assert retained.stdout.strip() == replay.payload_hash
    assert accepted is None or accepted == replay
    assert state(admission.invocation_id)[-2:] == (1, 1)
