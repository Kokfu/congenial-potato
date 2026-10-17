"""Start a private fixture workspace on a free port; stop preserves its data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'workforce.local.instance'
SERVICES = ('db', 'migrate', 'api', 'worker', 'web')


def run(args, *, env=None, capture=True, timeout=60):
    result = subprocess.run(args, env=env, cwd=ROOT, text=True,
        capture_output=capture, check=True, timeout=timeout)
    return result.stdout.strip() if capture else ''


def require_local_docker():
    # Honor a local Desktop context, but refuse remote/production Docker targets.
    context = os.environ.get('DOCKER_CONTEXT')
    endpoint = os.environ.get('DOCKER_HOST') if not context else None
    if endpoint is None:
        endpoint = run(['docker', 'context', 'inspect', *([context] if context else []),
            '--format', '{{.Endpoints.docker.Host}}'])
    if not endpoint.startswith(('unix://', 'npipe://')):
        raise ValueError('A local Docker socket/Desktop context is required; remote Docker is refused')
    info = json.loads(run(['docker', 'info', '--format', '{{json .}}']))
    if info['OSType'] != 'linux' or int(info['ServerVersion'].split('.')[0]) < 28:
        raise ValueError('Docker Engine 28+ with Linux containers is required')


def available_port(requested=None):
    if requested is not None and not 1024 <= requested <= 65535:
        raise ValueError('Port must be between 1024 and 65535')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(('127.0.0.1', requested or 0))
        except OSError:
            raise ValueError(f'Loopback port {requested} is occupied; no existing process was changed') from None
        return listener.getsockname()[1]


def read_state(directory):
    path = directory/'runtime.json'
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    if (type(state) is not dict or set(state) != {'project', 'instance', 'port'} or
            type(state['instance']) is not str or len(state['instance']) != 32 or
            any(c not in '0123456789abcdef' for c in state['instance']) or
            state['project'] != 'workforce-mvp-' + state['instance'][:12] or
            type(state['port']) is not int or not 1024 <= state['port'] <= 65535):
        raise ValueError('Invalid local runtime metadata; refusing to select Docker resources')
    return state


def write_private(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(content)


def compose_config(directory, state, build_ca=None):
    services = {}
    for name in SERVICES:
        image = 'backend' if name in ('migrate', 'api', 'worker') else name
        services[name] = {'image': f"{state['project']}-{image}:local",
            'labels': {LABEL: state['instance']}}
        if build_ca and name != 'db':
            services[name]['build'] = {'secrets': [
                {'source': 'local_build_ca', 'target': 'proxy_ca'}]}
    config = {'services': services,
        'networks': {name: {'labels': {LABEL: state['instance']}} for name in ('control', 'edge')},
        'volumes': {name: {'labels': {LABEL: state['instance']}} for name in ('pgdata', 'artifacts')},
        'secrets': {name: {'file': str(directory/name)}
            for name in ('db_password', 'initial_admin_password')}}
    if build_ca:
        config['secrets']['local_build_ca'] = {'file': str(build_ca)}
    return config


def environment(directory, state):
    env = dict(os.environ)
    env.update(COMPOSE_PROJECT_NAME=state['project'],
        COMPOSE_FILE=os.pathsep.join((str(ROOT/'docker-compose.yml'), str(directory/'compose.json'))),
        BIND_ADDR='127.0.0.1', PORT=str(state['port']),
        PUBLIC_BASE_URL=f"http://localhost:{state['port']}",
        SESSION_COOKIE_SECURE='false', DAILY_CAP_USD='0')
    env.pop('COMPOSE_PROFILES', None)
    env.pop('COMPOSE_ENV_FILES', None)
    return env


def check_ownership(state):
    for kind in ('container', 'network', 'volume'):
        args = ['docker', kind, 'ls', *(['-a'] if kind == 'container' else []), '-q',
            '--filter', 'label=com.docker.compose.project=' + state['project']]
        identities = run(args).splitlines()
        if identities:
            for item in json.loads(run(['docker', kind, 'inspect', *identities])):
                labels = item['Config']['Labels'] if kind == 'container' else item['Labels']
                if not labels or labels.get(LABEL) != state['instance']:
                    raise ValueError('Existing Docker resource is not owned by this local workspace')


def doctor(directory, state):
    """Inspect prerequisites without initializing a workspace or changing Docker resources."""
    if sys.version_info < (3, 10):
        raise ValueError('Python 3.10+ is required')
    print(f'Python {sys.version_info.major}.{sys.version_info.minor}: ready')
    require_local_docker()
    print('Local Docker Engine 28+ / Linux containers: ready')
    version = run(['docker', 'compose', 'version', '--short'])
    if int(version.lstrip('v').split('.')[0]) < 2:
        raise ValueError('Docker Compose v2+ is required')
    print(f'Docker Compose {version}: ready')
    available_port()
    print('An unused loopback port is available; startup will select its own port.')
    if state:
        check_ownership(state)
        for name in ('db_password', 'initial_admin_password', 'compose.json'):
            if not (directory/name).is_file():
                raise ValueError(f'Retained workspace file missing: {name}; restore it before startup')
        run(['docker', 'compose', 'config', '--quiet'], env=environment(directory, state))
        print('Retained runtime files and Docker ownership: ready (no password contents read)')
    else:
        print('No saved workspace yet; start will initialize a separate local project.')
    print('Doctor passed. This does not validate container startup, network isolation or PC end-to-end behavior.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status', 'stop', 'doctor'))
    parser.add_argument('--port', type=int, help='explicit unused port; otherwise select one automatically')
    parser.add_argument('--state-dir', type=Path, default=ROOT/'.local/mvp')
    parser.add_argument('--no-build', action='store_true', help='use this workspace project images already built')
    parser.add_argument('--build-ca', type=Path, help='optional public CA bundle for a managed build proxy')
    args = parser.parse_args(argv)
    directory = args.state_dir.absolute()
    state = read_state(directory)
    if args.action == 'doctor':
        doctor(directory, state)
        return 0
    if args.action != 'start' and state is None:
        print('Local workspace has not been initialized.')
        return 0
    require_local_docker()
    if state:
        check_ownership(state)
    if args.action == 'start':
        if args.build_ca and not args.build_ca.is_file():
            raise ValueError('Build CA bundle does not exist')
        running = ''
        if state:
            running = run(['docker', 'container', 'ls', '-q', '--filter',
                'label=com.docker.compose.project=' + state['project'], '--filter',
                'label=com.docker.compose.service=web'])
            if running:
                if args.port is not None and args.port != state['port']:
                    raise ValueError('Stop this workspace before changing its port')
        # An existing owned web service already occupies its port. Keep it while
        # reconciling/building the whole stack and waiting for readiness again.
        port = state['port'] if running else available_port(args.port)
        if state is None:
            token = uuid4().hex
            state = {'project': 'workforce-mvp-' + token[:12], 'instance': token, 'port': port}
            check_ownership(state)
        state['port'] = port
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ('db_password', 'initial_admin_password'):
            if not (directory/name).exists():
                # Never silently replace credentials for an initialized workspace.
                if (directory/'runtime.json').exists():
                    raise ValueError('Retained workspace credential file is missing; restore it before startup')
                write_private(directory/name, secrets.token_urlsafe(32) + '\n')
        ca = args.build_ca.absolute() if args.build_ca else None
        (directory/'compose.json').write_text(json.dumps(compose_config(directory, state, ca)))
        (directory/'runtime.json').write_text(json.dumps(state))
    env = environment(directory, state)
    command = ['docker', 'compose']
    if args.action == 'start':
        run(command + ['up', '-d', '--no-build' if args.no_build else '--build',
            '--wait', '--wait-timeout', '180'], env=env, capture=False, timeout=900)
        print(f"Open http://localhost:{state['port']}")
        print(f"Owner password file (keep private): {directory/'initial_admin_password'}")
        print('Fixture-only workspace. Stop preserves data. No other project or occupied port is changed.')
    elif args.action == 'status':
        run(command + ['ps'], env=env, capture=False)
        print(f"Workspace URL: http://localhost:{state['port']}")
        print(f"Owner password file: {directory/'initial_admin_password'}")
    else:
        run(command + ['stop'], env=env, capture=False, timeout=120)
        print('Stopped this workspace; containers, private secrets and persistent volumes retained.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Local workspace command failed: {error}', file=sys.stderr)
        raise SystemExit(1)
