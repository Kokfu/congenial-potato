"""Prove local Compose backend egress denial using a disposable synthetic sink.

Requires the running Compose fixture and Docker Engine 28+. No public network
probe, model call, credential or production integration is used. Only containers
created by this script are removed; application services/volumes are preserved.
"""
import ipaddress
import json
import subprocess
import sys
import time
from uuid import uuid4


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, text=True,
                          capture_output=True, timeout=45)


def inspect_json(kind, target, template):
    return json.loads(docker(kind, 'inspect', '--format', template, target).stdout)


def container(service):
    result = docker('compose', 'ps', '--all', '-q', service).stdout.strip().splitlines()
    assert len(result) == 1, f'Expected one local {service} container'
    return result[0]


def networks(container_id):
    return json.loads(docker('inspect', '--format',
        '{{json .NetworkSettings.Networks}}', container_id).stdout)


def execute(container_id, code, *args):
    return docker('exec', '--user', '10001:10001', container_id,
                  'python', '-c', code, *args).stdout.strip()


SINK = '''
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'LOCAL_EGRESS_SINK'
        print('sink_request', flush=True)
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass
server = HTTPServer(('0.0.0.0', 8089), Handler)
print('sink_ready', flush=True)
server.serve_forever()
'''

PROBE = '''
import http.client
import socket
import sys
import urllib.request
from pathlib import Path
sink, web = sys.argv[1:]
# Lack of a gateway matters: an internal bridge with a host gateway alone is
# insufficient. Also require that IPv6 is unavailable outside loopback.
rows = Path('/proc/net/route').read_text().splitlines()[1:]
assert all(row.split()[1] != '00000000' for row in rows), 'default route exists'
assert all(row.split()[-1] == 'lo' for row in
           Path('/proc/net/if_inet6').read_text().splitlines()), 'IPv6 interface exists'
for port in (5432,):
    with socket.create_connection(('db', port), timeout=2):
        pass

def must_deny(call):
    try:
        call()
    except (OSError, urllib.error.URLError):
        return
    raise AssertionError('synthetic outside destination was reachable')

must_deny(lambda: socket.create_connection((sink, 8089), timeout=1))
def direct_http():
    conn = http.client.HTTPConnection(sink, 8089, timeout=1)
    try:
        conn.request('GET', '/direct')
        conn.getresponse().read()
    finally:
        conn.close()
must_deny(direct_http)
# Treat the sink as a hypothetical proxy. Even that proxy's private numeric
# address must be unreachable; fixture.invalid is never resolved or contacted.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({
    'http': 'http://' + sink + ':8089'}))
must_deny(lambda: opener.open('http://fixture.invalid/proxy', timeout=1))
# The dual-homed web service is a fixed reverse proxy, not a CONNECT tunnel.
conn = http.client.HTTPConnection(web, 8080, timeout=2)
try:
    conn.request('CONNECT', sink + ':8089')
    response = conn.getresponse()
    assert response.status >= 400, 'web accepted a CONNECT tunnel'
    response.read()
finally:
    conn.close()
conn = http.client.HTTPConnection(web, 8080, timeout=2)
try:
    conn.request('GET', 'http://' + sink + ':8089/forward-proxy')
    response = conn.getresponse()
    assert response.read(65536) != b'LOCAL_EGRESS_SINK', 'web forwarded an arbitrary origin'
finally:
    conn.close()
print('routes=isolated; db=reachable; direct=denied; http=denied; proxy=denied; connect=denied; web_forward=denied')
'''


def main():
    version = docker('version', '--format', '{{.Server.Version}}').stdout.strip()
    assert int(version.split('.')[0]) >= 28, 'Docker Engine 28+ is required'
    services = {name: container(name) for name in ('db', 'migrate', 'api', 'worker', 'web')}
    attached = {name: networks(cid) for name, cid in services.items()}
    assert len(attached['worker']) == 1
    control = next(iter(attached['worker']))
    for name in ('db', 'migrate', 'api', 'worker'):
        assert set(attached[name]) == {control}, f'{name} has another network'
        assert not attached[name][control].get('Gateway'), f'{name} has a host gateway'
    edge_names = set(attached['web']) - {control}
    assert len(edge_names) == 1 and len(attached['web']) == 2
    edge = edge_names.pop()
    config = inspect_json('network', control, '{{json .}}')
    assert config['Internal'] and not config['EnableIPv6']
    assert config['Options'].get('com.docker.network.bridge.gateway_mode_ipv4') == 'isolated'
    for name in ('api', 'worker', 'migrate'):
        dropped = json.loads(docker('inspect', '--format', '{{json .HostConfig.CapDrop}}', services[name]).stdout)
        assert {'NET_ADMIN', 'NET_RAW'} <= {cap.removeprefix('CAP_') for cap in dropped}
        options = json.loads(docker('inspect', '--format', '{{json .HostConfig.SecurityOpt}}', services[name]).stdout)
        assert 'no-new-privileges:true' in options
    image = docker('inspect', '--format', '{{.Image}}', services['worker']).stdout.strip()
    sink = 'workforce-egress-sink-' + uuid4().hex[:12]
    created = False
    try:
        docker('run', '-d', '--name', sink, '--network', edge, '--user', '10001:10001',
               '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
               '--entrypoint', 'python', image, '-u', '-c', SINK)
        created = True
        sink_ip = networks(sink)[edge]['IPAddress']
        assert ipaddress.ip_address(sink_ip).is_private
        deadline = time.monotonic() + 15
        while 'sink_ready' not in docker('logs', sink).stdout:
            assert time.monotonic() < deadline, 'synthetic sink not ready'
            time.sleep(.1)
        # Positive control proves the sink is listening from its own network.
        positive = docker('run', '--rm', '--network', edge, '--user', '10001:10001',
            '--read-only', '--cap-drop', 'ALL', '--entrypoint', 'python', image, '-c',
            "import http.client,sys; c=http.client.HTTPConnection(sys.argv[1],8089,timeout=2); "
            "c.request('GET','/positive'); r=c.getresponse(); "
            "assert r.status==200 and r.read()==b'LOCAL_EGRESS_SINK'; c.close(); print('positive=passed')",
            sink_ip).stdout.strip()
        assert positive == 'positive=passed'
        web_ip = attached['web'][control]['IPAddress']
        for name in ('api', 'worker'):
            result = execute(services[name], PROBE, sink_ip, web_ip)
            print(f'{name}: {result}')
        assert docker('logs', sink).stdout.count('sink_request') == 1, 'denied probe reached sink'
        print('egress_smoke=passed; synthetic_positive=passed; backend_bypass=denied')
    finally:
        if created:
            docker('rm', '-f', sink, check=False)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        # Commands contain only fixed fixtures and container IDs, not secrets.
        print(exc.stderr, file=sys.stderr)
        raise
