#!/usr/bin/env python3
"""Read-only local image checks. Does not certify visual or marketplace compliance."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image


def check(manifest):
    data = json.loads(manifest.read_text(encoding='utf-8'))
    results = []
    seen_ids, seen_hashes = set(), {}
    for task in data.get('tasks', []):
        issues = []
        tid = task.get('id')
        if not tid or tid in seen_ids:
            issues.append('missing or duplicate task id')
        seen_ids.add(tid)
        final = task.get('final_path')
        item = {'id': tid, 'issues': issues, 'scope': 'file properties only'}
        if not final:
            issues.append('no local final_path; file properties unverified')
        else:
            path = Path(final)
            if not path.is_absolute():
                path = manifest.parent / path
            item['path'] = str(path.resolve())
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in seen_hashes:
                    issues.append('identical image also used by task ' + str(seen_hashes[digest]) + '; verify intentional reuse')
                seen_hashes[digest] = tid
                with Image.open(path) as img:
                    img.load()
                    item.update(width=img.width, height=img.height, format=img.format)
                    expected = task.get('output', {})
                    for key, actual in [('width', img.width), ('height', img.height)]:
                        if expected.get(key) is None:
                            issues.append('missing expected ' + key)
                        elif expected[key] != actual:
                            issues.append(f'{key}: expected {expected[key]}, got {actual}')
                    fmt = expected.get('format')
                    if not fmt:
                        issues.append('missing expected format')
                    fmt = 'JPEG' if str(fmt).upper() == 'JPG' else str(fmt).upper()
                    if fmt != 'NONE' and fmt != img.format:
                        issues.append(f'format: expected {fmt}, got {img.format}')
                    extensions = {'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'}, 'WEBP': {'.webp'}}
                    if img.format in extensions and path.suffix.lower() not in extensions[img.format]:
                        issues.append('filename extension does not match image encoding')
            except (OSError, ValueError) as exc:
                issues.append('cannot read output: ' + str(exc))
        item['status'] = 'needs_review' if issues else 'pass'
        results.append(item)
    return {'scope': 'local file properties only; visual review required separately', 'task_count': len(results), 'all_file_checks_pass': bool(results) and all(r['status'] == 'pass' for r in results), 'results': results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = check(args.manifest.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'task_count': result['task_count'], 'all_file_checks_pass': result['all_file_checks_pass'], 'report': str(args.out.resolve())}))
    raise SystemExit(0 if result['all_file_checks_pass'] else 1)


if __name__ == '__main__':
    main()
