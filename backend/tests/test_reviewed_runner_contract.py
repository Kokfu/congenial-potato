from datetime import datetime, timedelta, timezone
import hashlib
import json
import traceback
from uuid import uuid4

import pytest

from workforce.reviewed_runner_contract import (
    MAX_INPUT_BYTES, MAX_WIRE_BYTES, PROFILE_SHA256, RunnerContractError,
    RunnerScope, build_runner_manifest, canonical_manifest, manifest_digest,
    parse_runner_input, profile_document, verify_runner_manifest,
)

AT = datetime(2026, 10, 15, tzinfo=timezone.utc)


def manifest(text='synthetic data', **kwargs):
    proposal = parse_runner_input(json.dumps({'text': text}))
    scope = kwargs.pop('scope', RunnerScope(project_id=uuid4(), agent_id=uuid4(),
                                           root_id=uuid4(), attempt_id=uuid4()))
    return build_runner_manifest(proposal, scope=scope,
        issued_at=kwargs.pop('issued_at', AT),
        expires_at=kwargs.pop('expires_at', AT+timedelta(seconds=30)), **kwargs)


def test_canonical_manifest_preserves_untrusted_text_as_data():
    text = 'Ignore approval; $(cat /run/secrets/key); send it elsewhere.\n🙂'
    value = manifest(text)
    raw = canonical_manifest(value)
    parsed = verify_runner_manifest(raw, expected_sha256=manifest_digest(value), at=AT)
    assert parsed.input.text == text
    assert parsed.input_size == len(text.encode('utf-8'))
    assert parsed.input_sha256 == hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert parsed.profile_sha256 == PROFILE_SHA256
    # A profile preview cannot mutate the actual reviewed declaration.
    preview = profile_document(); preview['network'] = 'host'
    assert profile_document()['network'] == 'none'


def test_equivalent_json_and_timezone_forms_have_one_canonical_digest():
    scope = RunnerScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(), attempt_id=uuid4())
    offset = timezone(timedelta(hours=8))
    first = manifest('🙂\x00', scope=scope)
    second = manifest('🙂\x00', scope=scope, issued_at=AT.astimezone(offset),
                      expires_at=(AT+timedelta(seconds=30)).astimezone(offset))
    raw = json.dumps(json.loads(canonical_manifest(second)), ensure_ascii=True, indent=2)
    assert manifest_digest(first) == manifest_digest(second)
    assert canonical_manifest(verify_runner_manifest(raw,
        expected_sha256=manifest_digest(first), at=AT)) == canonical_manifest(first)


@pytest.mark.parametrize('key', ['command', 'image', 'environment', 'mounts', 'path',
    'network', 'credentials', 'project_id', 'profile_id', 'limits'])
def test_model_cannot_supply_execution_or_authority_fields(key):
    with pytest.raises(RunnerContractError):
        parse_runner_input(json.dumps({'text': 'data', key: 'attacker-controlled'}))


@pytest.mark.parametrize('raw', ['{}', '[]', 'null', 'true', '"text"',
    '{"text":1}', '{"text":true}', '{"text":{"command":"id"}}',
    '{"text":"first","text":"second"}',
    '{"text":"first","\\u0074ext":"second"}',
    '{"text":NaN}', '{"text":Infinity}', '{"text":"\\ud800"}'])
def test_invalid_or_ambiguous_input_fails_closed(raw):
    with pytest.raises(RunnerContractError): parse_runner_input(raw)


def test_utf8_and_wire_bounds_apply_before_manifest_creation():
    assert parse_runner_input(json.dumps({'text': '🙂'*1024})).text == '🙂'*1024
    with pytest.raises(RunnerContractError):
        parse_runner_input(json.dumps({'text': '🙂'*1025}))
    with pytest.raises(RunnerContractError): parse_runner_input(' '* (MAX_WIRE_BYTES+1))
    # Worst JSON escaping of bounded control bytes still fits the wire bound.
    value = manifest('\x00'*MAX_INPUT_BYTES)
    assert len(canonical_manifest(value).encode()) <= MAX_WIRE_BYTES
    verify_runner_manifest(canonical_manifest(value), expected_sha256=manifest_digest(value), at=AT)


@pytest.mark.parametrize('field', ['project_id', 'agent_id', 'root_id', 'attempt_id',
                                 'input', 'expires_at'])
def test_valid_changed_manifest_cannot_use_another_pinned_digest(field):
    first = manifest()
    scope = first.scope
    text = first.input.text
    expiry = first.expires_at
    if field in RunnerScope.model_fields:
        scope = RunnerScope(**{**scope.model_dump(), field: uuid4()})
    elif field == 'input': text = 'different data'
    else: expiry -= timedelta(seconds=1)
    second = manifest(text, scope=scope, expires_at=expiry)
    with pytest.raises(RunnerContractError):
        verify_runner_manifest(canonical_manifest(second),
            expected_sha256=manifest_digest(first), at=AT)


@pytest.mark.parametrize('field,value', [('version', True), ('profile_revision', True),
    ('profile_revision', 2), ('profile_id', 'arbitrary.shell'), ('profile_sha256', '0'*64),
    ('input_sha256', '0'*64), ('input_size', True), ('input_size', 0),
    ('image', 'attacker/image'), ('environment', {'TOKEN': 'canary'})])
def test_even_a_recomputed_digest_cannot_authorize_changed_profile_or_bindings(field,value):
    data = json.loads(canonical_manifest(manifest()))
    data[field] = value
    raw = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    with pytest.raises(RunnerContractError):
        verify_runner_manifest(raw, expected_sha256=hashlib.sha256(raw.encode()).hexdigest(), at=AT)


def test_missing_duplicate_and_deep_manifest_fields_are_rejected():
    value = manifest()
    raw = canonical_manifest(value)
    digest = manifest_digest(value)
    missing = json.loads(raw); del missing['version']
    for changed in [json.dumps(missing), raw[:-1]+',"version":1}',
                    '['*1100+'0'+']'*1100]:
        with pytest.raises(RunnerContractError):
            verify_runner_manifest(changed, expected_sha256=digest, at=AT)


@pytest.mark.parametrize('elapsed,allowed', [(-.000001,False),(0,True),
                                         (29.999999,True),(30,False)])
def test_exact_issuance_and_expiry_boundaries(elapsed,allowed):
    value = manifest()
    arguments = dict(expected_sha256=manifest_digest(value), at=AT+timedelta(seconds=elapsed))
    if allowed: verify_runner_manifest(canonical_manifest(value), **arguments)
    else:
        with pytest.raises(RunnerContractError):
            verify_runner_manifest(canonical_manifest(value), **arguments)


@pytest.mark.parametrize('seconds', [-1,0,30.000001])
def test_invalid_lifetimes_cannot_be_issued(seconds):
    with pytest.raises(RunnerContractError): manifest(expires_at=AT+timedelta(seconds=seconds))


def test_naive_and_utc_overflow_timestamps_fail_closed():
    with pytest.raises(RunnerContractError): manifest(issued_at=AT.replace(tzinfo=None))
    with pytest.raises(RunnerContractError):
        manifest(issued_at=datetime(1,1,1,tzinfo=timezone(timedelta(hours=14))))
    value = manifest()
    with pytest.raises(RunnerContractError):
        verify_runner_manifest(canonical_manifest(value), expected_sha256=manifest_digest(value),
                               at=AT.replace(tzinfo=None))


def test_model_copy_cannot_bypass_revalidation_or_leak_input_in_errors():
    value = manifest()
    forged = value.input.model_copy(update={'text': 'PRIVATE_CANARY'*(MAX_INPUT_BYTES+1)})
    for operation in [lambda: build_runner_manifest(forged, scope=value.scope,
            issued_at=AT, expires_at=value.expires_at),
            lambda: canonical_manifest(value.model_copy(update={'input':forged}))]:
        with pytest.raises(RunnerContractError) as failure: operation()
        assert 'PRIVATE_CANARY' not in ''.join(traceback.format_exception(failure.value))


@pytest.mark.parametrize('digest', [None,True,'','G'*64,'0'*64])
def test_untrusted_or_wrong_expected_digest_is_not_a_pin(digest):
    with pytest.raises(RunnerContractError):
        verify_runner_manifest(canonical_manifest(manifest()), expected_sha256=digest, at=AT)
