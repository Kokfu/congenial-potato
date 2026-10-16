"""Durable acceptance of exact private fake-ledger receipts."""
import json
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import select

from workforce.db import session_factory
from workforce.models import (AuditEvent, SyntheticWriteAdmission,
    SyntheticWriteReceipt, ToolInvocation)
from synthetic_write_admission import SyntheticWriteAdmissionUnknown
from synthetic_write_receipt_acceptance import (SyntheticWriteReceiptDenied,
    accept_synthetic_write_receipt)
from test_synthetic_write_admission import KEY, prepared, run
from workforce.synthetic_write_contract import verify_write_receipt


def test_exact_receipt_is_persisted_once_and_replayed_as_history(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    envelope = run(invocation_id, intent, directory)
    first = accept_synthetic_write_receipt(invocation_id, intent, envelope,
        key=KEY, experiment_enabled=True)
    second = accept_synthetic_write_receipt(invocation_id, intent, envelope,
        key=KEY, experiment_enabled=True)
    assert first == second
    assert first.result_revision == 1
    with sqlite3.connect(directory/'ledger.sqlite3') as ledger_db:
        before_replay = (ledger_db.execute('SELECT revision FROM records').fetchone()[0],
            ledger_db.execute('SELECT receipt_json FROM attempts').fetchone()[0])
    assert accept_synthetic_write_receipt(invocation_id, intent, envelope,
        key=KEY, experiment_enabled=True) == first
    with sqlite3.connect(directory/'ledger.sqlite3') as ledger_db:
        assert (ledger_db.execute('SELECT revision FROM records').fetchone()[0],
            ledger_db.execute('SELECT receipt_json FROM attempts').fetchone()[0]) == before_replay
    with session_factory()() as db:
        admission = db.get(SyntheticWriteAdmission, invocation_id)
        row = db.get(SyntheticWriteReceipt, invocation_id)
        assert admission.status == 'unknown'
        assert row.receipt_sha256 == first.receipt_sha256
        assert row.receipt['event_id'] == first.event_id
        assert row.trust_origin == 'synthetic_write'
        assert db.get(ToolInvocation, invocation_id).status == 'admitted'
        assert len(db.scalars(select(AuditEvent).where(
            AuditEvent.action == 'synthetic.write.receipt')).all()) == 1
    with pytest.raises(SyntheticWriteAdmissionUnknown):
        run(invocation_id, intent, directory)


def test_bad_receipt_preserves_unknown_admission_and_allows_retained_exact_delivery(
        authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    envelope = run(invocation_id, intent, directory)
    parsed = json.loads(envelope)
    parsed['signature'] = '0' * 64
    with pytest.raises(SyntheticWriteReceiptDenied):
        accept_synthetic_write_receipt(invocation_id, intent, json.dumps(parsed),
            key=KEY, experiment_enabled=True)
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id).status == 'unknown'
        assert db.get(SyntheticWriteReceipt, invocation_id) is None
    accepted = accept_synthetic_write_receipt(invocation_id, intent, envelope,
        key=KEY, experiment_enabled=True)
    assert verify_write_receipt(envelope, intent, key=KEY).result_revision == 1
    assert accepted.result_revision == 1


def test_fresh_authority_required_for_first_acceptance(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    envelope = run(invocation_id, intent, directory)
    with session_factory()() as db:
        invocation = db.get(ToolInvocation, invocation_id)
        invocation.policy_snapshot = invocation.policy_snapshot | {'revision': -1}
        db.commit()
    with pytest.raises(SyntheticWriteReceiptDenied):
        accept_synthetic_write_receipt(invocation_id, intent, envelope,
            key=KEY, experiment_enabled=True)
    with session_factory()() as db:
        assert db.get(SyntheticWriteAdmission, invocation_id).status == 'unknown'
        assert db.get(SyntheticWriteReceipt, invocation_id) is None


def test_downgrade_refuses_to_erase_accepted_receipt_history(authenticated, tmp_path):
    invocation_id, intent, directory = prepared(authenticated, tmp_path)
    envelope = run(invocation_id, intent, directory)
    accept_synthetic_write_receipt(invocation_id, intent, envelope,
        key=KEY, experiment_enabled=True)
    result = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade',
        'c4e6a819d0b2'], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Cannot erase accepted synthetic write receipt history' in result.stderr
    with session_factory()() as db:
        assert db.get(SyntheticWriteReceipt, invocation_id) is not None
