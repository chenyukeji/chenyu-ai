"""Exercise remote plugin updates without GitHub or a real Codex install."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sync_remote_plugins.py'
SPEC = importlib.util.spec_from_file_location('sync_remote_plugins', SCRIPT)
assert SPEC and SPEC.loader
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


def git(folder: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(folder), *args], text=True).strip()


class RemoteSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.seed = root / 'seed'
        self.remote = root / 'remote.git'
        self.live = root / 'live'
        self.market = root / 'market'
        self.cache = root / 'cache'
        self.status = root / 'status.json'
        self.market.mkdir()
        self.cache.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.seed)], check=True)
        git(self.seed, 'config', 'user.name', 'Test')
        git(self.seed, 'config', 'user.email', 'test@example.com')
        for name in SYNC.NAMES:
            self.write_plugin(name, '1.0.0')
        self.commit('Initial plugins')
        subprocess.run(['git', 'clone', '-q', '--bare', str(self.seed), str(self.remote)], check=True)
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(self.live)], check=True)
        for name in SYNC.NAMES:
            (self.market / name).symlink_to(self.live / 'plugins' / name, target_is_directory=True)
            shutil.copytree(self.live / 'plugins' / name, self.cache / name / '1.0.0')
        self.fake_codex = root / 'fake-codex'
        self.fake_codex.write_text('''#!/usr/bin/env python3
import json, os, shutil, sys
from pathlib import Path
name = sys.argv[3].split('@')[0]
market = Path(os.environ['TEST_MARKET']) / name
cache = Path(os.environ['TEST_CACHE']) / name
if sys.argv[2] == 'remove':
    shutil.rmtree(cache, ignore_errors=True)
    print('{}')
else:
    version = json.loads((market / 'plugin.json').read_text())['version']
    shutil.copytree(market, cache / version, dirs_exist_ok=True)
    print(json.dumps({'version': version, 'installedPath': str(cache / version)}))
''')
        self.fake_codex.chmod(0o755)
        self.environment = patch.dict(os.environ, TEST_MARKET=str(self.market), TEST_CACHE=str(self.cache))
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_plugin(self, name: str, version: str) -> None:
        root = self.seed / 'plugins' / name
        (root / '.codex-plugin').mkdir(parents=True, exist_ok=True)
        (root / 'skills' / name).mkdir(parents=True, exist_ok=True)
        manifest = json.dumps({'name': name, 'version': version}) + '\n'
        (root / 'plugin.json').write_text(manifest)
        (root / '.codex-plugin/plugin.json').write_text(manifest)
        (root / 'skills' / name / 'SKILL.md').write_text(f'# {name} {version}\n')

    def commit(self, message: str) -> None:
        git(self.seed, 'add', '.')
        git(self.seed, 'commit', '-q', '-m', message)

    def publish(self) -> None:
        git(self.seed, 'remote', 'add', 'origin', str(self.remote)) if not git(self.seed, 'remote') else None
        git(self.seed, 'push', '-q', 'origin', 'main')

    def run_sync(self) -> int:
        return SYNC.sync(self.live, self.market, self.cache, str(self.fake_codex), self.status)

    def test_fast_forwards_and_replaces_old_cache(self) -> None:
        for name in SYNC.NAMES:
            self.write_plugin(name, '1.0.1')
        self.commit('Release 1.0.1')
        self.publish()
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual(git(self.live, 'rev-parse', 'HEAD'), git(self.seed, 'rev-parse', 'HEAD'))
        for name in SYNC.NAMES:
            self.assertEqual([path.name for path in (self.cache / name).iterdir()], ['1.0.1'])
            self.assertEqual(SYNC.file_hashes(self.live / 'plugins' / name), SYNC.file_hashes(self.cache / name / '1.0.1'))
        self.assertEqual(json.loads(self.status.read_text())['state'], 'current')

    def test_dirty_checkout_is_not_overwritten(self) -> None:
        original = git(self.live, 'rev-parse', 'HEAD')
        for name in SYNC.NAMES:
            self.write_plugin(name, '1.0.1')
        self.commit('Release 1.0.1')
        self.publish()
        (self.live / 'plugins' / SYNC.NAMES[0] / 'plugin.json').write_text('{"local": "change"}')
        self.assertEqual(self.run_sync(), 0)
        self.assertEqual(git(self.live, 'rev-parse', 'HEAD'), original)
        self.assertEqual(json.loads(self.status.read_text())['state'], 'deferred_dirty')

    def test_rejects_suffixed_remote_version_before_activation(self) -> None:
        original = git(self.live, 'rev-parse', 'HEAD')
        for name in SYNC.NAMES:
            self.write_plugin(name, '1.0.1+codex.timestamp')
        self.commit('Invalid release')
        self.publish()
        self.assertEqual(self.run_sync(), 1)
        self.assertEqual(git(self.live, 'rev-parse', 'HEAD'), original)
        self.assertEqual(json.loads(self.status.read_text())['state'], 'error')


if __name__ == '__main__':
    unittest.main()
