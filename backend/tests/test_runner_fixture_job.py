from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
from threading import Event, Timer
import time
from uuid import uuid4

import pytest

from workforce.reviewed_runner_contract import (
    MAX_WIRE_BYTES, PROFILE, RunnerContractError, RunnerScope, build_runner_manifest,
    canonical_manifest, manifest_digest, parse_runner_input,
)
from workforce.runner_fixture_job import (
    canonical_receipt, execute_fixture_job, job_code_digest, verify_runner_receipt,
)
from runner_isolation_harness import RunnerOutcomeUnknown, _bounded_io, _persist, run_job


def current_manifest(text='synthetic 🙂'):
    at = datetime.now(timezone.utc)
    return build_runner_manifest(parse_runner_input(json.dumps({'text':text})),
        scope=RunnerScope(project_id=uuid4(),agent_id=uuid4(),root_id=uuid4(),attempt_id=uuid4()),
        issued_at=at,expires_at=at+timedelta(seconds=30))


def receipt(value):
    return execute_fixture_job(canonical_manifest(value),
        expected_manifest_sha256=manifest_digest(value), expected_job_sha256=job_code_digest())


def test_fixed_job_returns_only_bound_metadata():
    value = current_manifest('PRIVATE_CANARY; $(read-secret)')
    raw = canonical_receipt(receipt(value))
    assert 'PRIVATE_CANARY' not in raw and value.input.text not in raw
    assert len(raw.encode())+1 <= PROFILE.stdout_bytes
    assert verify_runner_receipt(raw,value,expected_job_sha256=job_code_digest()).input_size == value.input_size


@pytest.mark.parametrize('code', ['0'*64,'not-a-pin','🙂',None])
def test_job_requires_reviewed_source_pin(code):
    value = current_manifest()
    with pytest.raises(RunnerContractError):
        execute_fixture_job(canonical_manifest(value),expected_manifest_sha256=manifest_digest(value),
                            expected_job_sha256=code)


@pytest.mark.parametrize('field,new', [('manifest_sha256','0'*64),('profile_sha256','0'*64),
    ('job_sha256','0'*64),('input_sha256','0'*64),('input_size',0),('version',True),
    ('content','PRIVATE_CANARY')])
def test_receipt_cannot_change_scope_job_input_or_schema(field,new):
    value = current_manifest()
    data = json.loads(canonical_receipt(receipt(value))); data[field]=new
    with pytest.raises(RunnerContractError):
        verify_runner_receipt(json.dumps(data),value,expected_job_sha256=job_code_digest())


@pytest.mark.parametrize('raw', ['x'*(PROFILE.stdout_bytes+1),'\ud800',
                               '{"version":1,"version":1}', '[]'])
def test_receipt_bounds_and_ambiguity_are_denied(raw):
    with pytest.raises(RunnerContractError):
        verify_runner_receipt(raw,current_manifest(),expected_job_sha256=job_code_digest())


def test_cli_watchdog_exits_even_when_stdin_never_closes():
    value = current_manifest()
    with subprocess.Popen([sys.executable,'-m','workforce.runner_fixture_job',
            manifest_digest(value),job_code_digest()],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
        started = time.monotonic()
        assert process.wait(timeout=5) == 124
        assert time.monotonic()-started < 4
        assert process.stdout.read() == process.stderr.read() == b''


def test_cli_rejects_oversized_input_without_echoing_it():
    value = current_manifest()
    result = subprocess.run([sys.executable,'-m','workforce.runner_fixture_job',
        manifest_digest(value),job_code_digest()],input=b'C'*(MAX_WIRE_BYTES+1),
        capture_output=True,timeout=5)
    assert result.returncode == 2 and result.stdout == b''
    assert result.stderr == b'runner_fixture=denied\n'


@pytest.mark.parametrize('stream', ['stdout','stderr'])
def test_parent_pipe_drain_kills_output_above_bound(stream):
    program = f'import os; os.write({1 if stream=="stdout" else 2}, b"x"*1025)'
    process = subprocess.Popen([sys.executable,'-c',program],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    with pytest.raises(RunnerOutcomeUnknown,match='output bound'):
        _bounded_io(process,b'',deadline=time.monotonic()+2,cancelled=lambda:False)
    assert process.poll() is not None


@pytest.mark.parametrize('kind', ['cancel','blocked_stdin'])
def test_parent_bounds_cancelled_or_blocked_input(kind):
    process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    cancelled = Event()
    timer = Timer(.1,cancelled.set) if kind=='cancel' else None
    if timer:timer.start()
    try:
        started = time.monotonic()
        with pytest.raises(RunnerOutcomeUnknown):
            _bounded_io(process,b'x'*MAX_WIRE_BYTES,deadline=started+.3,cancelled=cancelled.is_set)
        assert process.poll() is not None and time.monotonic()-started < 2
    finally:
        if timer:timer.join()


def test_fence_is_private_exclusive_and_partial_markers_never_reset(tmp_path):
    journal = tmp_path/'journal'; journal.mkdir(mode=0o700)
    def fence(_):
        try:_persist(journal,'fixed.attempt',b'bound-metadata\n'); return 'fenced'
        except RunnerOutcomeUnknown:return 'unknown'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(fence,range(2))) == ['fenced','unknown']
    marker = journal/'fixed.attempt'
    assert marker.read_bytes()==b'bound-metadata\n' and marker.stat().st_mode & 0o777==0o600
    marker.write_bytes(b'')
    with pytest.raises(RunnerOutcomeUnknown):_persist(journal,marker.name,b'new')
    assert marker.read_bytes()==b''


@pytest.mark.parametrize('kind', ['weak','directory_symlink','marker_symlink'])
def test_fence_refuses_unsafe_storage_without_overwriting_targets(tmp_path,kind):
    journal=tmp_path/'journal'; journal.mkdir(mode=0o700)
    target=tmp_path/'preserve'; target.write_text('preserve')
    if kind=='weak':journal.chmod(0o755)
    elif kind=='directory_symlink':
        alias=tmp_path/'alias'; alias.symlink_to(journal); journal=alias
    else:(journal/'one.attempt').symlink_to(target)
    with pytest.raises(RunnerContractError):_persist(journal,'one.attempt',b'new')
    assert target.read_text()=='preserve'


@pytest.mark.parametrize('allowed', [None,False])
def test_unconfirmed_authority_never_reaches_docker_or_records_result(tmp_path,monkeypatch,allowed):
    import runner_isolation_harness as harness
    monkeypatch.setattr(harness,'docker',lambda *args,**kwargs:pytest.fail('Docker reached'))
    journal=tmp_path/'journal'; journal.mkdir(mode=0o700)
    value=current_manifest()
    with pytest.raises(RunnerOutcomeUnknown):
        run_job(canonical_manifest(value),expected_sha256=manifest_digest(value),
            image_id='sha256:'+'0'*64,journal=journal,authorize=lambda *args:allowed,experiment_enabled=True)
    assert len(list(journal.glob('*.attempt')))==1 and not list(journal.glob('*.result'))


@pytest.mark.parametrize('enabled,image', [(None,'sha256:'+'0'*64),
    (False,'sha256:'+'0'*64),('true','sha256:'+'0'*64),
    (True,'workforce-backend:phase1'),(True,None)])
def test_disabled_or_unpinned_launch_cannot_persist_or_contact_docker(tmp_path,monkeypatch,enabled,image):
    import runner_isolation_harness as harness
    monkeypatch.setattr(harness,'docker',lambda *args,**kwargs:pytest.fail('Docker reached'))
    journal=tmp_path/'journal'; journal.mkdir(mode=0o700)
    value=current_manifest()
    with pytest.raises(RunnerContractError):
        run_job(canonical_manifest(value),expected_sha256=manifest_digest(value),
            image_id=image,journal=journal,authorize=lambda *_:True,experiment_enabled=enabled)
    assert not list(journal.iterdir())


def test_expired_manifest_never_launches_and_existing_fence_stays_unknown(tmp_path,monkeypatch):
    import runner_isolation_harness as harness
    monkeypatch.setattr(harness,'docker',lambda *args,**kwargs:pytest.fail('Docker reached'))
    journal=tmp_path/'journal'; journal.mkdir(mode=0o700)
    value=current_manifest()
    old=datetime.now(timezone.utc)-timedelta(minutes=1)
    value=build_runner_manifest(value.input,scope=value.scope,
        issued_at=old,expires_at=old+timedelta(seconds=30))
    arguments=dict(expected_sha256=manifest_digest(value),image_id='sha256:'+'0'*64,
        journal=journal,authorize=lambda *_:True,experiment_enabled=True)
    with pytest.raises(RunnerContractError):run_job(canonical_manifest(value),**arguments)
    with pytest.raises(RunnerOutcomeUnknown):run_job(canonical_manifest(value),**arguments)
    assert len(list(journal.glob('*.attempt')))==1 and not list(journal.glob('*.result'))
