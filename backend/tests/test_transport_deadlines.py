from contextlib import contextmanager
import ipaddress
import socket
import socketserver
import ssl
import subprocess
from threading import Event, Thread
import time

import pytest

from workforce import bounded_resolver
from workforce.bounded_resolver import resolve_with_deadline
from workforce.local_read_experiment import ReadDenied
from workforce.network_policy import (PinnedHTTPConnection, PinnedHTTPSConnection,
    execute_public_read_experiment, prepare_public_destination)
from test_network_policy import answers, fixture


@contextmanager
def server(handler):
    stopped = Event()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                handler(self.request, stopped)
            except OSError:
                pass  # expected client aborts and certificate/deadline failures
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    instance = Server(('127.0.0.1', 0), Handler)
    thread = Thread(target=instance.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield instance.server_address[1]
    finally:
        stopped.set()
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def read_headers(sock):
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def test_os_resolver_executes_locally_with_bounded_answers():
    rows = resolve_with_deadline('localhost', 443, timeout_seconds=2)
    assert rows and all(ipaddress.ip_address(row[4][0]).is_loopback for row in rows)
    assert all(row[4][1] == 443 and row[1] == socket.SOCK_STREAM for row in rows)


def test_stalled_resolver_is_killed_and_reaped_before_transport(monkeypatch):
    launched = []
    original = subprocess.Popen
    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        launched.append(process)
        return process
    monkeypatch.setattr(bounded_resolver.subprocess, 'Popen', capture)
    # Simulates a wedged OS resolver inside the real interpreter lifecycle.
    monkeypatch.setattr(bounded_resolver, '_RESOLVE_PROGRAM', 'import time; time.sleep(60)')
    request, grant = fixture()
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    request = request.model_copy(update={'timeout_seconds': .15})
    created = []
    start = time.monotonic()
    with pytest.raises(ReadDenied, match='deadline'):
        execute_public_read_experiment(request, grant, prepared, experiment_enabled=True,
            connection_factory=lambda *a, **kw: created.append(True))
    assert time.monotonic() - start < 1
    assert not created and len(launched) == 1
    assert launched[0].poll() is not None and launched[0].returncode != 0


def test_child_watchdog_exits_without_parent_timeout_enforcement():
    import signal
    import sys
    # No parent-side kill: the same child prelude must terminate a wedged
    # resolver even when the application process is gone.
    process = subprocess.Popen([sys.executable, '-I', '-c',
        bounded_resolver._WATCHDOG_PROGRAM + 'import time; time.sleep(60)',
        'example.test', '443', '.15'], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    try:
        assert process.wait(timeout=1) == -signal.SIGALRM
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)


def test_interrupted_resolver_is_reaped(monkeypatch):
    launched = []
    original = subprocess.Popen
    def interrupt(*args, **kwargs):
        process = original(*args, **kwargs)
        launched.append(process)
        communicate = process.communicate
        first = True
        def interrupted(*args, **kwargs):
            nonlocal first
            if first:
                first = False
                raise KeyboardInterrupt()
            return communicate(*args, **kwargs)
        process.communicate = interrupted
        return process
    monkeypatch.setattr(bounded_resolver.subprocess, 'Popen', interrupt)
    monkeypatch.setattr(bounded_resolver, '_RESOLVE_PROGRAM', 'import time; time.sleep(60)')
    with pytest.raises(KeyboardInterrupt):
        resolve_with_deadline('example.test', 443, timeout_seconds=2)
    assert len(launched) == 1 and launched[0].poll() is not None


@pytest.mark.parametrize('payload', ['{}', '[]', 'not json', '[1]',
    '[[2,1,6,"",["8.8.8.8",444]]]'])
def test_invalid_resolver_output_fails_closed(monkeypatch, payload):
    monkeypatch.setattr(bounded_resolver, '_RESOLVE_PROGRAM', f'print({payload!r})')
    with pytest.raises(ReadDenied, match='response'):
        resolve_with_deadline('example.test', 443, timeout_seconds=2)


def test_resolver_subprocess_private_answer_still_hits_public_policy(monkeypatch):
    monkeypatch.setattr(bounded_resolver, '_RESOLVE_PROGRAM',
        'print(\'[[2,1,6,"",["169.254.169.254",443]]]\')')
    request, grant = fixture()
    with pytest.raises(ReadDenied, match='public address'):
        prepare_public_destination(request, grant)


def test_dns_consumes_effect_deadline_before_any_connection():
    request, grant = fixture()
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    request = request.model_copy(update={'timeout_seconds': .03})
    def delayed(host, port, *, type):
        time.sleep(.05)
        return answers('8.8.8.8')(host, port, type=type)
    with pytest.raises(ReadDenied, match='before connection'):
        execute_public_read_experiment(request, grant, prepared, experiment_enabled=True,
            resolver=delayed, connection_factory=lambda *a, **kw: pytest.fail('dial after expiry'))


@pytest.fixture
def certificate(tmp_path):
    key, cert = tmp_path / 'key.pem', tmp_path / 'cert.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
        '-keyout', str(key), '-out', str(cert), '-days', '1',
        '-subj', '/CN=example.test', '-addext', 'subjectAltName=DNS:example.test'],
        check=True, capture_output=True, timeout=15)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return cert, context


@pytest.mark.parametrize('verification', ['trusted', 'wrong_host', 'untrusted'])
def test_real_tls_verifies_certificate_and_original_host(certificate, verification):
    cert, context = certificate
    sni, received = [], []
    context.set_servername_callback(lambda _sock, host, _ctx: sni.append(host))
    def handle(sock, _stopped):
        with context.wrap_socket(sock, server_side=True) as tls:
            received.append(read_headers(tls))
            body = b'Local TLS evidence'
            tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n'
                        b'Content-Length: 18\r\nConnection: close\r\n\r\n' + body)
    request, grant = fixture()
    if verification == 'wrong_host':
        request = request.model_copy(update={'url': 'https://wrong.test/evidence'})
        grant = grant.model_copy(update={'host': 'wrong.test'})
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    with server(handle) as port:
        def factory(host, public_port, ip, *, timeout):
            assert (public_port, ip) == (443, '8.8.8.8')
            client_context = ssl.create_default_context(cafile=str(cert)) if verification != 'untrusted' else None
            conn = PinnedHTTPSConnection(host, port, '127.0.0.1', timeout=timeout,
                                         context=client_context)
            assert conn.context.check_hostname and conn.context.verify_mode == ssl.CERT_REQUIRED
            return conn
        if verification == 'trusted':
            result = execute_public_read_experiment(request, grant, prepared,
                experiment_enabled=True, resolver=answers('8.8.8.8'), connection_factory=factory)
            assert result.text == 'Local TLS evidence'
            assert received and b'Host: example.test:' in received[0]
        else:
            with pytest.raises(ReadDenied, match='connection failed'):
                execute_public_read_experiment(request, grant, prepared,
                    experiment_enabled=True, resolver=answers('8.8.8.8'), connection_factory=factory)
            assert received == []
    assert sni == [grant.host]


def test_tls_handshake_stall_uses_remaining_deadline():
    request, grant = fixture()
    request = request.model_copy(update={'timeout_seconds': .15})
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    def stall(sock, stopped):
        stopped.wait(2)
    with server(stall) as port:
        def factory(host, public_port, ip, *, timeout):
            return PinnedHTTPSConnection(host, port, '127.0.0.1', timeout=timeout)
        start = time.monotonic()
        with pytest.raises(ReadDenied, match='connection failed'):
            execute_public_read_experiment(request, grant, prepared, experiment_enabled=True,
                resolver=answers('8.8.8.8'), connection_factory=factory)
        assert time.monotonic() - start < 1


@pytest.mark.parametrize('stage', ['status', 'headers', 'body', 'chunked'])
@pytest.mark.parametrize('use_tls', [False, True])
def test_trickled_http_cannot_extend_absolute_deadline(stage, use_tls, certificate):
    cert, context = certificate
    request, grant = fixture()
    request = request.model_copy(update={'timeout_seconds': .15})
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    def trickle(sock, stopped):
        if use_tls:
            with context.wrap_socket(sock, server_side=True) as tls:
                send_trickle(tls, stopped)
        else:
            send_trickle(sock, stopped)
    def send_trickle(sock, stopped):
        read_headers(sock)
        if stage == 'status':
            data = b'HTTP/1.1 200 OK\r\n'
        elif stage == 'headers':
            sock.sendall(b'HTTP/1.1 200 OK\r\n')
            data = b'Content-Type: text/plain\r\n'
        elif stage == 'body':
            sock.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n'
                         b'Content-Length: 100\r\nConnection: close\r\n\r\n')
            data = b'x' * 100
        else:
            sock.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n'
                         b'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n')
            data = b'64\r\n' + b'x' * 100 + b'\r\n0\r\n\r\n'
        for byte in data:
            if stopped.wait(.02):
                return
            sock.sendall(bytes([byte]))
    with server(trickle) as port:
        def factory(host, public_port, ip, *, timeout):
            if use_tls:
                return PinnedHTTPSConnection(host, port, '127.0.0.1', timeout=timeout,
                    context=ssl.create_default_context(cafile=str(cert)))
            return PinnedHTTPConnection(host, port, '127.0.0.1', timeout=timeout)
        start = time.monotonic()
        with pytest.raises(ReadDenied, match='connection failed'):
            execute_public_read_experiment(request, grant, prepared, experiment_enabled=True,
                resolver=answers('8.8.8.8'), connection_factory=factory)
        assert time.monotonic() - start < 1


@pytest.mark.parametrize('trusted', [True, False])
def test_mediated_attempt_and_provenance_through_local_tls(authenticated, certificate, trusted):
    from sqlalchemy import select
    from workforce.db import session_factory
    from workforce.models import ExternalReadObservation, ReadEffectAttempt
    from workforce.read_effect_experiment import run_read_effect_experiment
    from test_read_effect_experiment import approved_read
    cert, context = certificate
    invocation_id, _, _ = approved_read(authenticated)
    received, created = [], []
    def handle(sock, _stopped):
        with context.wrap_socket(sock, server_side=True) as tls:
            received.append(read_headers(tls))
            tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n'
                        b'Content-Length: 18\r\nConnection: close\r\n\r\nLocal TLS evidence')
    with server(handle) as port:
        def factory(host, public_port, ip, *, timeout):
            assert (host, public_port, ip) == ('example.test', 443, '8.8.8.8')
            created.append(True)
            return PinnedHTTPSConnection(host, port, '127.0.0.1', timeout=timeout,
                context=ssl.create_default_context(cafile=str(cert)) if trusted else None)
        def run():
            return run_read_effect_experiment(invocation_id, experiment_enabled=True,
                resolver=answers('8.8.8.8'), connection_factory=factory)
        if trusted:
            assert run() == 'succeeded'
        else:
            with pytest.raises(ReadDenied):
                run()
        assert run() == ('succeeded' if trusted else 'unknown')
        assert len(created) == 1 and len(received) == (1 if trusted else 0)
    with session_factory()() as db:
        attempt = db.get(ReadEffectAttempt, invocation_id)
        if trusted:
            observation = db.get(ExternalReadObservation, attempt.observation_id)
            assert observation.content == 'Local TLS evidence'
            assert observation.trust_origin == 'external_claim'
            assert observation.source_url == 'https://example.test/source'
        else:
            assert attempt.status == 'unknown' and attempt.observation_id is None
            assert db.scalar(select(ExternalReadObservation)) is None



def test_rejected_response_closes_its_file_even_when_connection_dropped_socket():
    request, grant = fixture()
    request = request.model_copy(update={'max_bytes': 1})
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    from test_local_read_experiment import local_server
    responses = []
    with local_server() as (port, _seen):
        def factory(host, public_port, ip, *, timeout):
            connection = PinnedHTTPConnection(host, port, '127.0.0.1', timeout=timeout)
            original = connection.getresponse
            def capture():
                response = original()
                responses.append(response)  # keep alive so GC cannot hide a leak
                return response
            connection.getresponse = capture
            return connection
        with pytest.raises(ReadDenied, match='byte limit'):
            execute_public_read_experiment(request, grant, prepared, experiment_enabled=True,
                resolver=answers('8.8.8.8'), connection_factory=factory)
    assert len(responses) == 1 and responses[0].isclosed()
