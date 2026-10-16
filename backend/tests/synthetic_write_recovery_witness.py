"""In-memory protocol simulator, never a trusted or durable recovery service."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from threading import Lock
from uuid import UUID, uuid4


_DOMAIN = b'workforce.synthetic.write.recovery.witness.v1\0'


class RecoveryWitnessDenied(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryTicket:
    generation: int
    ledger_id: str
    invocation_id: str
    intent_sha256: str
    nonce: str
    signature: str


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise RecoveryWitnessDenied('Recovery witness identity unavailable') from None
    return value


def _body(generation, ledger_id, invocation_id, intent_sha256, nonce):
    return json.dumps({'generation': generation, 'ledger_id': ledger_id,
        'invocation_id': invocation_id, 'intent_sha256': intent_sha256,
        'nonce': nonce}, sort_keys=True, separators=(',', ':')).encode()


class SimulatedMonotonicRecoveryWitness:
    """Process-local stand-in used only to test a witness protocol."""
    def __init__(self, key: bytes, *, generation=1):
        if type(key) is not bytes or len(key) != 32:
            raise RecoveryWitnessDenied('Recovery witness key unavailable')
        if type(generation) is not int or not 1 <= generation < 2**63:
            raise RecoveryWitnessDenied('Recovery witness generation unavailable')
        self._key = key
        self._generation = generation
        self._available = True
        self._consumed = set()
        self._issued = {}
        self._lock = Lock()

    def _require_available(self):
        if self._available is not True:
            raise RecoveryWitnessDenied('Recovery witness unavailable')

    def set_available(self, value):
        if type(value) is not bool:
            raise RecoveryWitnessDenied('Recovery witness availability unavailable')
        with self._lock:
            self._available = value

    def advance_generation(self):
        with self._lock:
            self._require_available()
            if self._generation == 2**63-1:
                raise RecoveryWitnessDenied('Recovery witness generation exhausted')
            self._generation += 1
            return self._generation

    def issue(self, *, ledger_id, invocation_id, intent_sha256):
        ledger_id = _uuid(ledger_id)
        invocation_id = _uuid(invocation_id)
        if type(intent_sha256) is not str or re.fullmatch(r'[0-9a-f]{64}', intent_sha256) is None:
            raise RecoveryWitnessDenied('Recovery witness intent unavailable')
        with self._lock:
            self._require_available()
            if invocation_id in self._consumed:
                raise RecoveryWitnessDenied('Recovery witness invocation already consumed')
            previous = self._issued.get(invocation_id)
            if previous is not None:
                if (previous.ledger_id, previous.intent_sha256) != (ledger_id, intent_sha256):
                    raise RecoveryWitnessDenied('Recovery witness binding unavailable')
                if previous.generation == self._generation:
                    return previous
            nonce = str(uuid4())
            message = _body(self._generation, ledger_id, invocation_id, intent_sha256, nonce)
            signature = hmac.digest(self._key, _DOMAIN+message, 'sha256').hex()
            permit = RecoveryTicket(self._generation, ledger_id, invocation_id,
                intent_sha256, nonce, signature)
            self._issued[invocation_id] = permit
            return permit

    def consume(self, ticket, *, ledger_id, invocation_id, intent_sha256):
        if type(ticket) is not RecoveryTicket:
            raise RecoveryWitnessDenied('Recovery witness ticket unavailable')
        expected = (_uuid(ledger_id), _uuid(invocation_id), intent_sha256)
        with self._lock:
            self._require_available()
            if (type(ticket.generation) is not int or not 1 <= ticket.generation < 2**63 or
                    type(ticket.signature) is not str or
                    re.fullmatch(r'[0-9a-f]{64}', ticket.signature) is None):
                raise RecoveryWitnessDenied('Recovery witness ticket shape unavailable')
            _uuid(ticket.nonce)
            if (ticket.generation != self._generation or
                    (ticket.ledger_id, ticket.invocation_id, ticket.intent_sha256) != expected or
                    type(ticket.intent_sha256) is not str or
                    re.fullmatch(r'[0-9a-f]{64}', ticket.intent_sha256) is None):
                raise RecoveryWitnessDenied('Recovery witness binding unavailable')
            message = _body(ticket.generation, ticket.ledger_id, ticket.invocation_id,
                ticket.intent_sha256, ticket.nonce)
            signature = hmac.digest(self._key, _DOMAIN+message, 'sha256').hex()
            if not hmac.compare_digest(signature, ticket.signature):
                raise RecoveryWitnessDenied('Recovery witness signature unavailable')
            if ticket.invocation_id in self._consumed:
                raise RecoveryWitnessDenied('Recovery witness invocation already consumed')
            self._consumed.add(ticket.invocation_id)
            return hashlib.sha256(message).hexdigest()
