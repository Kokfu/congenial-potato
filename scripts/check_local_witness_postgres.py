"""Run synthetic witness/admission checks on disposable, unpublished PostgreSQL.

Requires Linux, a reachable local Docker Unix socket, the pinned image already
present, backend development dependencies, and host access to an internal bridge.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from check_local_witness import check_product_imports


ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'postgres@sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929'
DOCKER = ['docker', '--host=unix:///var/run/docker.sock']
SELECTION = ('test_live_witness_blocks_single_or_joint_store_rollback or '
             'test_lost_rpc_consume_reply_keeps_postgres_and_fake_ledger_empty')


def docker_env():
    env = dict(os.environ)
    for name in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS',
                 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(name, None)
    return env


def docker(*args):
    return subprocess.check_output(DOCKER + list(args), env=docker_env(),
        text=True, stderr=subprocess.STDOUT, timeout=60).strip()


def test_env(host):
    env = dict(os.environ)
    for name in list(env):
        if name.startswith('DBOS__') or name in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS'):
            env.pop(name)
    env.update(
        APP_DATABASE_URL=f'postgresql+psycopg://postgres@{host}:5432/workforce_test?connect_timeout=5',
        DBOS_SYSTEM_DATABASE_URL=f'postgresql://postgres@{host}:5432/workforce_dbos_test?connect_timeout=5',
        DAILY_CAP_USD='0', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        PYTHONPATH=os.pathsep.join(str(ROOT / path) for path in
            ('backend/src', 'backend/tests')))
    return env


def remove_owned(kind, name, label):
    # Inspect exact names and ownership before removal; never prune shared state.
    info = json.loads(docker(kind, 'inspect', name))[0]
    labels = info['Config']['Labels'] if kind == 'container' else info['Labels']
    if labels.get('workforce.witness.check') != label:
        raise RuntimeError(f'Refusing cleanup of unexpected {kind}: {name}')
    docker(kind, 'rm', *(['--force'] if kind == 'container' else []), name)
    print(f'Removed own {kind}: {name}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full-admission', action='store_true',
        help='run the entire synthetic admission file instead of seven witness cases')
    args = parser.parse_args()
    if not check_product_imports():
        return 1
    # No automatic downloads, existing databases, host mounts or product services.
    docker('image', 'inspect', IMAGE)
    token = uuid4().hex
    container, network = f'witness-pg-{token}', f'witness-net-{token}'
    label = f'local-only-{token}'
    created_network = created_container = False
    try:
        created_network = True
        docker('network', 'create', '--internal', '--label',
            f'workforce.witness.check={label}', network)
        # Create before start so a start failure still leaves a known cleanup target.
        created_container = True
        docker('create', '--pull=never', '--name', container,
            '--label', f'workforce.witness.check={label}', '--network', network,
            '--memory', '512m', '--cpus', '1', '--pids-limit', '128',
            '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,mode=700',
            '--env', 'POSTGRES_HOST_AUTH_METHOD=trust',
            '--env', 'POSTGRES_DB=workforce_test', IMAGE)
        info = json.loads(docker('container', 'inspect', container))[0]
        net = json.loads(docker('network', 'inspect', network))[0]
        if (info['HostConfig']['PortBindings'] or
                info['HostConfig']['Binds'] or not net['Internal'] or
                info['HostConfig']['Tmpfs'] != {
                    '/var/lib/postgresql/data': 'rw,nosuid,nodev,mode=700'}):
            raise RuntimeError('Disposable database isolation checks failed')
        docker('start', container)
        deadline = time.monotonic() + 30
        while True:
            try:
                docker('exec', container, 'pg_isready', '-h', '127.0.0.1',
                    '-U', 'postgres', '-d', 'workforce_test')
                break
            except subprocess.CalledProcessError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Disposable PostgreSQL did not become ready') from None
                time.sleep(0.25)
        info = json.loads(docker('container', 'inspect', container))[0]
        host = info['NetworkSettings']['Networks'][network]['IPAddress']
        if not ipaddress.ip_address(host).is_private:
            raise RuntimeError('Expected private disposable bridge address')
        docker('exec', container, 'createdb', '-U', 'postgres', 'workforce_dbos_test')
        env = test_env(host)
        jobs = [
            ('Application migration', ROOT/'backend',
                ['-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head']),
            ('Workflow migration', ROOT/'backend',
                ['-m', 'workforce.migrate_workflows']),
            ('Synthetic admission checks', ROOT,
                ['-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider',
                 'backend/tests/test_synthetic_write_admission.py'] +
                ([] if args.full_admission else ['-k', SELECTION])),
        ]
        for title, cwd, command in jobs:
            print(title, flush=True)
            subprocess.run([sys.executable, *command], cwd=cwd, env=env,
                check=True, timeout=300)
    finally:
        # Attempt both cleanups even if one fails; report any resource left behind.
        failed = []
        for created, kind, name in ((created_container, 'container', container),
                                   (created_network, 'network', network)):
            if created:
                try:
                    remove_owned(kind, name, label)
                except Exception as error:
                    failed.append(f'{kind} {name}: {error}')
        if failed:
            raise RuntimeError('Fixture cleanup incomplete: ' + '; '.join(failed))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
