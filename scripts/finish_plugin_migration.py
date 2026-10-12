#!/usr/bin/env python3
"""Finish the first pinned-plugin rollout after legacy executions drain."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

import sync_remote_plugins as syncer


def finish_once(repo, bootstrap, alias, market, cache, codex, status, releases, jobs):
    with syncer.execution_versions_lock(releases):
        if syncer.legacy_running_jobs(jobs):
            return False
    if syncer.sync(repo, market, cache, codex, status, releases, jobs):
        raise RuntimeError('Plugin source synchronization failed')
    if json.loads(status.read_text()).get('state') != 'current':
        return False
    with syncer.execution_versions_lock(releases):
        if not alias.is_symlink() or alias.resolve() not in {bootstrap.resolve(), repo.resolve()}:
            raise RuntimeError('Unexpected plugin source alias; refusing to overwrite')
        if bootstrap.resolve() == repo.resolve():
            raise RuntimeError('Bootstrap source must be a separate worktree')
        temporary = alias.with_name(alias.name + '.next')
        temporary.symlink_to(repo, target_is_directory=True)
        temporary.replace(alias)
        if bootstrap.exists():
            syncer.git(repo, 'worktree', 'remove', str(bootstrap))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['repo', 'bootstrap', 'alias', 'market', 'cache', 'status', 'releases', 'jobs', 'worker_dir', 'record']:
        parser.add_argument('--' + name.replace('_', '-'), required=True, type=Path)
    parser.add_argument('--codex', default='/usr/bin/codex')
    parser.add_argument('--bridge-unit', default='chenyu-plugin-hot-update-ready.service')
    args = parser.parse_args()
    while not finish_once(args.repo, args.bootstrap, args.alias, args.market, args.cache,
                          args.codex, args.status, args.releases, args.jobs):
        time.sleep(5)
    # Standard workers are already restarting gracefully. Retire the bridge only
    # once both replacements have started; its own jobs also drain gracefully.
    for unit in ['chenyu-worker.service', 'chenyu-worker-parallel.service']:
        while True:
            pid = int(subprocess.check_output(['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True))
            try:
                ready = pid > 0 and (Path('/proc') / str(pid) / 'cwd').resolve(strict=True) == args.worker_dir.resolve()
            except OSError:
                ready = False
            if ready:
                break
            time.sleep(5)
    subprocess.run(['sudo', '-n', 'systemctl', 'stop', '--no-block', args.bridge_unit], check=True)
    args.record.write_text(json.dumps({'state': 'complete', 'revision': syncer.git(args.repo, 'rev-parse', 'HEAD'),
                                      'finished_at': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n')
    print('Legacy plugin source retired; standard workers use pinned plugin releases.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
