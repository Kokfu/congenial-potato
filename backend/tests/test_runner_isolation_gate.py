from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time
from uuid import uuid4

import pytest

from workforce.reviewed_runner_contract import canonical_manifest, manifest_digest
from workforce.runner_fixture_job import job_code_digest
from runner_isolation_harness import (
    RunnerOutcomeUnknown, details, docker, run_job, run_reviewed_probe,
)
from test_runner_fixture_job import current_manifest

pytestmark = pytest.mark.skipif(os.environ.get('WORKFORCE_DOCKER_GATE')!='1',
                              reason='explicit local Docker gate required')


@pytest.fixture
def image_id():
    return docker('image','inspect','--format','{{.Id}}','workforce-backend:phase1')


@pytest.fixture
def journal(tmp_path):
    path=tmp_path/'journal'; path.mkdir(mode=0o700)
    return path


def remaining(attempt):
    return docker('ps','--all','-q','--filter','label=workforce.runner.attempt='+attempt)


def run(value,image_id,journal,**kwargs):
    return run_job(canonical_manifest(value),expected_sha256=manifest_digest(value),
        image_id=image_id,journal=journal,authorize=kwargs.pop('authorize',lambda *_:True),
        experiment_enabled=True,**kwargs)


def test_reviewed_job_has_a_durable_fence_before_any_container_and_one_receipt(image_id,journal):
    value=current_manifest('PRIVATE_CANARY; do not execute this text')
    attempt=value.scope.attempt_id.hex
    stages=[]; containers=[]
    def fenced():
        marker=journal/(attempt+'.attempt')
        binding=json.loads(marker.read_text())
        assert binding=={'manifest_sha256':manifest_digest(value),'image_id':image_id,
                         'job_sha256':job_code_digest()}
        assert marker.stat().st_mode & 0o777==0o600 and not remaining(attempt)
        assert 'PRIVATE_CANARY' not in marker.read_text()
    result=run(value,image_id,journal,after_fence=fenced,
        after_create=lambda cid:containers.append(cid),
        authorize=lambda stage,_:stages.append(stage) or True)
    assert result.input_sha256==value.input_sha256 and stages==['before','before_start','after']
    assert len(containers)==1 and not remaining(attempt)
    assert json.loads((journal/(attempt+'.result')).read_text())['input_size']==value.input_size
    assert 'PRIVATE_CANARY' not in (journal/(attempt+'.result')).read_text()
    with pytest.raises(RunnerOutcomeUnknown):run(value,image_id,journal)
    assert not remaining(attempt)


def test_fixed_resource_probe_observes_namespace_privileges_and_read_only_root(image_id,journal):
    code='''
import errno,json,os,socket
from pathlib import Path
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert os.getpid()==1 and os.getuid()==os.getgid()==10001
assert int(status['CapEff'].strip(),16)==0
assert status['NoNewPrivs'].strip()=='1' and status['Seccomp'].strip()=='2'
assert not Path('/run/secrets/db_password').exists() and not Path('/var/run/docker.sock').exists()
try:Path('/tmp/forbidden-write').write_text('synthetic')
except OSError as exc:assert exc.errno==errno.EROFS
else:raise AssertionError('root writable')
assert len(Path('/proc/net/route').read_text().splitlines())==1
with socket.socket() as connection:
    connection.settimeout(.1)
    try:connection.connect(('127.0.0.1',9))
    except OSError:pass
    else:raise AssertionError('unexpected loopback service')
assert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='134217728'
assert Path('/sys/fs/cgroup/pids.max').read_text().strip()=='32'
quota,period=map(int,Path('/sys/fs/cgroup/cpu.max').read_text().split())
assert quota/period==1
print(json.dumps({'uid':os.getuid(),'caps':'none','seccomp':2,'nnp':True,'readonly':True,'routes':'none','cgroups':'bounded'}))
'''
    attempt=uuid4()
    status,out,err=run_reviewed_probe(code,image_id=image_id,attempt_id=attempt,journal=journal)
    assert status==0 and not err and json.loads(out)['cgroups']=='bounded'
    assert not remaining(attempt.hex)


def test_memory_limit_actually_kills_oversized_allocation(image_id,journal):
    observed=[]; attempt=uuid4()
    # Capture kernel OOM state before normal fixture cleanup removes the ID.
    status,out,err=run_reviewed_probe('data=bytearray(256*1024*1024)',
        image_id=image_id,attempt_id=attempt,journal=journal,
        after_job=lambda cid:observed.append(details(cid)['State']['OOMKilled']))
    assert status==137 and observed==[True] and not out and not err
    assert not remaining(attempt.hex)


def test_pid_limit_denies_more_children(image_id,journal):
    code='''
import errno,json,os,signal,time
children=[]
try:
    for _ in range(40):
        try:child=os.fork()
        except OSError as exc:
            assert exc.errno==errno.EAGAIN
            print(json.dumps({'limit_hit':True,'children':len(children)}),flush=True)
            break
        if child==0:
            time.sleep(10)
            os._exit(0)
        children.append(child)
    else:raise AssertionError('PID limit not enforced')
finally:
    for child in children:os.kill(child,signal.SIGKILL)
    for child in children:os.waitpid(child,0)
'''
    status,out,err=run_reviewed_probe(code,image_id=image_id,attempt_id=uuid4(),journal=journal)
    value=json.loads(out)
    assert status==0 and not err and value['limit_hit'] and 0<value['children']<32


def test_parallel_cpu_probe_stays_within_kernel_quota(image_id,journal):
    code='''
import json,os,time
from pathlib import Path
def usage():return int(dict(line.split() for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())['usage_usec'])/1000000
before=usage(); started=time.monotonic(); children=[]
for _ in range(4):
    child=os.fork()
    if child==0:
        end=time.monotonic()+.4
        while time.monotonic()<end:pass
        os._exit(0)
    children.append(child)
for child in children:os.waitpid(child,0)
wall=time.monotonic()-started
print(json.dumps({'wall':wall,'cpu':usage()-before}))
'''
    status,out,err=run_reviewed_probe(code,image_id=image_id,attempt_id=uuid4(),journal=journal)
    value=json.loads(out)
    assert status==0 and not err and value['cpu']<=value['wall']*1.5+.05


@pytest.mark.parametrize('descriptor',[1,2])
def test_container_output_overflow_is_unknown_and_cleaned(image_id,journal,descriptor):
    attempt=uuid4()
    with pytest.raises(RunnerOutcomeUnknown,match='output bound'):
        run_reviewed_probe(f'import os; os.write({descriptor},b"x"*1025)',
            image_id=image_id,attempt_id=attempt,journal=journal)
    assert (journal/(attempt.hex+'.attempt')).exists() and not remaining(attempt.hex)


def test_job_wall_timeout_cleans_the_container_and_retains_unknown(image_id,journal):
    attempt=uuid4(); observed=[]
    status,out,err=run_reviewed_probe('import time; time.sleep(10)',image_id=image_id,
        attempt_id=attempt,journal=journal,after_job=lambda cid:observed.append(details(cid)['State']))
    assert status==124 and not out and not err and not remaining(attempt.hex)
    elapsed=(datetime.fromisoformat(observed[0]['FinishedAt'].replace('Z','+00:00'))-
             datetime.fromisoformat(observed[0]['StartedAt'].replace('Z','+00:00'))).total_seconds()
    assert 1.8<=elapsed<3.5
    assert (journal/(attempt.hex+'.attempt')).exists()


def test_job_watchdog_independently_exits_as_namespace_pid_one(image_id,journal):
    # Disable the probe's outer timer so only the actual job main watchdog can
    # terminate its blocked input. The bounded parent remains a 30s backstop.
    code='''
import sys,time
from workforce.runner_fixture_job import main
class BlockedInput:
    @property
    def buffer(self):return self
    def read(self,*_):time.sleep(10);return b''
sys.stdin=BlockedInput()
sys.argv=['fixture','0'*64,'0'*64]
raise SystemExit(main())
'''
    status,out,err=run_reviewed_probe(code,image_id=image_id,attempt_id=uuid4(),
                                    journal=journal,watchdog=False)
    assert status==124 and not out and not err


def test_inflight_cancellation_observes_running_container_before_cleanup(image_id,journal):
    attempt=uuid4(); cancelled=Event(); observed=Event(); threads=[]
    def watch(cid):
        def observe():
            end=time.monotonic()+2
            while time.monotonic()<end:
                if details(cid)['State']['Running']:
                    observed.set(); cancelled.set(); return
                time.sleep(.01)
        thread=Thread(target=observe); thread.start(); threads.append(thread)
    try:
        with pytest.raises(RunnerOutcomeUnknown):
            run_reviewed_probe('import time; time.sleep(10)',image_id=image_id,
                attempt_id=attempt,journal=journal,cancelled=cancelled.is_set,after_create=watch)
        assert observed.is_set() and not remaining(attempt.hex)
    finally:
        for thread in threads:thread.join(timeout=3); assert not thread.is_alive()


def test_cancellation_after_create_prevents_start(image_id,journal):
    value=current_manifest(); cancelled=Event(); created=[]
    def cancel(cid):
        created.append(details(cid)['State']['Status']); cancelled.set()
    with pytest.raises(RunnerOutcomeUnknown):
        run(value,image_id,journal,after_create=cancel,cancelled=cancelled.is_set)
    assert created==['created'] and not remaining(value.scope.attempt_id.hex)
    assert not list(journal.glob('*.result'))


def test_changed_code_pin_and_post_result_authority_do_not_persist_receipts(image_id,journal,monkeypatch):
    import runner_isolation_harness as harness
    value=current_manifest()
    original=harness.job_code_digest
    monkeypatch.setattr(harness,'job_code_digest',lambda:'0'*64)
    with pytest.raises(RunnerOutcomeUnknown):run(value,image_id,journal)
    monkeypatch.setattr(harness,'job_code_digest',original)
    other=current_manifest()
    with pytest.raises(RunnerOutcomeUnknown):
        run(other,image_id,journal,authorize=lambda stage,_:stage!='after')
    assert len(list(journal.glob('*.attempt')))==2 and not list(journal.glob('*.result'))
    assert not remaining(value.scope.attempt_id.hex) and not remaining(other.scope.attempt_id.hex)


@pytest.mark.parametrize('stage',['after_fence','after_job'])
def test_process_loss_and_fresh_interpreter_cannot_repeat_a_durable_attempt(image_id,journal,tmp_path,stage):
    value=current_manifest(); attempt=value.scope.attempt_id.hex
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'raw':canonical_manifest(value),'digest':manifest_digest(value),
                                  'image':image_id,'journal':str(journal),'stage':stage}))
    config.chmod(0o600)
    program='''
import json,os,sys
from pathlib import Path
from runner_isolation_harness import run_job,RunnerOutcomeUnknown
cfg=json.loads(Path(sys.argv[1]).read_text())
def crash(*_):os._exit(73)
hooks={cfg['stage']:crash} if sys.argv[2]=='crash' else {}
try:
    run_job(cfg['raw'],expected_sha256=cfg['digest'],image_id=cfg['image'],journal=Path(cfg['journal']),
        authorize=lambda *_:True,experiment_enabled=True,**hooks)
except RunnerOutcomeUnknown:
    print('unknown; no repeat',flush=True)
'''
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':os.pathsep.join((str(root/'backend/src'),str(root/'backend/tests')))}
    try:
        first=subprocess.run([sys.executable,'-c',program,str(config),'crash'],env=env,
                             capture_output=True,text=True,timeout=40)
        assert first.returncode==73,first.stderr
        before=remaining(attempt).splitlines()
        assert len(before)==(1 if stage=='after_job' else 0)
        second=subprocess.run([sys.executable,'-c',program,str(config),'restart'],env=env,
                              capture_output=True,text=True,timeout=10)
        assert second.returncode==0 and second.stdout=='unknown; no repeat\n',second.stderr
        assert remaining(attempt).splitlines()==before and not list(journal.glob('*.result'))
    finally:
        for cid in remaining(attempt).splitlines():
            data=details(cid)
            assert data['Image']==image_id and data['Config']['Labels']['workforce.runner.attempt']==attempt
            docker('rm','-f',cid)
