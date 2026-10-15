"""Fixed synthetic digest job. Explicit fixture CLI only; no product route.

Input is data, never Python, a command, an image, a path or environment. The
host fixture must pin this file AND the immutable image containing its imports.
Receipts alone do not prove execution or establish database authority.
"""
import hashlib
import hmac
import os
from pathlib import Path
import signal
import sys
from typing import Literal

from pydantic import Field, field_validator

from .reviewed_runner_contract import (
    MAX_INPUT_BYTES, MAX_WIRE_BYTES, PROFILE, RunnerContractError, RunnerManifest,
    _StrictModel, _canonical, _parse, canonical_manifest, manifest_digest,
    verify_runner_manifest,
)


class RunnerReceipt(_StrictModel):
    version: Literal[1]
    manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    job_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_size: int = Field(ge=0, le=MAX_INPUT_BYTES)

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Runner receipt version unavailable')
        return value


def job_code_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def execute_fixture_job(raw: str, *, expected_manifest_sha256: str,
                        expected_job_sha256: str) -> RunnerReceipt:
    if (not isinstance(expected_job_sha256, str) or
            len(expected_job_sha256) != 64 or
            any(c not in '0123456789abcdef' for c in expected_job_sha256) or
            not hmac.compare_digest(job_code_digest(), expected_job_sha256)):
        raise RunnerContractError('Reviewed fixture code unavailable')
    manifest = verify_runner_manifest(raw, expected_sha256=expected_manifest_sha256)
    body = manifest.input.text.encode('utf-8')
    result = RunnerReceipt(version=1, manifest_sha256=manifest_digest(manifest),
        profile_sha256=manifest.profile_sha256, job_sha256=job_code_digest(),
        input_sha256=hashlib.sha256(body).hexdigest(), input_size=len(body))
    manifest.current()
    return result


def canonical_receipt(receipt: RunnerReceipt) -> str:
    try:
        raw = _canonical(RunnerReceipt.model_validate(receipt).model_dump(mode='json'))
        if len(raw.encode('utf-8'))+1 > PROFILE.stdout_bytes:
            raise ValueError('Runner receipt exceeds output bound')
        return raw
    except (ValueError, TypeError):
        raise RunnerContractError('Runner receipt unavailable') from None


def verify_runner_receipt(raw: str, manifest: RunnerManifest, *,
                           expected_job_sha256: str) -> RunnerReceipt:
    try:
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > PROFILE.stdout_bytes:
            raise ValueError('Runner receipt exceeds output bound')
    except (ValueError, TypeError):
        raise RunnerContractError('Runner receipt unavailable') from None
    receipt = _parse(raw, RunnerReceipt)
    canonical_manifest(manifest)  # revalidate copied models before using fields
    manifest.current()
    if (receipt.manifest_sha256 != manifest_digest(manifest) or
            receipt.profile_sha256 != manifest.profile_sha256 or
            receipt.job_sha256 != expected_job_sha256 or
            receipt.input_sha256 != manifest.input_sha256 or
            receipt.input_size != manifest.input_size):
        raise RunnerContractError('Runner receipt binding unavailable')
    return receipt


def main() -> int:
    # An independent child watchdog complements the host's bounded I/O/kill.
    # Linux/POSIX is the only accepted fixture platform.
    # Namespace PID 1 may ignore signals with a default disposition. An explicit
    # handler exits without catchable cleanup or payload-bearing tracebacks.
    signal.signal(signal.SIGALRM, lambda *_:os._exit(124))
    inherited = signal.getitimer(signal.ITIMER_REAL)[0]
    signal.setitimer(signal.ITIMER_REAL, min(inherited,PROFILE.wall_seconds)
                     if inherited>0 else PROFILE.wall_seconds)
    try:
        if len(sys.argv) != 3:
            raise RunnerContractError('Fixture requires two pinned digests')
        body = sys.stdin.buffer.read(MAX_WIRE_BYTES+1)
        if len(body) > MAX_WIRE_BYTES:
            raise RunnerContractError('Runner wire bound unavailable')
        result = execute_fixture_job(body.decode('utf-8'),
            expected_manifest_sha256=sys.argv[1], expected_job_sha256=sys.argv[2])
        sys.stdout.write(canonical_receipt(result)+'\n')
        sys.stdout.flush()
        return 0
    except (ValueError, TypeError, OSError):
        sys.stderr.write('runner_fixture=denied\n')
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


if __name__ == '__main__':
    raise SystemExit(main())
