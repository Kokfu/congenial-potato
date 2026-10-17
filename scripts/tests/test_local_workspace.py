import importlib.util
import json
import os
from pathlib import Path
import socket
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


if __name__ == '__main__':
    unittest.main()
