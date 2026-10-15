"""Inert Phase 8 fixture manifest. No launch, authority or product dispatch.

The fixed profile is a declaration, not an executable image/command. A later
isolated executor must bind reviewed code/image and fresh database authority.
A digest pins canonical data; it is neither a signature nor an approval.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_INPUT_BYTES = 4096
MAX_WIRE_BYTES = 32768
MAX_MANIFEST_LIFETIME = timedelta(seconds=30)


class RunnerContractError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewedProfile:
    profile_id: str = 'synthetic.text-digest'
    revision: int = 1
    job: str = 'sha256-and-utf8-size'
    input_trust: str = 'untrusted_data'
    uid: int = 10001
    gid: int = 10001
    read_only: bool = True
    network: str = 'none'
    dropped_capabilities: tuple[str, ...] = ('ALL',)
    no_new_privileges: bool = True
    cpu_count: int = 1
    memory_bytes: int = 134217728
    pid_limit: int = 32
    wall_seconds: int = 2
    input_bytes: int = MAX_INPUT_BYTES
    stdout_bytes: int = 1024
    stderr_bytes: int = 1024
    host_mounts: bool = False
    credential_access: bool = False


PROFILE = ReviewedProfile()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False)


def profile_document() -> dict:
    """Fresh preview of the one reviewed declaration; never accepts a profile."""
    return asdict(PROFILE)


PROFILE_SHA256 = hashlib.sha256(_canonical(profile_document()).encode()).hexdigest()


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True,
                             revalidate_instances='always', hide_input_in_errors=True)


class RunnerInput(_StrictModel):
    text: str = Field(max_length=MAX_INPUT_BYTES)

    @field_validator('text')
    @classmethod
    def bounded_text(cls, value):
        if len(value.encode('utf-8')) > MAX_INPUT_BYTES:
            raise ValueError('Runner input exceeds UTF-8 bound')
        return value


class RunnerScope(_StrictModel):
    project_id: UUID
    agent_id: UUID
    root_id: UUID
    attempt_id: UUID


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RunnerContractError('Runner timestamp must be timezone-aware')
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise RunnerContractError('Runner timestamp unavailable') from None


class RunnerManifest(_StrictModel):
    version: Literal[1]
    profile_id: Literal['synthetic.text-digest']
    profile_revision: Literal[1]
    profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    scope: RunnerScope
    input: RunnerInput
    input_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_size: int = Field(ge=0, le=MAX_INPUT_BYTES)
    issued_at: datetime
    expires_at: datetime

    @field_validator('version', 'profile_revision', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Runner version must be an integer')
        return value

    @field_validator('issued_at', 'expires_at')
    @classmethod
    def aware_timestamp(cls, value):
        return _utc(value)

    @model_validator(mode='after')
    def bindings(self):
        body = self.input.text.encode('utf-8')
        if (self.profile_sha256 != PROFILE_SHA256 or self.input_size != len(body)
                or self.input_sha256 != hashlib.sha256(body).hexdigest()
                or not timedelta(0) < self.expires_at-self.issued_at <= MAX_MANIFEST_LIFETIME):
            raise ValueError('Runner manifest bindings unavailable')
        return self

    def current(self, at: datetime | None = None) -> None:
        if not self.issued_at <= _utc(at if at is not None else datetime.now(timezone.utc)) < self.expires_at:
            raise RunnerContractError('Runner manifest is not current')


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate runner JSON field')
        value[key] = item
    return value


def _constant(_):
    raise ValueError('Non-finite runner JSON value')


def _parse(raw, model):
    try:
        if not isinstance(raw, str) or not 0 < len(raw.encode('utf-8')) <= MAX_WIRE_BYTES:
            raise ValueError('Runner wire bound unavailable')
        json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
        # Strict JSON validation permits UUID/date representations, while strict
        # Python validation still refuses arbitrary objects/coerced primitives.
        return model.model_validate_json(raw)
    except (ValueError, TypeError, RecursionError):
        raise RunnerContractError('Runner document unavailable') from None


def parse_runner_input(raw: str) -> RunnerInput:
    return _parse(raw, RunnerInput)


def build_runner_manifest(proposal: RunnerInput, *, scope: RunnerScope,
        issued_at: datetime, expires_at: datetime) -> RunnerManifest:
    try:
        proposal = RunnerInput.model_validate(proposal)
        scope = RunnerScope.model_validate(scope)
        body = proposal.text.encode('utf-8')
        return RunnerManifest(version=1, profile_id=PROFILE.profile_id, profile_revision=1,
            profile_sha256=PROFILE_SHA256, scope=scope, input=proposal,
            input_sha256=hashlib.sha256(body).hexdigest(), input_size=len(body),
            issued_at=issued_at, expires_at=expires_at)
    except (ValueError, TypeError):
        raise RunnerContractError('Runner manifest unavailable') from None


def canonical_manifest(manifest: RunnerManifest) -> str:
    try:
        value = _canonical(RunnerManifest.model_validate(manifest).model_dump(mode='json'))
        if len(value.encode('utf-8')) > MAX_WIRE_BYTES:
            raise ValueError('Runner wire bound unavailable')
        return value
    except (ValueError, TypeError):
        raise RunnerContractError('Runner manifest unavailable') from None


def manifest_digest(manifest: RunnerManifest) -> str:
    return hashlib.sha256(canonical_manifest(manifest).encode('utf-8')).hexdigest()


def pinned_runner_manifest(raw: str, *, expected_sha256: str) -> RunnerManifest:
    """Inspect exact identity only, including historical attempts. No permission."""
    manifest = _parse(raw, RunnerManifest)
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in '0123456789abcdef' for c in expected_sha256)
            or not hmac.compare_digest(manifest_digest(manifest), expected_sha256)):
        raise RunnerContractError('Runner manifest digest unavailable')
    return manifest


def verify_runner_manifest(raw: str, *, expected_sha256: str,
                           at: datetime | None = None) -> RunnerManifest:
    manifest = pinned_runner_manifest(raw, expected_sha256=expected_sha256)
    manifest.current(at)
    return manifest
