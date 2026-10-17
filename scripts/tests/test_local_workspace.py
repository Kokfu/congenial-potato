import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('local_workspace', Path(__file__).parents[1]/'local_workspace.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LocalWorkspaceTests(unittest.TestCase):
    def state(self):
        token = 'a'*32
        return {'project': 'workforce-mvp-' + token[:12], 'instance': token, 'port': 49152}

    def test_occupied_port_is_refused_without_closing_other_listener(self):
        with socket.socket() as other:
            other.bind(('127.0.0.1', 0))
            other.listen(1)
            port = other.getsockname()[1]
            with self.assertRaisesRegex(ValueError, 'occupied'):
                launcher.available_port(port)
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                accepted, _ = other.accept()
                accepted.close()

    def test_automatic_port_is_loopback_and_nonprivileged(self):
        port = launcher.available_port()
        self.assertGreaterEqual(port, 1024)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))

    def test_invalid_ports_refused(self):
        for port in (-1, 0, 80, 65536):
            with self.subTest(port=port), self.assertRaises(ValueError):
                launcher.available_port(port)

    def test_remote_docker_refused_before_info(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://production.example:2376'}, clear=True), \
                patch.object(launcher, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'remote Docker'):
                launcher.require_local_docker()
            run.assert_not_called()

    def test_local_desktop_context_overrides_inherited_host(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://unused.example', 'DOCKER_CONTEXT': 'desktop-linux'}, clear=True), \
                patch.object(launcher, 'run', side_effect=[
                    'unix:///local/docker.sock', json.dumps({'OSType': 'linux', 'ServerVersion': '28.4.0'})]) as run:
            launcher.require_local_docker()
            self.assertIn('desktop-linux', run.call_args_list[0].args[0])

    def test_existing_foreign_resource_is_not_adopted(self):
        with patch.object(launcher, 'run', side_effect=['sentinel-container',
                json.dumps([{'Config': {'Labels': {launcher.LABEL: 'someone-else'}}}])]):
            with self.assertRaisesRegex(ValueError, 'not owned'):
                launcher.check_ownership(self.state())

    def test_runtime_metadata_cannot_select_another_project(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            state = self.state()
            (path/'runtime.json').write_text(json.dumps(state))
            self.assertEqual(launcher.read_state(path), state)
            state['project'] = 'other-project'
            (path/'runtime.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                launcher.read_state(path)

    def test_compose_override_labels_every_resource_and_uses_own_images(self):
        state = self.state()
        config = launcher.compose_config(Path('/private/workforce'), state)
        for group in ('services', 'networks', 'volumes'):
            for resource in config[group].values():
                self.assertEqual(resource['labels'], {launcher.LABEL: state['instance']})
        self.assertTrue(all(v['image'].startswith(state['project']) for v in config['services'].values()))
        self.assertNotIn('ports', config['services']['web'])

    def test_environment_overrides_conflicting_project_ports_and_paid_cap(self):
        with patch.dict(os.environ, {'PORT': '8080', 'COMPOSE_FILE': 'other.yml',
                'BIND_ADDR': '0.0.0.0', 'DAILY_CAP_USD': '100', 'COMPOSE_PROFILES': 'live'}):
            env = launcher.environment(Path('/private/workforce'), self.state())
        self.assertEqual(env['PORT'], '49152')
        self.assertEqual(env['PUBLIC_BASE_URL'], 'http://localhost:49152')
        self.assertEqual(env['BIND_ADDR'], '127.0.0.1')
        self.assertEqual(env['DAILY_CAP_USD'], '0')
        self.assertNotIn('COMPOSE_PROFILES', env)
        self.assertNotEqual(env['COMPOSE_FILE'], 'other.yml')

    def test_private_secret_creation_is_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'password'
            launcher.write_private(path, 'fixture-only')
            with self.assertRaises(FileExistsError):
                launcher.write_private(path, 'replacement')
            self.assertEqual(path.read_text(), 'fixture-only')
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def saved_workspace(self, directory):
        state = self.state()
        (directory/'runtime.json').write_text(json.dumps(state))
        (directory/'compose.json').write_text('{}')
        for name in ('db_password', 'initial_admin_password'):
            launcher.write_private(directory/name, 'private-test-sentinel')
        return state

    def test_running_start_reconciles_readiness_and_requested_build_mode(self):
        for no_build in (False, True):
            with self.subTest(no_build=no_build), tempfile.TemporaryDirectory() as d:
                directory = Path(d)
                state = self.saved_workspace(directory)
                with patch.object(launcher, 'require_local_docker'), \
                        patch.object(launcher, 'check_ownership'), \
                        patch.object(launcher, 'available_port', side_effect=AssertionError('must retain owned port')), \
                        patch.object(launcher, 'run', side_effect=['running-web', '']) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(launcher.main(['start', '--state-dir', d] + (['--no-build'] if no_build else [])), 0)
                self.assertEqual(run.call_count, 2)
                command = run.call_args_list[-1].args[0]
                self.assertIn('--wait', command)
                self.assertIn('--no-build' if no_build else '--build', command)
                self.assertEqual(run.call_args.kwargs['env']['PORT'], str(state['port']))
                self.assertEqual(launcher.read_state(directory), state)
                self.assertEqual((directory/'initial_admin_password').read_text(), 'private-test-sentinel')

    def test_running_start_propagates_readiness_failure(self):
        with tempfile.TemporaryDirectory() as d:
            self.saved_workspace(Path(d))
            with patch.object(launcher, 'require_local_docker'), \
                    patch.object(launcher, 'check_ownership'), \
                    patch.object(launcher, 'run', side_effect=['running-web',
                        subprocess.CalledProcessError(1, ['docker', 'compose', 'up'])]), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaises(subprocess.CalledProcessError):
                launcher.main(['start', '--state-dir', d, '--no-build'])

    def test_doctor_without_state_does_not_initialize_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)/'not-created'
            with patch.object(launcher, 'require_local_docker'), \
                    patch.object(launcher, 'available_port', return_value=49152), \
                    patch.object(launcher, 'run', return_value='2.40.3') as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.main(['doctor', '--state-dir', str(directory)]), 0)
            self.assertFalse(directory.exists())
            self.assertEqual(run.call_args.args[0], ['docker', 'compose', 'version', '--short'])
            self.assertEqual(run.call_count, 1)

    def test_doctor_rejects_legacy_compose(self):
        with patch.object(launcher, 'require_local_docker'), \
                patch.object(launcher, 'run', return_value='1.29.2'), \
                patch.object(launcher, 'available_port') as port, \
                contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(ValueError, 'Compose v2'):
            launcher.doctor(Path('/unused'), None)
        port.assert_not_called()

    def test_doctor_retained_state_does_not_read_or_change_passwords(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            state = self.saved_workspace(directory)
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            read_text = Path.read_text
            def guarded(path, *args, **kwargs):
                if path.name in ('db_password', 'initial_admin_password'):
                    self.fail('doctor must not read password contents')
                return read_text(path, *args, **kwargs)
            output = io.StringIO()
            with patch.object(Path, 'read_text', guarded), \
                    patch.object(launcher, 'require_local_docker'), \
                    patch.object(launcher, 'check_ownership') as ownership, \
                    patch.object(launcher, 'available_port', return_value=49153), \
                    patch.object(launcher, 'run', side_effect=['2.40.3', '']) as run, \
                    contextlib.redirect_stdout(output):
                self.assertEqual(launcher.main(['doctor', '--state-dir', d]), 0)
            ownership.assert_called_once_with(state)
            self.assertEqual(run.call_args.args[0], ['docker', 'compose', 'config', '--quiet'])
            self.assertNotIn('private-test-sentinel', output.getvalue())
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)

    def test_doctor_missing_retained_file_does_not_replace_it(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            state = self.saved_workspace(directory)
            (directory/'initial_admin_password').unlink()
            with patch.object(launcher, 'require_local_docker'), \
                    patch.object(launcher, 'check_ownership'), \
                    patch.object(launcher, 'available_port', return_value=49153), \
                    patch.object(launcher, 'run', return_value='2.40.3') as run, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(ValueError, 'initial_admin_password'):
                launcher.doctor(directory, state)
            self.assertFalse((directory/'initial_admin_password').exists())
            self.assertEqual(run.call_count, 1)

    def test_non_object_runtime_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            for value in (None, [], 3, 'invalid'):
                with self.subTest(value=value):
                    (directory/'runtime.json').write_text(json.dumps(value))
                    with self.assertRaisesRegex(ValueError, 'runtime metadata'):
                        launcher.read_state(directory)


if __name__ == '__main__':
    unittest.main()
