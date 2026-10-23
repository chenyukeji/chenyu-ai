import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-meigong/skills/chenyu-zuotu/scripts/check_outputs.py'
SPEC = importlib.util.spec_from_file_location('incremental_image_outputs', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def prepare(tmp_path):
    (tmp_path / 'in').mkdir()
    (tmp_path / 'out').mkdir()
    tasks = []
    for number in range(9):
        preserved = number < 7
        size = (12, 12) if number in (1, 4) else (16, 16)
        name = f'{number + 1:02}.png'
        target = tmp_path / 'out' / name
        Image.new('RGB', size, (number * 25, 40, 90)).save(target)
        task = {'task_id': f'image-{number + 1:03}', 'final_path': 'out/' + name,
                'product_ids': [f'variant-{max(1, number - 5)}'],
                'output': {'width': size[0], 'height': size[1], 'format': 'PNG'}}
        if preserved:
            shutil.copyfile(target, tmp_path / 'in' / name)
            task.update(preserved_from_baseline=True, baseline_file='in/' + name)
        tasks.append(task)
    manifest = tmp_path / 'tasks.json'
    manifest.write_text(json.dumps({'tasks': tasks}))
    return manifest, tasks


def test_incremental_set_preserves_seven_and_adds_two_with_host_ids(tmp_path):
    manifest, _ = prepare(tmp_path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    result = MODULE.check(manifest)
    assert result['all_file_checks_pass']
    assert result['task_count'] == 9
    assert [r['id'] for r in result['results']] == [f'image-{i:03}' for i in range(1, 10)]
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before


def test_unrequested_change_to_preserved_image_is_reported(tmp_path):
    manifest, _ = prepare(tmp_path)
    Image.new('RGB', (16, 16), 'red').save(tmp_path / 'out/01.png')
    result = MODULE.check(manifest)
    assert not result['all_file_checks_pass']
    assert 'preserved image differs from baseline' in result['results'][0]['issues']
    assert all(r['status'] == 'pass' for r in result['results'][1:])


def test_copied_original_cannot_count_as_new_variant(tmp_path):
    manifest, _ = prepare(tmp_path)
    shutil.copyfile(tmp_path / 'in/01.png', tmp_path / 'out/08.png')
    result = MODULE.check(manifest)
    assert not result['all_file_checks_pass']
    assert any('identical image' in issue for issue in result['results'][7]['issues'])


def test_id_aliases_remain_unique_and_legacy_ids_still_work(tmp_path):
    manifest, tasks = prepare(tmp_path)
    for task in tasks:
        task['id'] = task.pop('task_id')
    manifest.write_text(json.dumps({'tasks': tasks}))
    assert MODULE.check(manifest)['all_file_checks_pass']
    tasks[7]['task_id'] = tasks[7]['id']
    manifest.write_text(json.dumps({'tasks': tasks}))
    assert MODULE.check(manifest)['all_file_checks_pass']
    tasks[8]['task_id'] = tasks[7]['id']
    manifest.write_text(json.dumps({'tasks': tasks}))
    result = MODULE.check(manifest)
    assert not result['all_file_checks_pass']
    assert 'conflicting id and task_id' in result['results'][8]['issues']
    assert 'missing or duplicate task id' in result['results'][8]['issues']


def test_new_variant_size_and_missing_output_still_fail(tmp_path):
    manifest, tasks = prepare(tmp_path)
    tasks[7]['output']['width'] = 20
    (tmp_path / 'out/09.png').unlink()
    manifest.write_text(json.dumps({'tasks': tasks}))
    result = MODULE.check(manifest)
    assert not result['all_file_checks_pass']
    assert 'width: expected 20, got 16' in result['results'][7]['issues']
    assert any('cannot read output' in issue for issue in result['results'][8]['issues'])
