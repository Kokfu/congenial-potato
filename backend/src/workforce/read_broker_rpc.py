"""Bounded private RPC experiment; never an HTTP proxy or product service.

The broker has only its injected key/journal/adapters, not database credentials.
Its challenge asks the trusted caller to recheck current database authority
before returning a one-second permit. The unavoidable cancellation race after
that check is handled by the mediator's post-effect checks, not a retry.
"""
from datetime import datetime, timedelta, timezone
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import socketserver
import struct
import time
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .deadline_socket import remaining
from .local_read_experiment import ReadDenied
from .read_broker_contract import (BrokerOutcomeUnknown, MAX_ENVELOPE_BYTES,
                                   _key, _unique_object, verify_ticket)
from .read_broker_result import (MAX_REPLY_BYTES, execute_authenticated_broker_read,
                                 ticket_digest, verify_broker_reply)

RPC_DEADLINE_SECONDS = 10.0
CONTROL_BYTES = 4096
PERMIT_LIFETIME = timedelta(seconds=1)
_CHALLENGE_DOMAIN = b'workforce.read.rpc.challenge.v1\0'
_PERMIT_DOMAIN = b'workforce.read.rpc.permit.v1\0'


class _Challenge(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['authorize'] = 'authorize'
    ticket_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    nonce: str = Field(pattern=r'^[0-9a-f]{64}$')


class _Permit(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['permit'] = 'permit'
    ticket_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    nonce: str = Field(pattern=r'^[0-9a-f]{64}$')
    checked_at: datetime
    expires_at: datetime

    @model_validator(mode='after')
    def lifetime(self):
        if (any(v.tzinfo is None or v.utcoffset() is None for v in (
                self.checked_at, self.expires_at)) or
                not timedelta(0) < self.expires_at-self.checked_at <= PERMIT_LIFETIME):
            raise ValueError('Broker permit lifetime unavailable')
        return self


def _canonical(message, domain):
    return domain + json.dumps(message.model_dump(mode='json'), sort_keys=True,
                              separators=(',', ':')).encode()


def _sign(message, key, domain):
    return json.dumps({'message':message.model_dump(mode='json'),
        'signature':hmac.digest(key,_canonical(message,domain),'sha256').hex()},
        separators=(',', ':'))


def _verify(value, model, key, domain):
    try:
        data = json.loads(value, object_pairs_hook=_unique_object)
        if not isinstance(data,dict) or set(data) != {'message','signature'}:
            raise ValueError('Broker control fields unavailable')
        message = model.model_validate(data['message'])
        expected = hmac.digest(key,_canonical(message,domain),'sha256').hex()
        if (not isinstance(data['signature'],str) or
                not hmac.compare_digest(expected,data['signature'])):
            raise ValueError('Broker control authentication unavailable')
        return message
    except (ValueError, TypeError, RecursionError) as exc:
        raise ReadDenied('Broker control message unavailable') from exc


def _read_exact(connection, size, deadline):
    body = bytearray()
    while len(body) < size:
        connection.settimeout(remaining(deadline))
        piece = connection.recv(size-len(body))
        if not piece:
            raise EOFError('Broker channel closed')
        body.extend(piece)
    return bytes(body)


def _read_frame(connection, limit, deadline):
    size = struct.unpack('!I',_read_exact(connection,4,deadline))[0]
    if not 0 < size <= limit:
        raise ReadDenied('Broker frame exceeds limit')
    try:
        return _read_exact(connection,size,deadline).decode('utf-8')
    except UnicodeError as exc:
        raise ReadDenied('Broker frame is not UTF-8') from exc


def _write_frame(connection, value, limit, deadline):
    body = value.encode('utf-8')
    if not 0 < len(body) <= limit:
        raise ReadDenied('Broker frame exceeds limit')
    connection.settimeout(remaining(deadline))
    connection.sendall(struct.pack('!I',len(body))+body)


def _remote_authorizer(connection, envelope, key, deadline):
    ticket = verify_ticket(envelope,key=key)
    challenge = _Challenge(ticket_hash=ticket_digest(envelope),nonce=secrets.token_hex(32))
    _write_frame(connection,_sign(challenge,key,_CHALLENGE_DOMAIN),CONTROL_BYTES,deadline)
    permit = _verify(_read_frame(connection,CONTROL_BYTES,deadline),_Permit,key,_PERMIT_DOMAIN)
    at = datetime.now(timezone.utc)
    if (permit.nonce != challenge.nonce or permit.ticket_hash != challenge.ticket_hash or
            not permit.checked_at <= at < permit.expires_at or
            permit.expires_at > ticket.expires_at):
        raise ReadDenied('Broker permit unavailable or expired')
    ticket.current()


def _private_endpoint(address, *, binding=False):
    host, port = address
    ip = ipaddress.ip_address(host)
    local = ip.is_loopback or (binding and ip.is_unspecified) or any(
        ip in ipaddress.ip_network(block) for block in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if (not local or ip.is_multicast or '%' in host or
            type(port) is not int or not (0 if binding else 1) <= port <= 65535):
        raise ReadDenied('Broker channel requires a configured private numeric endpoint')
    # This fixture server currently supports IPv4 only, with no hostname DNS.
    if ip.version != 4:
        raise ReadDenied('Broker fixture channel requires IPv4')


def make_broker_server(address, *, key: bytes, journal: Path, resolver,
        connection_factory, experiment_enabled: bool = False,
        after_fetch: Callable | None = None) -> socketserver.TCPServer:
    if not experiment_enabled or resolver is None or connection_factory is None:
        raise ReadDenied('Broker RPC experiment is disabled or uninjected')
    _key(key)
    _private_endpoint(address,binding=True)
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            deadline = time.monotonic()+RPC_DEADLINE_SECONDS
            try:
                envelope = _read_frame(self.request,MAX_ENVELOPE_BYTES,deadline)
                signed = execute_authenticated_broker_read(envelope,key=key,journal=journal,
                    resolver=resolver,connection_factory=connection_factory,
                    authorize=lambda value: _remote_authorizer(self.request,value,key,deadline),
                    experiment_enabled=True,after_fetch=after_fetch)
                _write_frame(self.request,signed,MAX_REPLY_BYTES,deadline)
            except (ReadDenied, OSError, EOFError):
                # No response bodies, tickets, keys or exception details in logs.
                # Closing the channel leaves the caller's attempt unconfirmed.
                return
    class Server(socketserver.TCPServer):
        allow_reuse_address = True
        # One active connection; fixed backlog and deadline bound idle clients.
        request_queue_size = 4
        def handle_error(self, request, client_address):
            pass  # unexpected failures also close; no payload-bearing traceback
    return Server(address,Handler)


def broker_exchange(address, envelope: str, *, key: bytes,
        authorize: Callable[[str], None], experiment_enabled: bool = False) -> str:
    if not experiment_enabled or not callable(authorize):
        raise ReadDenied('Broker RPC experiment is disabled or uninjected')
    _private_endpoint(address)
    ticket = verify_ticket(envelope,key=key)
    deadline = time.monotonic()+min(RPC_DEADLINE_SECONDS,
        (ticket.expires_at-datetime.now(timezone.utc)).total_seconds())
    try:
        with socket.create_connection(address,timeout=remaining(deadline)) as connection:
            _write_frame(connection,envelope,MAX_ENVELOPE_BYTES,deadline)
            challenge = _verify(_read_frame(connection,CONTROL_BYTES,deadline),
                                _Challenge,key,_CHALLENGE_DOMAIN)
            if challenge.ticket_hash != ticket_digest(envelope):
                raise ReadDenied('Broker challenge does not match issued ticket')
            authorize(envelope)  # fresh database checks, no locks held during fetch
            at = datetime.now(timezone.utc)
            permit = _Permit(ticket_hash=challenge.ticket_hash,nonce=challenge.nonce,
                             checked_at=at,expires_at=min(at+PERMIT_LIFETIME,ticket.expires_at))
            _write_frame(connection,_sign(permit,key,_PERMIT_DOMAIN),CONTROL_BYTES,deadline)
            signed = _read_frame(connection,MAX_REPLY_BYTES,deadline)
            verify_broker_reply(signed,envelope,key=key)
            return signed
    except (OSError, EOFError) as exc:
        raise BrokerOutcomeUnknown('Broker reply unconfirmed; no retry') from exc
