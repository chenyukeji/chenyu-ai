#!/usr/bin/env python3
"""Fast-forward the published plugin checkout and refresh verified Codex caches."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


NAMES = ('chenyu-kaifa', 'chenyu-yunying', 'chenyu-meigong', 'chenyu-caigou')
VERSION = re.compile(r'\d+\.\d+\.\d+\Z')


def command(args: list[str], *, timeout: int = 120) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f'{" ".join(args[:4])} failed ({result.returncode}): {detail}')
    return result.stdout.strip()


def git(repo: Path, *args: str) -> str:
    return command(['git', '-C', str(repo), *args])


def file_hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def validate_plugins(root: Path) -> dict[str, str]:
    versions = {}
    for name in NAMES:
        path = root / 'plugins' / name
        outer = json.loads((path / 'plugin.json').read_text(encoding='utf-8'))
        inner = json.loads((path / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
        version = outer.get('version')
        if outer.get('name') != name or inner.get('name') != name:
            raise RuntimeError(f'{name}: plugin name mismatch')
        if not isinstance(version, str) or not VERSION.fullmatch(version) or inner.get('version') != version:
            raise RuntimeError(f'{name}: expected equal plain semantic versions in both manifests')
        if not list((path / 'skills').glob('*/SKILL.md')):
            raise RuntimeError(f'{name}: no usable skill')
        versions[name] = version
    return versions


def validate_remote(repo: Path, revision: str) -> dict[str, str]:
    temporary = Path(tempfile.mkdtemp(prefix='chenyu-plugin-release-'))
    stage = temporary / 'checkout'
    try:
        git(repo, 'worktree', 'add', '--detach', '--quiet', str(stage), revision)
        return validate_plugins(stage)
    finally:
        try:
            if (stage / '.git').exists():
                git(repo, 'worktree', 'remove', '--force', str(stage))
        finally:
            shutil.rmtree(temporary)


def install_plugins(repo: Path, market: Path, cache: Path, codex: str, versions: dict[str, str]) -> None:
    for name in NAMES:
        source = repo / 'plugins' / name
        entry = market / name
        if not entry.is_symlink() or entry.resolve() != source.resolve():
            raise RuntimeError(f'{name}: marketplace entry must link to {source}')

    for name in NAMES:
        source = repo / 'plugins' / name
        installed = cache / name / versions[name]
        expected = file_hashes(source)
        if installed.is_dir() and file_hashes(installed) == expected:
            continue
        command([codex, 'plugin', 'add', f'{name}@personal', '--json'])
        if not installed.is_dir() or file_hashes(installed) != expected:
            # Some Codex versions keep a same-version cache; force one clean reinstall.
            command([codex, 'plugin', 'remove', f'{name}@personal', '--json'])
            command([codex, 'plugin', 'add', f'{name}@personal', '--json'])
        if not installed.is_dir() or file_hashes(installed) != expected:
            raise RuntimeError(f'{name}: installed files differ from Git source')

    # Only remove old versions after every replacement has passed verification.
    for name in NAMES:
        folder = cache / name
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.name != versions[name]:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)


def save_status(path: Path, state: str, **details: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    data = {
        'state': state,
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'last_success_at': previous.get('last_success_at'),
        **details,
    }
    if state == 'current':
        data['last_success_at'] = data['checked_at']
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def sync(repo: Path, market: Path, cache: Path, codex: str, status: Path) -> int:
    lock = status.with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another plugin sync is running; skipped')
            return 0
        try:
            if git(repo, 'symbolic-ref', '--short', 'HEAD') != 'main':
                raise RuntimeError('plugin checkout must be on main')
            git(repo, 'fetch', '--quiet', 'origin', 'main')
            local = git(repo, 'rev-parse', 'HEAD')
            remote = git(repo, 'rev-parse', 'origin/main')
            if git(repo, 'status', '--porcelain'):
                save_status(status, 'deferred_dirty', local_revision=local, remote_revision=remote)
                print('Plugin checkout has local changes; update deferred')
                return 0
            ancestor = subprocess.run(
                ['git', '-C', str(repo), 'merge-base', '--is-ancestor', local, remote],
                timeout=30,
                check=False,
            )
            if ancestor.returncode:
                raise RuntimeError('local main is ahead of or diverged from origin/main; refusing to overwrite')
            if local != remote:
                versions = validate_remote(repo, remote)
                git(repo, 'merge', '--ff-only', 'origin/main')
            else:
                versions = validate_plugins(repo)
            active = git(repo, 'rev-parse', 'HEAD')
            if active != remote:
                raise RuntimeError('checkout did not reach the fetched remote revision')
            install_plugins(repo, market, cache, codex, versions)
            save_status(status, 'current', revision=active, versions=versions)
            print(f'Plugins current at {active}: {versions}')
            return 0
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            save_status(status, 'error', error=str(exc))
            print(f'Plugin sync failed: {exc}', file=sys.stderr)
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('/home/ubuntu/chenyu/chenyu-ai'))
    parser.add_argument('--market', type=Path, default=Path('/home/ubuntu/plugins'))
    parser.add_argument('--cache', type=Path, default=Path('/home/ubuntu/.codex/plugins/cache/personal'))
    parser.add_argument('--codex', default='/usr/bin/codex')
    parser.add_argument('--status', type=Path, default=Path('/home/ubuntu/chenyu/chenyu-runtime/plugin-sync-status.json'))
    args = parser.parse_args()
    return sync(args.repo.resolve(), args.market.resolve(), args.cache.resolve(), args.codex, args.status)


if __name__ == '__main__':
    raise SystemExit(main())
