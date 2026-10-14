"""Exercise fresh local Compose volumes and remove only this fixture's resources.

Build the Compose images first. Uses synthetic private secrets, a unique project
and a temporary loopback port; never resets the regular application's volumes.
Requires Docker Engine 28+ and the installed backend Python dependencies.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    project = 'workforce-clean-' + uuid4().hex[:12]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    # A port race fails startup and triggers cleanup; it never falls back to a
    # non-loopback bind or reuses the regular project's resources.
    with tempfile.TemporaryDirectory(prefix=project + '-') as directory:
        private = Path(directory)
        paths = {}
        for name in ('db_password', 'initial_admin_password'):
            paths[name] = private / name
            paths[name].write_text(secrets.token_urlsafe(32))
            paths[name].chmod(0o600)
        override = private / 'compose.json'
        override.write_text(json.dumps({'secrets': {
            name: {'file': str(path)} for name, path in paths.items()}}))
        env = {**os.environ, 'COMPOSE_PROJECT_NAME': project,
            'COMPOSE_FILE': os.pathsep.join((str(root / 'docker-compose.yml'), str(override))),
            'BIND_ADDR': '127.0.0.1', 'PORT': str(port),
            'PUBLIC_BASE_URL': f'http://localhost:{port}',
            'SESSION_COOKIE_SECURE': 'false', 'DAILY_CAP_USD': '0'}

        def run(arguments, *, timeout=60):
            result = subprocess.run(arguments, cwd=root, env=env, text=True,
                                    capture_output=True, timeout=timeout)
            if result.returncode:
                # Do not dump command output, configuration or secret contents.
                raise RuntimeError(f'Fixture command failed ({arguments[0]}, exit {result.returncode}); project={project}')
            return result.stdout.strip()

        def compose(*arguments, timeout=60):
            return run(['docker', 'compose', *arguments], timeout=timeout)

        def sql(database, query):
            return compose('exec', '-T', 'db', 'psql', '-U', 'postgres', '-d', database,
                           '-v', 'ON_ERROR_STOP=1', '-Atc', query)

        def resources(kind):
            options = ['--all'] if kind == 'container' else []
            return run(['docker', kind, 'ls', *options, '-q', '--filter',
                        'label=com.docker.compose.project=' + project])

        # Refuse even an improbable namespace collision before any mutation or
        # cleanup. Never adopt pre-existing application or fixture resources.
        for kind in ('container', 'network', 'volume'):
            assert not resources(kind), f'Existing {kind} namespace; project={project}'
        try:
            # Explicit no-build keeps this acceptance run on the reviewed images.
            compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '120', timeout=150)
            assert set(sql('postgres', "SELECT datname FROM pg_database WHERE datname IN ('workforce','workforce_dbos')").splitlines()) == {'workforce', 'workforce_dbos'}
            assert sql('workforce', 'SELECT count(*) FROM projects') == '0'
            for service, uid in (('db', '999'), ('api', '10001'), ('worker', '10001')):
                status = compose('exec', '-T', service, 'cat', '/proc/1/status')
                ids = next(line for line in status.splitlines() if line.startswith('Uid:')).split()[1:]
                assert ids == [uid] * 4, f'{service} PID 1 UID unavailable'
            print('fresh_volumes=passed; both_databases=present; pid1_non_root=passed', flush=True)
            print(run([sys.executable, 'scripts/smoke.py', '--base-url', env['PUBLIC_BASE_URL'],
                       '--password-file', str(paths['initial_admin_password'])]), flush=True)
            assert sql('workforce', "SELECT count(*) FROM executions WHERE status='succeeded'") == '1'
            print(run([sys.executable, 'scripts/egress_smoke.py'], timeout=120), flush=True)
        finally:
            compose('down', '--volumes', '--remove-orphans', timeout=90)
            for kind in ('container', 'network', 'volume'):
                assert not resources(kind), f'Fixture {kind} cleanup incomplete; project={project}'
            print('fixture_resources=removed', flush=True)
    print('clean_compose_smoke=passed', flush=True)


if __name__ == '__main__':
    main()
