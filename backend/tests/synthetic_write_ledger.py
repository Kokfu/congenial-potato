"""Trusted test-only local fake external ledger. Never imported by product code.

Its fence is independent of application DB state, but establishes no approval or
current authority. SQLite/process-exit evidence is not stale-restore acceptance.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from uuid import UUID, uuid4

from workforce.synthetic_write_contract import (AppliedWriteReceipt, SyntheticWriteIntent,
    WriteContractError, intent_digest, parse_reconciliation_query, parse_write_intent,
    sign_reconciliation_result, sign_write_receipt)


class WriteAttemptConsumed(WriteContractError):
    pass


class WriteOutcomeUnknown(WriteAttemptConsumed):
    pass


class SyntheticWriteLedger:
    def __init__(self, directory, *, ledger_id: UUID, key: bytes, experiment_enabled=False):
        if experiment_enabled is not True:
            raise WriteContractError('Synthetic ledger disabled')
        if type(ledger_id) is not UUID or type(key) is not bytes or len(key) != 32:
            raise WriteContractError('Synthetic ledger configuration unavailable')
        directory = Path(directory)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) != 0o700):
            raise WriteContractError('Private fixture directory required')
        self.path = directory/'ledger.sqlite3'
        self.ledger_id, self.key = ledger_id, key
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                    stat.S_IMODE(info.st_mode) != 0o600):
                raise WriteContractError('Private fixture ledger required') from None
            with self._db() as db:
                row = db.execute('SELECT ledger_id FROM metadata').fetchone()
                if row is None or row[0] != str(ledger_id):
                    raise WriteContractError('Fixture ledger identity unavailable')
        else:
            os.close(fd)
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE metadata (ledger_id TEXT PRIMARY KEY)')
                db.execute('INSERT INTO metadata VALUES (?)', (str(ledger_id),))
                db.execute('''CREATE TABLE attempts (invocation_id TEXT PRIMARY KEY,
                    intent_sha256 TEXT NOT NULL, intent_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('unknown','applied','not_applied')),
                    receipt_json TEXT, CHECK((status='applied')=(receipt_json IS NOT NULL)))''')
                db.execute('''CREATE TABLE records (record_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL, revision INTEGER NOT NULL, content BLOB NOT NULL)''')
                db.commit()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def _intent(self, intent):
        if type(intent) is not SyntheticWriteIntent:
            raise WriteContractError('Exact synthetic intent required')
        intent_digest(intent)  # revalidate even copied model instances
        if intent.ledger_id != self.ledger_id:
            raise WriteContractError('Wrong fixture ledger')
        return intent

    def _attempt(self, db, intent):
        row = db.execute('SELECT * FROM attempts WHERE invocation_id=?',
            (str(intent.scope.invocation_id),)).fetchone()
        if row is not None and (row['intent_sha256'] != intent_digest(intent) or
                parse_write_intent(row['intent_json']) != intent):
            raise WriteContractError('Consumed fixture identity changed')
        return row

    def _receipt(self, row, intent):
        return sign_write_receipt(row['receipt_json'], intent, key=self.key, experiment_enabled=True)

    def apply(self, intent, content: bytes, *, after_fence=None, before_effect_commit=None,
              after_effect_commit=None):
        intent = self._intent(intent)
        if (type(content) is not bytes or len(content) != intent.content_size or
                hashlib.sha256(content).hexdigest() != intent.content_sha256):
            raise WriteContractError('Synthetic content binding unavailable')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = self._attempt(db, intent)
            if previous is not None:
                if previous['status'] == 'applied':
                    return self._receipt(previous, intent)
                if previous['status'] == 'unknown':
                    raise WriteOutcomeUnknown('Consumed fixture outcome unknown; no reexecution')
                raise WriteAttemptConsumed('Consumed fixture precondition failure; no reexecution')
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,NULL)',
                (str(intent.scope.invocation_id), intent_digest(intent), intent.model_dump_json(), 'unknown'))
            db.commit()  # consumes invocation before any synthetic record mutation
        if after_fence:
            after_fence()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._attempt(db, intent)
            if row is None or row['status'] != 'unknown':
                raise WriteOutcomeUnknown('Fixture fence unavailable')
            record = db.execute('SELECT * FROM records WHERE record_id=?',
                (str(intent.record_id),)).fetchone()
            if ((record is None and intent.expected_revision != 0) or
                    (record is not None and (record['project_id'] != str(intent.scope.project_id) or
                        record['revision'] != intent.expected_revision))):
                db.execute("UPDATE attempts SET status='not_applied' WHERE invocation_id=?",
                    (str(intent.scope.invocation_id),))
                db.commit()
                raise WriteAttemptConsumed('Synthetic precondition failed; no automatic retry')
            receipt = AppliedWriteReceipt(version=1, trust_origin='synthetic_write',
                intent_sha256=intent_digest(intent), event_id=uuid4(), applied_at=datetime.now(timezone.utc),
                result_revision=intent.expected_revision+1, content_sha256=intent.content_sha256,
                content_size=intent.content_size)
            raw = receipt.model_dump_json()
            signed = sign_write_receipt(raw, intent, key=self.key, experiment_enabled=True)
            db.execute('INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET '
                'revision=excluded.revision, content=excluded.content',
                (str(intent.record_id), str(intent.scope.project_id), receipt.result_revision, content))
            db.execute("UPDATE attempts SET status='applied', receipt_json=? WHERE invocation_id=?",
                (raw, str(intent.scope.invocation_id)))
            if before_effect_commit:
                before_effect_commit()
            db.commit()
        if after_effect_commit:
            after_effect_commit()
        return signed

    def reconcile(self, intent, raw_query):
        intent = self._intent(intent)
        query = parse_reconciliation_query(raw_query, intent)
        with self._db() as db:
            row = self._attempt(db, intent)
            status = row['status'] if row is not None else 'not_applied'
            receipt = json.loads(row['receipt_json']) if row is not None and status == 'applied' else None
        result = {'version': 1, 'trust_origin': 'synthetic_write',
            'query': query.model_dump(mode='json'), 'outcome': status,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'receipt': receipt}
        return sign_reconciliation_result(json.dumps(result), query, intent,
            key=self.key, experiment_enabled=True)
