from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
from threading import Thread
import time

import pytest

from workforce.local_read_experiment import (LocalReadGrant, ReadDenied,
                                             ReadRequest, read_local_fixture)


@contextmanager
def local_server(content=b'A synthetic source claim'):
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/target')
                self.end_headers()
                return
            if self.path == '/slow':
                time.sleep(.2)
            body = content
            if self.path == '/big':
                body = b'x' * 100
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_exact_local_grant_and_bounded_provenance():
    with local_server() as (port, seen):
        grant = LocalReadGrant(project_id='project-a', agent_id='agent-a',
                               port=port, expires_at=datetime.now(timezone.utc) + timedelta(minutes=1))
        request = ReadRequest(project_id='project-a', agent_id='agent-a',
                              url=f'http://127.0.0.1:{port}/ok', max_bytes=64)
        with pytest.raises(ReadDenied, match='disabled'):
            read_local_fixture(request, grant)
        assert seen == []
        result = read_local_fixture(request, grant, test_transport_enabled=True)
        assert result.text == 'A synthetic source claim'
        assert result.size == len(result.text.encode())
        assert result.sha256 == hashlib.sha256(result.text.encode()).hexdigest()
        assert result.trust_origin == 'external_claim'
        assert result.retrieved_at.tzinfo is not None
        for changed in (
            request.model_copy(update={'project_id': 'project-b'}),
            request.model_copy(update={'agent_id': 'agent-b'}),
            request.model_copy(update={'url': f'http://localhost:{port}/ok'}),
            request.model_copy(update={'url': f'http://127.0.0.1:{port}/ok#fragment'}),
            request.model_copy(update={'url': 'http://169.254.169.254/latest/meta-data/'}),
        ):
            with pytest.raises(ReadDenied):
                read_local_fixture(changed, grant, test_transport_enabled=True)
        assert seen == ['/ok']
        expired = grant.model_copy(update={'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
        with pytest.raises(ReadDenied):
            read_local_fixture(request, expired, test_transport_enabled=True)


def test_local_fixture_rejects_redirect_size_and_deadline():
    with local_server() as (port, seen):
        grant = LocalReadGrant(project_id='p', agent_id='a', port=port,
                               expires_at=datetime.now(timezone.utc) + timedelta(minutes=1))
        def request(path, **kwargs):
            return ReadRequest(project_id='p', agent_id='a',
                               url=f'http://127.0.0.1:{port}/{path}', **kwargs)
        with pytest.raises(ReadDenied, match='302'):
            read_local_fixture(request('redirect'), grant, test_transport_enabled=True)
        assert '/target' not in seen
        with pytest.raises(ReadDenied, match='byte limit'):
            read_local_fixture(request('big', max_bytes=16), grant, test_transport_enabled=True)
        with pytest.raises(ReadDenied, match='timed out'):
            read_local_fixture(request('slow', timeout_seconds=.05), grant,
                               test_transport_enabled=True)
