"""Isolated Phase 7 read fixture; no API, worker or tool registration."""
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection, HTTPException
import socket
import time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


class ReadDenied(ValueError):
    pass


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(min_length=1, max_length=36)
    agent_id: str = Field(min_length=1, max_length=36)
    url: str = Field(min_length=1, max_length=2048)
    max_bytes: int = Field(default=65536, ge=1, le=65536)
    timeout_seconds: float = Field(default=3, gt=0, le=5)


class LocalReadGrant(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str
    agent_id: str
    port: int = Field(ge=1, le=65535)
    expires_at: datetime


class ReadResult(BaseModel):
    url: str
    retrieved_at: datetime
    media_type: str
    size: int
    sha256: str
    text: str
    trust_origin: str = 'external_claim'


def bounded_text_response(response, connection, request: ReadRequest,
                          deadline: float) -> ReadResult:
    """Validate a single response without following links or decoding compression."""
    if response.status != 200:
        raise ReadDenied(f'Fixture returned HTTP {response.status}')
    media_type = response.getheader('Content-Type', '').split(';', 1)[0].lower()
    if media_type not in ('text/plain', 'text/html'):
        raise ReadDenied('Fixture media type is unavailable')
    if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
        raise ReadDenied('Compressed fixture responses are unavailable')
    length = response.getheader('Content-Length')
    if length is not None and (not length.isdecimal() or int(length) > request.max_bytes):
        raise ReadDenied('Fixture response exceeds byte limit')
    chunks: list[bytes] = []
    size = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReadDenied('Fixture deadline exceeded')
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        chunk = response.read(min(8192, request.max_bytes + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > request.max_bytes:
            raise ReadDenied('Fixture response exceeds byte limit')
        chunks.append(chunk)
    body = b''.join(chunks)
    try:
        content = body.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ReadDenied('Fixture text is not UTF-8') from exc
    return ReadResult(url=request.url, retrieved_at=datetime.now(timezone.utc),
                      media_type=media_type, size=size,
                      sha256=hashlib.sha256(body).hexdigest(), text=content)


def read_local_fixture(request: ReadRequest, grant: LocalReadGrant,
                       *, test_transport_enabled: bool = False) -> ReadResult:
    """Make one bounded loopback GET only when a test harness opts in."""
    if not test_transport_enabled:
        raise ReadDenied('Local fixture transport is disabled')
    if (grant.project_id != request.project_id or grant.agent_id != request.agent_id or
            grant.expires_at.tzinfo is None or
            grant.expires_at <= datetime.now(timezone.utc)):
        raise ReadDenied('Destination grant unavailable')
    try:
        url = urlsplit(request.url)
        port = url.port
    except ValueError as exc:
        raise ReadDenied('Invalid destination URL') from exc
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or
            port != grant.port or url.username is not None or
            url.password is not None or url.fragment or not url.path.startswith('/')):
        raise ReadDenied('Destination outside exact local fixture grant')
    deadline = time.monotonic() + request.timeout_seconds
    path = url.path + (f'?{url.query}' if url.query else '')
    connection = HTTPConnection('127.0.0.1', grant.port,
                                timeout=request.timeout_seconds)
    try:
        connection.request('GET', path, headers={
            'Accept': 'text/plain, text/html', 'Accept-Encoding': 'identity',
            'User-Agent': 'workforce-local-read-fixture/1'})
        response = connection.getresponse()
        return bounded_text_response(response, connection, request, deadline)
    except (OSError, HTTPException, socket.timeout) as exc:
        raise ReadDenied('Fixture connection failed or timed out') from exc
    finally:
        connection.close()
