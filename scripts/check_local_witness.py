"""Run only the synthetic local witness suite; no database or product startup."""
import os
import ast
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MODULES = frozenset({
    'durable_local_recovery_witness',
    'durable_local_witness_transport',
    'run_durable_local_witness_server',
    'synthetic_write_recovery_witness',
    'synthetic_write_ledger',
    'synthetic_write_admission',
    'synthetic_write_receipt_acceptance',
})
TEST_NAMES = (
    'test_durable_local_recovery_witness.py',
    'test_durable_witness_fake_ledger_recovery.py',
    'test_durable_local_witness_transport.py',
    'test_witness_pending_snapshot_audit_rollback.py',
    'test_witness_rpc_response_validation.py',
    'test_synthetic_write_recovery_witness.py',
)
COMPILE_PATHS = (
    *(f'backend/tests/{name}' for name in TEST_NAMES),
    'backend/tests/durable_local_recovery_witness.py',
    'backend/tests/durable_local_witness_transport.py',
    'backend/tests/run_durable_local_witness_server.py',
    'backend/tests/synthetic_write_recovery_witness.py',
    'backend/tests/synthetic_write_ledger.py',
    'backend/tests/test_synthetic_write_admission.py',
    'backend/src/workforce/synthetic_write_contract.py',
    'backend/src/workforce/reviewed_runner_contract.py',
    'scripts/check_local_witness.py',
)


def check_product_imports():
    files = sorted((ROOT/'backend/src').rglob('*.py'))
    if not files:
        raise SystemExit('No product Python source files found for fixture import check')
    violations = []
    for path in files:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '', *(alias.name for alias in node.names)]
            else:
                continue
            if any(FIXTURE_MODULES.intersection(name.split('.')) for name in names):
                violations.append(f'{path.relative_to(ROOT)}:{node.lineno}')
    if violations:
        print('Product imports test-only witness/fake-ledger modules: ' +
            ', '.join(violations), file=sys.stderr)
        return False
    print(f'Product fixture import check: {len(files)} Python files passed.', flush=True)
    return True


def main():
    if not check_product_imports():
        return 1
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(str(ROOT / path) for path in
        ('backend/tests', 'backend/src'))
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    env.pop('PYTEST_ADDOPTS', None)
    env.pop('PYTEST_PLUGINS', None)
    result = subprocess.run([
        sys.executable, '-m', 'pytest', '-q', '-x', '--noconftest',
        '-c', os.devnull, '-p', 'no:cacheprovider',
        *(str(ROOT/'backend/tests'/name) for name in TEST_NAMES),
    ], cwd=ROOT, env=env, check=False)
    if result.returncode:
        return result.returncode
    with tempfile.TemporaryDirectory(prefix='witness-compile-') as directory:
        for index, path in enumerate(COMPILE_PATHS):
            py_compile.compile(str(ROOT/path),
                cfile=str(Path(directory)/f'{index}.pyc'), doraise=True)
    print(f'Local witness compilation: {len(COMPILE_PATHS)} files passed; '
          'PostgreSQL fixture compiled only.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
