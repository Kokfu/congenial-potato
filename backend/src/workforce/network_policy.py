"""Isolated Phase 7 destination checks; no product tool registration."""
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException
import ipaddress
import re
import socket
import ssl
import time
from typing import Callable, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from .local_read_experiment import (ReadDenied, ReadRequest, ReadResult,
                                    bounded_text_response)


class PublicReadGrant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str
    agent_id: str
    scheme: Literal['https'] = 'https'
    host: str = Field(min_length=1, max_length=253)
    port: Literal[443] = 443
    expires_at: datetime


@dataclass(frozen=True)
class PinnedDestination:
    host: str
    port: int
    addresses: tuple[str, ...]


Resolver = Callable[..., list[tuple]]


def _public_addresses(host: str, port: int, resolver: Resolver) -> tuple[str, ...]:
    try:
        answers = resolver(host, port, type=socket.SOCK_STREAM)
        addresses = set()
        for answer in answers:
            address = ipaddress.ip_address(answer[4][0])
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if not address.is_global:
                raise ReadDenied('Destination resolved outside public address space')
            addresses.add(str(address))
    except ReadDenied:
        raise
    except (OSError, ValueError, IndexError, KeyError) as exc:
        raise ReadDenied('Destination DNS resolution failed') from exc
    if not addresses:
        raise ReadDenied('Destination has no resolved address')
    return tuple(sorted(addresses))


def canonical_public_host(host: str) -> str:
    """Validate a stored exact destination without doing DNS or making a request."""
    if not isinstance(host, str) or host != host.lower() or len(host) > 253:
        raise ReadDenied('Destination hostname is not canonical ASCII')
    labels = host.split('.')
    if (len(labels) < 2 or not re.fullmatch(r'[a-z0-9.-]+', host) or
            any(not label or len(label) > 63 or label[0] == '-' or
                label[-1] == '-' for label in labels) or
            all(label.isdigit() for label in labels)):
        raise ReadDenied('Destination hostname is not canonical ASCII')
    return host


def canonical_public_url(value: str) -> tuple[str, int]:
    if (len(value) > 2048 or '#' in value or
            any(char.isspace() or ord(char) == 127 for char in value)
            or '\\' in value):
        raise ReadDenied('Invalid destination URL')
    try:
        url = urlsplit(value)
        port = 443 if url.port is None else url.port
        host = canonical_public_host(url.hostname)
    except (ValueError, TypeError) as exc:
        raise ReadDenied('Invalid destination URL') from exc
    if (url.scheme != 'https' or port != 443 or url.username is not None or
            url.password is not None or url.fragment or not url.path.startswith('/') or
            not url.netloc or '@' in url.netloc):
        raise ReadDenied('Destination outside exact HTTPS grant')
    return host, port


def prepare_public_destination(request: ReadRequest, grant: PublicReadGrant,
                               *, resolver: Resolver = socket.getaddrinfo) -> PinnedDestination:
    """Require an exact HTTPS grant and reject mixed public/private DNS answers."""
    if (grant.project_id != request.project_id or grant.agent_id != request.agent_id or
            grant.expires_at.tzinfo is None or
            grant.expires_at <= datetime.now(timezone.utc)):
        raise ReadDenied('Destination grant unavailable')
    host, port = canonical_public_url(request.url)
    if host != grant.host or port != grant.port:
        raise ReadDenied('Destination outside exact HTTPS grant')
    return PinnedDestination(host=host, port=port,
                             addresses=_public_addresses(host, port, resolver))


def revalidate_public_destination(request: ReadRequest, grant: PublicReadGrant,
                                  prepared: PinnedDestination, *,
                                  resolver: Resolver = socket.getaddrinfo) -> str:
    """Re-resolve immediately before effect; any changed answer fails closed."""
    current = prepare_public_destination(request, grant, resolver=resolver)
    if current != prepared:
        raise ReadDenied('Destination DNS answers changed before execution')
    return current.addresses[0]


class PinnedHTTPConnection(HTTPConnection):
    def __init__(self, host: str, port: int, pinned_ip: str, *,
                 timeout: float, socket_factory=socket.create_connection):
        super().__init__(host, port, timeout=timeout)
        self.pinned_ip = str(ipaddress.ip_address(pinned_ip))
        self.socket_factory = socket_factory

    def connect(self):
        sock = self.socket_factory((self.pinned_ip, self.port), self.timeout)
        try:
            peer = str(ipaddress.ip_address(sock.getpeername()[0]))
            if peer != self.pinned_ip:
                raise ReadDenied('Connected peer differs from pinned address')
        except Exception:
            sock.close()
            raise
        self.sock = sock


class PinnedHTTPSConnection(PinnedHTTPConnection):
    def __init__(self, host: str, port: int, pinned_ip: str, *,
                 timeout: float, context: ssl.SSLContext | None = None,
                 socket_factory=socket.create_connection):
        super().__init__(host, port, pinned_ip, timeout=timeout,
                         socket_factory=socket_factory)
        self.context = context or ssl.create_default_context()

    def connect(self):
        super().connect()
        try:
            self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


def execute_public_read_experiment(request: ReadRequest, grant: PublicReadGrant,
                                   prepared: PinnedDestination, *,
                                   experiment_enabled: bool = False,
                                   resolver: Resolver = socket.getaddrinfo,
                                   connection_factory=None) -> ReadResult:
    """Revalidate then make one pinned HTTPS GET; product registration is absent."""
    if not experiment_enabled:
        raise ReadDenied('Public read experiment is disabled')
    ip = revalidate_public_destination(request, grant, prepared,
                                       resolver=resolver)
    factory = connection_factory or PinnedHTTPSConnection
    connection = factory(prepared.host, prepared.port, ip,
                         timeout=request.timeout_seconds)
    url = urlsplit(request.url)
    path = url.path + (f'?{url.query}' if url.query else '')
    deadline = time.monotonic() + request.timeout_seconds
    try:
        connection.request('GET', path, headers={
            'Accept': 'text/plain, text/html', 'Accept-Encoding': 'identity',
            'User-Agent': 'workforce-read-experiment/1'})
        return bounded_text_response(connection.getresponse(), connection,
                                     request, deadline)
    except (OSError, HTTPException) as exc:
        raise ReadDenied('Pinned read connection failed') from exc
    finally:
        connection.close()
