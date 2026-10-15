from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from threading import Event
from uuid import uuid4

import pytest

from workforce.reviewed_runner_contract import (RunnerContractError, RunnerInput, RunnerScope,
    build_runner_manifest, canonical_manifest, manifest_digest)
from workforce.runner_admission import RunnerAdmission
from workforce.runner_fixture_job import execute_fixture_job, canonical_receipt, job_code_digest
from workforce.runner_result_contract import sign_runner_result, verify_runner_result

KEY = b'k'*32


def fixture_result():
    issued = datetime.now(timezone.utc)
    scope = RunnerScope(project_id=uuid4(), agent_id=uuid4(), root_id=uuid4(), attempt_id=uuid4())
    manifest = build_runner_manifest(RunnerInput(text='Synthetic 🥔 untrusted input'), scope=scope,
        issued_at=issued, expires_at=issued+timedelta(seconds=30))
    admission = RunnerAdmission(str(scope.attempt_id), canonical_manifest(manifest), manifest_digest(manifest),
        'sha256:'+'a'*64, job_code_digest(), b'c'*32)
    receipt = execute_fixture_job(admission.manifest_raw,
        expected_manifest_sha256=admission.manifest_sha256, expected_job_sha256=admission.job_sha256)
    raw = canonical_receipt(receipt)
    signed = sign_runner_result(raw, admission, key=KEY, experiment_enabled=True)
    return admission, raw, signed


def test_exact_private_result_metadata_binds_manifest_scope_image_and_input():
    admission, raw, signed = fixture_result()
    payload = verify_runner_result(signed, admission, key=KEY)
    assert canonical_receipt(payload.receipt) == raw
    assert str(payload.scope.attempt_id) == admission.invocation_id
    assert payload.image_id == admission.image_id
    assert payload.admission_sha256 == hashlib.sha256(admission.capability).hexdigest()
    assert 'untrusted input' not in signed and admission.capability.hex() not in signed
    assert KEY.hex() not in signed


def resign(document, domain=b'workforce.runner.result.v1\0'):
    document['signature'] = hmac.digest(KEY, domain+json.dumps(document['result'],
        sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(), 'sha256').hex()
    return json.dumps(document)


@pytest.mark.parametrize('field,value', [
    ('image_id', 'sha256:'+'b'*64), ('admission_sha256', 'b'*64),
    ('completed_at', '2000-01-01T00:00:00Z'), ('completed_at', '2999-01-01T00:00:00Z'),
    ('version', True), ('version', 2), ('command', 'sh'),
])
@pytest.mark.parametrize('with_valid_signature', [False, True])
def test_altered_headers_denied_even_with_valid_mac(field, value, with_valid_signature):
    admission, _, signed = fixture_result()
    document = json.loads(signed)
    document['result'][field] = value
    altered = resign(document) if with_valid_signature else json.dumps(document)
    with pytest.raises(RunnerContractError):
        verify_runner_result(altered, admission, key=KEY)


@pytest.mark.parametrize('field', ['project_id', 'agent_id', 'root_id', 'attempt_id'])
def test_resigned_scope_substitution_denied(field):
    admission, _, signed = fixture_result()
    document = json.loads(signed)
    document['result']['scope'][field] = str(uuid4())
    with pytest.raises(RunnerContractError):
        verify_runner_result(resign(document), admission, key=KEY)


@pytest.mark.parametrize('field,value', [
    ('manifest_sha256', 'b'*64), ('profile_sha256', 'b'*64),
    ('job_sha256', 'b'*64), ('input_sha256', 'b'*64), ('input_size', 0),
    ('input_size', True), ('input_size', 4097), ('version', True), ('output', 'claims'),
])
def test_resigned_receipt_changes_denied(field, value):
    admission, _, signed = fixture_result()
    document = json.loads(signed)
    document['result']['receipt'][field] = value
    with pytest.raises(RunnerContractError):
        verify_runner_result(resign(document), admission, key=KEY)


@pytest.mark.parametrize('key', [b'x'*32, b'k'*31, 'k'*32, b'c'*32, None])
def test_wrong_weak_or_reused_private_keys_denied(key):
    admission, _, signed = fixture_result()
    with pytest.raises(RunnerContractError):
        verify_runner_result(signed, admission, key=key)


@pytest.mark.parametrize('enabled', [False, None, 1, 'true'])
def test_signer_is_explicitly_disabled_by_default(enabled):
    admission, raw, _ = fixture_result()
    with pytest.raises(RunnerContractError):
        sign_runner_result(raw, admission, key=KEY, experiment_enabled=enabled)


@pytest.mark.parametrize('change', [
    {'image_id': 'sha256:'+'b'*64}, {'job_sha256': 'b'*64}, {'manifest_sha256': 'b'*64},
    {'capability': b'd'*32}, {'invocation_id': str(uuid4())}, {'image_id': 'latest'},
])
def test_envelope_cannot_transfer_to_changed_admission(change):
    admission, _, signed = fixture_result()
    with pytest.raises(RunnerContractError):
        verify_runner_result(signed, replace(admission, **change), key=KEY)


def test_unsigned_ambiguous_oversized_and_cross_domain_documents_denied():
    admission, raw, signed = fixture_result()
    document = json.loads(signed)
    invalid = [raw, '{}', signed[:-1], ' '*8193, signed.encode(),
        signed.replace('"signature":', '"signature":"'+'a'*64+'","signature":', 1),
        signed.replace('"version":1', '"version":1,"version":1', 1),
        signed.replace('"version":1', '"version":NaN', 1),
        resign(document, b'workforce.read.result.v1\0')]
    for candidate in invalid:
        with pytest.raises(RunnerContractError):
            verify_runner_result(candidate, admission, key=KEY)


def test_signed_result_is_not_fresh_after_manifest_expiry():
    admission, raw, _ = fixture_result()
    # Build a genuine near-term manifest, sign it while current, then let actual
    # host time pass. This tests expiry without weakening the verifier clock.
    from workforce.reviewed_runner_contract import pinned_runner_manifest
    original = pinned_runner_manifest(admission.manifest_raw, expected_sha256=admission.manifest_sha256)
    issued = datetime.now(timezone.utc)
    manifest = build_runner_manifest(original.input, scope=original.scope,
        issued_at=issued, expires_at=issued+timedelta(seconds=1))
    admission = replace(admission, manifest_raw=canonical_manifest(manifest), manifest_sha256=manifest_digest(manifest))
    receipt = execute_fixture_job(admission.manifest_raw,
        expected_manifest_sha256=admission.manifest_sha256, expected_job_sha256=admission.job_sha256)
    signed = sign_runner_result(canonical_receipt(receipt), admission, key=KEY, experiment_enabled=True)
    Event().wait(1.05)
    with pytest.raises(RunnerContractError):
        verify_runner_result(signed, admission, key=KEY)


@pytest.mark.skipif(os.environ.get('WORKFORCE_DOCKER_GATE') != '1',
                    reason='explicit Docker fixture gate')
def test_private_host_signs_only_after_the_admitted_isolated_job(authenticated, tmp_path):
    import secrets
    from sqlalchemy import select
    from workforce.db import session_factory
    from workforce.models import RunnerAttempt, ToolInvocation
    from runner_isolation_harness import docker, details
    from runner_admission_harness import run_admitted_job
    from test_runner_admission import approved
    image_id = docker('image', 'inspect', '--format', '{{.Id}}', 'workforce-backend:phase1')
    invocation_id = approved(authenticated, image_id=image_id)[4]
    journal = tmp_path/'journal'
    journal.mkdir(mode=0o700)
    key = secrets.token_bytes(32)
    def private(container):
        info = details(container)
        assert key.hex() not in json.dumps(info['Config'])
        assert info['Mounts'] == []
    admission, envelope = run_admitted_job(invocation_id, journal=journal,
        experiment_enabled=True, result_key=key, after_create=private)
    payload = verify_runner_result(envelope, admission, key=key)
    assert str(payload.scope.attempt_id) == invocation_id
    assert key.hex() not in envelope
    with session_factory()() as db:
        assert db.get(RunnerAttempt, invocation_id).status == 'unknown'
        assert db.get(ToolInvocation, invocation_id).status == 'approved_staged'
    assert docker('ps', '--all', '-q', '--filter',
        'label=workforce.runner.attempt='+invocation_id.replace('-', '')) == ''


@pytest.mark.parametrize('raw', ['x'*1025, b'{}', None])
def test_signer_refuses_unbounded_or_untyped_receipt(raw):
    admission, _, _ = fixture_result()
    with pytest.raises(RunnerContractError):
        sign_runner_result(raw, admission, key=KEY, experiment_enabled=True)
