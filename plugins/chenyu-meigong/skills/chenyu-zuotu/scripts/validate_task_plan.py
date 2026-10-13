#!/usr/bin/env python3
"""Validate explicit brief-to-output routing without interpreting image content."""
import argparse
import json
from pathlib import Path


def ids(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value)
            and len(set(value)) == len(value))


def validate(data):
    errors, warnings = [], []
    tasks = data.get('tasks', [])
    if not isinstance(tasks, list) or not tasks:
        return {'valid': False, 'errors': ['tasks must be a non-empty list'], 'warnings': []}
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or not isinstance(task.get('id'), str) or not task['id'].strip():
            errors.append('each task requires an id')
            continue
        if task['id'] in by_id:
            errors.append('duplicate task id: ' + task['id'])
        by_id[task['id']] = task
    blocks = data.get('brief_blocks')
    if blocks is None:
        warnings.append('legacy plan: brief-to-output routing not checked')
    elif not isinstance(blocks, list) or not blocks:
        errors.append('brief_blocks must be a non-empty list')
    else:
        seen_blocks, routed = set(), set()
        for block in blocks:
            if not isinstance(block, dict):
                errors.append('brief_blocks entries must be objects')
                continue
            bid = block.get('id')
            if not isinstance(bid, str) or not bid.strip() or bid in seen_blocks:
                errors.append('brief block id must be non-empty and unique')
                continue
            seen_blocks.add(bid)
            products, outputs = block.get('product_ids'), block.get('outputs')
            if not ids(products) or not isinstance(outputs, list) or not outputs:
                errors.append(bid + ': product_ids and outputs must be non-empty')
                continue
            covered = []
            for output in outputs:
                if not isinstance(output, dict) or not ids(output.get('product_ids')):
                    errors.append(bid + ': each output requires product_ids')
                    continue
                covered.extend(output['product_ids'])
                tid = output.get('task_id')
                if not isinstance(tid, str) or tid not in by_id:
                    errors.append(bid + ': missing planned task ' + str(tid))
                    continue
                if tid in routed:
                    errors.append(bid + ': output task routed more than once: ' + tid)
                routed.add(tid)
                task = by_id[tid]
                actual = task.get('product_ids', [task.get('product_id')])
                if not ids(actual) or set(actual) != set(output['product_ids']):
                    errors.append(tid + ': product routing differs from brief')
                if task.get('product_id') is not None and actual != [task['product_id']]:
                    errors.append(tid + ': product_id conflicts with product_ids')
                if task.get('brief_task_id') != bid:
                    errors.append(tid + ': brief_task_id differs from source block')
            if sorted(covered) != sorted(products) or len(set(covered)) != len(covered):
                errors.append(bid + ': outputs must cover each product exactly once')
        gallery = {tid for tid, task in by_id.items() if task.get('content_type', 'gallery') == 'gallery'}
        for tid in sorted(gallery - routed):
            errors.append('gallery task is absent from brief_blocks: ' + tid)
    return {'valid': not errors, 'errors': errors, 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    result = validate(json.loads(args.manifest.read_text(encoding='utf-8')))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
