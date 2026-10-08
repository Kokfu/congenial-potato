from datetime import datetime, timedelta, timezone
import socket

import pytest

from workforce.local_read_experiment import ReadDenied, ReadRequest
from workforce.network_policy import (PinnedHTTPConnection, PinnedHTTPSConnection,
    PublicReadGrant, execute_public_read_experiment,
    prepare_public_destination, revalidate_public_destination)

from test_local_read_experiment import local_server


def answers(*addresses):
    def resolve(_host, port, *, type):
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))
                for ip in addresses]
    return resolve


def fixture():
    request = ReadRequest(project_id='project-a', agent_id='agent-a',
                          url='https://example.test/evidence')
    grant = PublicReadGrant(project_id='project-a', agent_id='agent-a',
                            host='example.test', expires_at=(
        datetime.now(timezone.utc) + timedelta(minutes=1)))
    return request, grant


def test_public_dns_is_rechecked_before_pinning():
    request, grant = fixture()
    prepared = prepare_public_destination(request, grant,
                                          resolver=answers('8.8.8.8', '1.1.1.1'))
    assert prepared.addresses == ('1.1.1.1', '8.8.8.8')
    assert revalidate_public_destination(request, grant, prepared,
                                         resolver=answers('8.8.8.8', '1.1.1.1')) == '1.1.1.1'
    for rebinding in (answers('127.0.0.1'), answers('169.254.169.254'),
                      answers('10.0.0.1'), answers('8.8.8.8', '10.0.0.1')):
        with pytest.raises(ReadDenied):
            revalidate_public_destination(request, grant, prepared,
                                          resolver=rebinding)
    with pytest.raises(ReadDenied, match='changed'):
        revalidate_public_destination(request, grant, prepared,
                                      resolver=answers('8.8.8.8'))


def test_exact_grant_and_url_reject_authority_tricks():
    request, grant = fixture()
    bad_urls = [
        'http://example.test/evidence', 'https://other.test/evidence',
        'https://example.test:444/evidence',
        'https://example.test:0/evidence',
        'https://user:pass@example.test/evidence',
        'https://example.test/evidence#fragment',
        'https://example.test./evidence',
        'https://example.test\\@other.test/evidence',
        'https://example.test/line\nunsafe',
    ]
    for url in bad_urls:
        with pytest.raises(ReadDenied):
            prepare_public_destination(request.model_copy(update={'url': url}),
                                       grant, resolver=answers('8.8.8.8'))
    with pytest.raises(ReadDenied):
        prepare_public_destination(request.model_copy(update={'project_id': 'other'}),
                                   grant, resolver=answers('8.8.8.8'))
    with pytest.raises(ReadDenied):
        prepare_public_destination(request, grant.model_copy(update={
            'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}),
            resolver=answers('8.8.8.8'))
    with pytest.raises(ReadDenied):
        prepare_public_destination(request, grant, resolver=answers('::ffff:169.254.169.254'))


def test_socket_dials_pinned_ip_and_checks_peer_before_request():
    with local_server() as (port, seen):
        connection = PinnedHTTPConnection('fixture.test', port, '127.0.0.1', timeout=2)
        try:
            connection.request('GET', '/ok')
            response = connection.getresponse()
            assert response.status == 200 and response.read() == b'A synthetic source claim'
        finally:
            connection.close()
        assert seen == ['/ok']

        wrong_peer = PinnedHTTPConnection('fixture.test', port, '127.0.0.2', timeout=2,
            socket_factory=lambda _address, _timeout: socket.create_connection(
                ('127.0.0.1', port), timeout=2))
        with pytest.raises(ReadDenied, match='peer'):
            wrong_peer.connect()

        class TestContext:
            def __init__(self):
                self.server_hostname = None

            def wrap_socket(self, sock, *, server_hostname):
                self.server_hostname = server_hostname
                return sock

        context = TestContext()
        tls = PinnedHTTPSConnection('fixture.test', port, '127.0.0.1',
                                    timeout=2, context=context)
        try:
            tls.connect()
            assert context.server_hostname == 'fixture.test'
        finally:
            tls.close()


def test_effect_revalidation_precedes_synthetic_connection_and_redirects_stop():
    request, grant = fixture()
    prepared = prepare_public_destination(request, grant, resolver=answers('8.8.8.8'))
    created = []
    with local_server() as (port, seen):
        def factory(host, public_port, ip, *, timeout):
            created.append((host, public_port, ip))
            return PinnedHTTPConnection(host, port, '127.0.0.1', timeout=timeout)
        with pytest.raises(ReadDenied, match='disabled'):
            execute_public_read_experiment(request, grant, prepared,
                                           resolver=answers('8.8.8.8'),
                                           connection_factory=factory)
        with pytest.raises(ReadDenied):
            execute_public_read_experiment(request, grant, prepared,
                experiment_enabled=True, resolver=answers('169.254.169.254'),
                connection_factory=factory)
        assert created == [] and seen == []
        result = execute_public_read_experiment(request, grant, prepared,
            experiment_enabled=True, resolver=answers('8.8.8.8'),
            connection_factory=factory)
        assert result.text == 'A synthetic source claim'
        assert created == [('example.test', 443, '8.8.8.8')]
        assert seen == ['/evidence']
        redirect = request.model_copy(update={'url': 'https://example.test/redirect'})
        with pytest.raises(ReadDenied, match='302'):
            execute_public_read_experiment(redirect, grant, prepared,
                experiment_enabled=True, resolver=answers('8.8.8.8'),
                connection_factory=factory)
        assert '/target' not in seen
