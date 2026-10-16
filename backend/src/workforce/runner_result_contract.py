"""Transient authenticated fixture metadata, not DB acceptance or attestation.

The host-only result key is distinct from the ongoing admission capability.
Callers must independently check current DB authority around signing/acceptance.
No signing key is supplied to the isolated job. No product route imports this.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import re
from typing import Literal

from pydantic import Field, field_validator

from .reviewed_runner_contract import (PROFILE, RunnerContractError, RunnerScope, _StrictModel,
    _canonical, _parse, _utc, pinned_runner_manifest)
from .runner_admission import RunnerAdmission
from .runner_fixture_job import RunnerReceipt, canonical_receipt, verify_runner_receipt

MAX_RESULT_BYTES = 8192
_RESULT_DOMAIN = b'workforce.runner.result.v1\0'


class RunnerResultPayload(_StrictModel):
    version: Literal[1]
    scope: RunnerScope
    image_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    admission_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    receipt: RunnerReceipt
    completed_at: datetime

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Runner result version unavailable')
        return value

    @field_validator('completed_at')
    @classmethod
    def aware_time(cls, value):
        return _utc(value)


class _ResultEnvelope(_StrictModel):
    result: RunnerResultPayload
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')


def _context(admission, key, *, current=True):
    if (type(admission) is not RunnerAdmission or type(key) is not bytes or len(key) != 32
            or type(admission.capability) is not bytes or len(admission.capability) != 32
            or hmac.compare_digest(key, admission.capability)
            or not isinstance(admission.image_id, str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', admission.image_id)
            or not isinstance(admission.job_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', admission.job_sha256)):
        raise RunnerContractError('Private runner result configuration unavailable')
    manifest = pinned_runner_manifest(admission.manifest_raw,
                                      expected_sha256=admission.manifest_sha256)
    if str(manifest.scope.attempt_id) != admission.invocation_id:
        raise RunnerContractError('Runner result admission unavailable')
    if current:
        manifest.current()
    return manifest


def _wire(payload):
    return _RESULT_DOMAIN + _canonical(payload.model_dump(mode='json')).encode('utf-8')


def _bound(payload, admission, manifest, *, current=True):
    if (payload.scope != manifest.scope or payload.image_id != admission.image_id or
            payload.admission_sha256 != hashlib.sha256(admission.capability).hexdigest() or
            not manifest.issued_at <= payload.completed_at <= datetime.now(timezone.utc) or
            payload.completed_at >= manifest.expires_at):
        raise RunnerContractError('Runner result bindings unavailable')
    canonical_receipt(payload.receipt)  # revalidate copied receipt models
    receipt = payload.receipt
    if (receipt.manifest_sha256 != admission.manifest_sha256 or
            receipt.profile_sha256 != manifest.profile_sha256 or
            receipt.job_sha256 != admission.job_sha256 or
            receipt.input_sha256 != manifest.input_sha256 or receipt.input_size != manifest.input_size):
        raise RunnerContractError('Runner result receipt bindings unavailable')
    if current:
        manifest.current()


def sign_runner_result(raw_receipt: str, admission: RunnerAdmission, *, key: bytes,
                       experiment_enabled=False) -> str:
    if experiment_enabled is not True:
        raise RunnerContractError('Runner result fixture is disabled')
    if not isinstance(raw_receipt, str) or len(raw_receipt) > PROFILE.stdout_bytes:
        raise RunnerContractError('Runner receipt wire bound unavailable')
    manifest = _context(admission, key)
    receipt = verify_runner_receipt(raw_receipt, manifest, expected_job_sha256=admission.job_sha256)
    payload = RunnerResultPayload(version=1, scope=manifest.scope, image_id=admission.image_id,
        admission_sha256=hashlib.sha256(admission.capability).hexdigest(), receipt=receipt,
        completed_at=datetime.now(timezone.utc))
    _bound(payload, admission, manifest)
    envelope = _ResultEnvelope(result=payload,
        signature=hmac.digest(key, _wire(payload), 'sha256').hex()).model_dump_json()
    if len(envelope.encode('utf-8')) > MAX_RESULT_BYTES:
        raise RunnerContractError('Runner result wire bound unavailable')
    manifest.current()
    return envelope


def verify_runner_result(raw: str, admission: RunnerAdmission, *, key: bytes) -> RunnerResultPayload:
    return _verify_result(raw, admission, key=key, current=True)


def pinned_runner_result(raw: str, admission: RunnerAdmission, *, key: bytes) -> RunnerResultPayload:
    """Authenticate historical identity only. Never permits new acceptance/run."""
    return _verify_result(raw, admission, key=key, current=False)


def _verify_result(raw, admission, *, key, current):
    manifest = _context(admission, key, current=current)
    try:
        if (not isinstance(raw, str) or not 0 < len(raw) <= MAX_RESULT_BYTES
                or len(raw.encode('utf-8')) > MAX_RESULT_BYTES):
            raise ValueError('Runner result wire bound unavailable')
        envelope = _parse(raw, _ResultEnvelope)
        if not hmac.compare_digest(hmac.digest(key, _wire(envelope.result), 'sha256').hex(),
                                   envelope.signature):
            raise ValueError('Runner result signature unavailable')
        _bound(envelope.result, admission, manifest, current=current)
        return envelope.result
    except (ValueError, TypeError, RecursionError):
        raise RunnerContractError('Runner result unavailable') from None
