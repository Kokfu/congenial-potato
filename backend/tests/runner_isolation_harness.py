"""Test-only Docker fixture. Never imported by product API/worker code.

The journal and image ID are trusted operator configuration, never model input.
This private local fence is not the independent DB admission still required by
Phase 8.2b. Missing/stale journal replacement is outside this fixture's recovery
contract. Resource probes are fixed reviewed test code, not runner proposals.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time
from uuid import UUID

from workforce.reviewed_runner_contract import (
    PROFILE, RunnerContractError, canonical_manifest, manifest_digest,
    pinned_runner_manifest,
)
from workforce.runner_fixture_job import (
    canonical_receipt, job_code_digest, verify_runner_receipt,
)


class RunnerOutcomeUnknown(RunnerContractError):
    pass


CONTROL_SECONDS = 30
PROXY_NAMES = ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY',
               'http_proxy','https_proxy','all_proxy','no_proxy')


def docker(*arguments, timeout=CONTROL_SECONDS):
    try:
        result = subprocess.run(['docker', *arguments], text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RunnerOutcomeUnknown('Fixture Docker control outcome unavailable') from None
    if result.returncode:
        raise RunnerOutcomeUnknown('Fixture Docker control outcome unavailable')
    return result.stdout.strip()


def details(container):
    return json.loads(docker('inspect', container))[0]


def _persist(journal: Path, name: str, body: bytes):
    directory = None
    try:
        directory = os.open(journal, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise RunnerContractError('Fixture journal must be private and owned')
        try:
            marker = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        except FileExistsError:
            raise RunnerOutcomeUnknown('Fixture attempt exists; no automatic repeat') from None
        with os.fdopen(marker, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
    except OSError:
        raise RunnerOutcomeUnknown('Fixture attempt persistence unavailable') from None
    finally:
        if directory is not None: os.close(directory)


def _bounded_io(process, payload: bytes, *, deadline, cancelled):
    """Drain bounded pipes without communicate() or a blocking stdin write."""
    streams = selectors.DefaultSelector()
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    pending = memoryview(payload)
    limits = {'stdout': PROFILE.stdout_bytes, 'stderr': PROFILE.stderr_bytes}
    for name in ('stdout', 'stderr'):
        channel = getattr(process, name)
        os.set_blocking(channel.fileno(), False)
        streams.register(channel, selectors.EVENT_READ, name)
    if pending:
        os.set_blocking(process.stdin.fileno(), False)
        streams.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
    else:
        process.stdin.close()
    try:
        while streams.get_map() or process.poll() is None:
            remaining = deadline-time.monotonic()
            if remaining <= 0 or cancelled():
                raise RunnerOutcomeUnknown('Fixture deadline/cancellation; no automatic repeat')
            for key, _ in streams.select(min(.02, remaining)):
                channel, name = key.fileobj, key.data
                if name == 'stdin':
                    try:
                        count = os.write(channel.fileno(), pending[:4096])
                        pending = pending[count:]
                    except BrokenPipeError:
                        pending = pending[len(pending):]
                    except BlockingIOError:
                        continue
                    if not pending:
                        streams.unregister(channel); channel.close()
                else:
                    try:
                        piece = os.read(channel.fileno(), limits[name]-len(output[name])+1)
                    except BlockingIOError:
                        continue
                    if not piece:
                        streams.unregister(channel); channel.close()
                    else:
                        output[name].extend(piece)
                        if len(output[name]) > limits[name]:
                            raise RunnerOutcomeUnknown('Fixture output bound; no automatic repeat')
        return process.returncode, bytes(output['stdout']), bytes(output['stderr'])
    finally:
        streams.close()
        for channel in (process.stdin, process.stdout, process.stderr):
            if not channel.closed: channel.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _check_container(container, *, image_id, attempt_id, binding):
    data = details(container)
    host = data['HostConfig']
    assert data['Image'] == image_id and data['Config']['User'] == '10001:10001'
    assert data['Config']['Labels']['workforce.runner.attempt'] == attempt_id
    assert data['Config']['Labels']['workforce.runner.binding'] == binding
    assert host['ReadonlyRootfs'] and host['NetworkMode'] == 'none'
    assert {v.removeprefix('CAP_') for v in host['CapDrop']} == {'ALL'}
    assert any(v.split(':')[0] == 'no-new-privileges' for v in host['SecurityOpt'])
    assert host['Memory'] == host['MemorySwap'] == PROFILE.memory_bytes
    assert host['PidsLimit'] == PROFILE.pid_limit
    assert host['NanoCpus'] == PROFILE.cpu_count*1_000_000_000
    assert not data['Mounts'] and not host['Privileged']
    assert host['PidMode'] in ('', 'private') and host['IpcMode'] == 'private'
    environment = dict(value.split('=',1) for value in data['Config']['Env'])
    assert all(environment.get(name,'')=='' for name in PROXY_NAMES)
    assert set(environment)-set(PROXY_NAMES) <= {'PATH','LANG','GPG_KEY','PYTHON_VERSION',
        'PYTHON_SHA256','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','PYTHONPATH'}


def _container_run(*, image_id, attempt_id, binding, command, payload, cancelled,
                   after_create=None, before_start=None, after_job=None,
                   accept_result=None, deadline=None):
    """Only called after the caller persists its fence. Always clean known IDs."""
    container = None
    try:
        cleared_proxy = [item for name in PROXY_NAMES for item in ('--env',name+'=')]
        container = docker('create', '--pull', 'never', '-i', '--name', 'workforce-runner-'+attempt_id,
            '--label', 'workforce.runner.attempt='+attempt_id,
            '--label', 'workforce.runner.binding='+binding,
            '--network', 'none', '--read-only', '--user', '10001:10001',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--memory', str(PROFILE.memory_bytes), '--memory-swap', str(PROFILE.memory_bytes),
            '--pids-limit', str(PROFILE.pid_limit), '--cpus', str(PROFILE.cpu_count),
            *cleared_proxy, '--entrypoint', 'python', image_id, *command)
        _check_container(container, image_id=image_id, attempt_id=attempt_id, binding=binding)
        if after_create: after_create(container)
        if before_start: before_start()
        if cancelled(): raise RunnerOutcomeUnknown('Fixture cancelled before start')
        # The independent child watchdog bounds actual job work. The parent
        # also bounds control-channel startup/draining against manifest expiry;
        # a slow Docker start is not permission to extend the child's timer.
        end = time.monotonic()+CONTROL_SECONDS
        if deadline is not None: end = min(end, deadline)
        if end <= time.monotonic():
            raise RunnerOutcomeUnknown('Fixture expired before start')
        process = subprocess.Popen(['docker','start','-ai',container], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = _bounded_io(process, payload, deadline=end, cancelled=cancelled)
        if after_job: after_job(container)
        if accept_result: result = accept_result(result)
        return result
    finally:
        if container is not None:
            docker('rm', '-f', container)


def run_job(raw, *, expected_sha256, image_id, journal, authorize,
            cancelled=lambda:False, experiment_enabled=False,
            after_fence=None, after_create=None, after_job=None):
    if (experiment_enabled is not True or not callable(authorize) or
            not isinstance(image_id, str) or
            not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)):
        raise RunnerContractError('Isolated runner fixture disabled or unpinned')
    # Inspect identity first so a durable duplicate stays unknown even after
    # expiry. Fresh current-time checks remain mandatory before any launch.
    manifest = pinned_runner_manifest(raw, expected_sha256=expected_sha256)
    code = job_code_digest()
    binding = {'manifest_sha256': manifest_digest(manifest), 'image_id':image_id,
               'job_sha256':code}
    attempt = manifest.scope.attempt_id.hex
    _persist(journal, attempt+'.attempt', json.dumps(binding,sort_keys=True).encode()+b'\n')
    if after_fence: after_fence()
    def check(stage):
        manifest.current()
        if cancelled() or authorize(stage, manifest) is not True:
            raise RunnerOutcomeUnknown('Fixture authority/cancellation unavailable')
        manifest.current()
    check('before')
    remaining = (manifest.expires_at-datetime.now(timezone.utc)).total_seconds()
    def accept(result):
        status, stdout, stderr = result
        if status != 0 or stderr:
            raise RunnerOutcomeUnknown('Fixture result unavailable; no automatic repeat')
        try:
            receipt = verify_runner_receipt(stdout.decode('utf-8'), manifest, expected_job_sha256=code)
        except (ValueError, TypeError):
            raise RunnerOutcomeUnknown('Fixture receipt unavailable; no automatic repeat') from None
        check('after')
        _persist(journal, attempt+'.result', canonical_receipt(receipt).encode()+b'\n')
        return receipt
    # Accept while the manifest is current; slow Docker teardown is subsequent
    # housekeeping, not permission to extend expiry or re-run the job.
    return _container_run(image_id=image_id, attempt_id=attempt,
        binding=expected_sha256, command=['-m','workforce.runner_fixture_job',expected_sha256,code],
        payload=canonical_manifest(manifest).encode(), cancelled=cancelled,
        after_create=after_create, before_start=lambda:check('before_start'),
        after_job=after_job, accept_result=accept, deadline=time.monotonic()+remaining)


def run_reviewed_probe(code, *, image_id, attempt_id: UUID, journal, cancelled=lambda:False,
                       after_create=None, after_job=None, watchdog=True):
    """Fixed reviewed test probes ONLY; never accepted as runner receipts."""
    if not isinstance(image_id, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise RunnerContractError('Probe image must be pinned')
    import hashlib
    binding = hashlib.sha256(code.encode()).hexdigest()
    _persist(journal, attempt_id.hex+'.attempt', binding.encode()+b'\n')
    if watchdog:
        code = ('import os,signal\nsignal.signal(signal.SIGALRM,lambda *_:os._exit(124))\n'
                f'signal.setitimer(signal.ITIMER_REAL,{PROFILE.wall_seconds})\n')+code
    return _container_run(image_id=image_id, attempt_id=attempt_id.hex, binding=binding,
        command=['-c',code], payload=b'', cancelled=cancelled, after_create=after_create,
        after_job=after_job)
