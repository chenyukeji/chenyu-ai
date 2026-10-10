"""Validate image brief content and visual evidence independently."""
import argparse
import json
import re
import unicodedata
from pathlib import Path


IMAGE_TEXT_KEYS = {'on_image_text', 'image_text', 'overlay_text', '上图文字', '图片文案'}
COPY_FIELD_STRUCTURE = re.compile(
    r'(?i)\b(?:search terms|seo keywords?|keyword coverage|bullet point [1-5]|bullet [1-5])\b'
    r'|(?:搜索词|关键词覆盖|五点[一二三四五1-5]|卖点[一二三四五1-5])'
)
REFERENCE_NARRATION = re.compile(
    r'(?:参考图(?:片)?\s*\d*\s*(?:用于|作为|展示|提供)|'
    r'按照参考图(?:片)?|照着参考图(?:片)?|同款产品参考|版式参考)'
)
MAIN_STYLES = {'clean_white', 'white_with_use_inset', 'scene_hero'}
IDENTITY_LOCK_FIELDS = (
    'shape_structure', 'color_pattern', 'quantity_components',
    'accessories_packaging',
)
MEASUREMENT = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)(?:\s*[–—−-]\s*(\d+(?:\.\d+)?))?\s*(cm|in)\b', re.I)


def dimension_label_error(label):
    values = {'cm': [], 'in': []}
    for first, second, unit in MEASUREMENT.findall(label):
        values[unit.lower()].append([float(first)] + ([float(second)] if second else []))
    if len(values['cm']) != 1 or len(values['in']) != 1:
        return 'must pair one cm value/range with one in value/range'
    if len(values['cm'][0]) != len(values['in'][0]):
        return 'cm and in ranges must have the same number of endpoints'
    if any(abs(cm / 2.54 - inch) > 0.06
           for cm, inch in zip(values['cm'][0], values['in'][0])):
        return 'cm and in values do not convert using 2.54'
    return ''


def words(value):
    return re.findall(
        r'[^\W_]+', unicodedata.normalize('NFC', str(value)).casefold(), re.UNICODE
    )


def walk_strings(value, path='$'):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_strings(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_strings(item, f'{path}[{index}]')
    elif isinstance(value, str) and value.strip():
        yield path, value.strip()


def _non_empty_strings(value):
    return (
        isinstance(value, list) and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _mapping_sources(tasks, task_ids, field, image_id):
    values = set()
    for task_id in task_ids:
        task = tasks.get(task_id, {})
        items = list(task.get(field, []))
        if field == 'text_mappings':
            items.extend(task.get('scene_cells', []))
        for item in items:
            if isinstance(item, dict) and item.get('source_image_id') == image_id:
                source_key = 'source_content' if field == 'content_mappings' else 'source_text'
                output_key = 'output_content' if field == 'content_mappings' else 'output_text'
                if str(item.get(source_key, '')).strip() and str(item.get(output_key, '')).strip():
                    values.add(str(item[source_key]).strip())
    return values


def validate_visual_contract(image_brief, errors):
    """Validate product identity, task planning and all reference inventories."""
    if not isinstance(image_brief, dict):
        errors.append('$ image brief must be an object')
        return

    products = image_brief.get('products')
    if not isinstance(products, list) or not products:
        errors.append('$.products must contain at least one product from 产品内容')
        return
    product_images = {}
    product_image_sources = {}
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            errors.append(f'$.products[{index}] must be an object')
            continue
        product_id = str(product.get('id', '')).strip()
        image_id = str(product.get('product_content_image_id', '')).strip()
        if not product_id or not image_id:
            errors.append(
                f'$.products[{index}] requires id and product_content_image_id'
            )
            continue
        if product_id in product_images:
            errors.append(f'$.products contains duplicate id: {product_id}')
        product_images[product_id] = image_id
        image_source = str(product.get('product_content_image_source', '')).strip()
        if image_source not in ('own_main', 'supplier', 'confirmed_reference_main', 'first_reference_main'):
            errors.append(
                f'$.products[{index}].product_content_image_source must be '
                'own_main, supplier, or confirmed_reference_main (legacy first_reference_main accepted)'
            )
        source_ref = str(product.get('product_content_image_source_ref', '')).strip()
        if not source_ref:
            errors.append(f'$.products[{index}].product_content_image_source_ref is required')
        product_image_sources[product_id] = (image_source, source_ref)
        if not str(product.get('visual_direction', '')).strip():
            errors.append(f'$.products[{index}].visual_direction is required')
        if image_source in ('confirmed_reference_main', 'first_reference_main'):
            if not str(product.get('matching_basis', '')).strip():
                errors.append(f'$.products[{index}].matching_basis is required for reference identity')
        if 'own_main_image_id' not in product or 'supplier_image_id' not in product:
            errors.append(
                f'$.products[{index}] must record own_main_image_id and '
                'supplier_image_id candidate checks (empty when unavailable)'
            )
        own_main_id = str(product.get('own_main_image_id', '')).strip()
        supplier_id = str(product.get('supplier_image_id', '')).strip()
        expected_source = 'own_main' if own_main_id else (
            'supplier' if supplier_id else image_source
        )
        if image_source != expected_source or (not own_main_id and not supplier_id
                and image_source not in ('confirmed_reference_main', 'first_reference_main')):
            errors.append(
                f'$.products[{index}] must choose image source in '
                'own_main → supplier → confirmed_reference_main order'
            )
        if own_main_id and image_id != own_main_id:
            errors.append(f'$.products[{index}] must use its own_main_image_id')
        elif not own_main_id and supplier_id and image_id != supplier_id:
            errors.append(f'$.products[{index}] must use its supplier_image_id')

    task_list = image_brief.get('image_tasks')
    if not isinstance(task_list, list) or not task_list:
        errors.append('$.image_tasks must contain the actual dynamic image plan')
        return
    tasks = {}
    for index, task in enumerate(task_list):
        if not isinstance(task, dict):
            errors.append(f'$.image_tasks[{index}] must be an object')
            continue
        task_id = str(task.get('id', '')).strip()
        if not task_id:
            errors.append(f'$.image_tasks[{index}] requires id')
            continue
        if task_id in tasks:
            errors.append(f'$.image_tasks contains duplicate id: {task_id}')
        tasks[task_id] = task
        for field in ('buyer_question', 'new_information'):
            if not str(task.get(field, '')).strip():
                errors.append(f'$.image_tasks[{index}].{field} is required')
        instructions = str(task.get('instructions', ''))
        if not instructions.strip():
            errors.append(f'$.image_tasks[{index}].instructions is required')
        if REFERENCE_NARRATION.search(instructions):
            errors.append(
                f'$.image_tasks[{index}].instructions narrates source-image usage; '
                'describe the final composition and content directly'
            )
        product_ids = task.get('product_ids')
        if not _non_empty_strings(product_ids):
            errors.append(f'$.image_tasks[{index}].product_ids must be non-empty')
            product_ids = []
        unknown_products = [item for item in product_ids if item not in product_images]
        if unknown_products:
            errors.append(
                f'$.image_tasks[{index}] references unknown products: '
                + ', '.join(unknown_products)
            )

    for product in products:
        if not isinstance(product, dict) or product.get('id') not in product_images:
            continue
        product_id = product['id']
        product_tasks = [
            task for task in tasks.values()
            if product_id in task.get('product_ids', [])
        ]
        if not 6 <= len(product_tasks) <= 8 and not str(product.get('task_count_reason', '')).strip():
            errors.append(
                f'$.image_tasks must contain 6-8 tasks for product {product_id}; '
                f'found {len(product_tasks)}; otherwise provide task_count_reason'
            )
        task_types = [task.get('type') for task in product_tasks]
        if not task_types or task_types[0] != 'main_image' or task_types.count('main_image') != 1:
            errors.append(f'$.image_tasks for product {product_id} must start with exactly one main_image')
        seen_information = set()
        for task in product_tasks:
            information = ' '.join(words(task.get('new_information', '')))
            if information and information in seen_information:
                errors.append(f'$.image_tasks for product {product_id} repeats new_information: {task["id"]}')
            seen_information.add(information)

    for task_id, task in tasks.items():
        task_type = task.get('type')
        if task_type not in {'main_image', 'detail', 'feature', 'advantage', 'process', 'packaging', 'size', 'scene', 'closeup_scene', 'key_scene', 'four_grid'}:
            errors.append(f'$.image_tasks[{task_id}] has unsupported type: {task_type}')
        if task_type in ('scene', 'closeup_scene', 'key_scene'):
            if not str(task.get('scene_mode', '')).strip():
                errors.append(
                    f'$.image_tasks[{task_id}] {task_type} requires scene_mode'
                )
        instructions = str(task.get('instructions', ''))
        on_image_text = str(task.get('on_image_text', ''))
        if task_type == 'size':
            evidence = task.get('dimension_source', {})
            if not isinstance(evidence, dict) or evidence.get('kind') not in (
                    'own_measurement', 'development', 'confirmed_same_product') or not str(evidence.get('source_ref', '')).strip():
                errors.append(f'$.image_tasks[{task_id}] requires dimension_source from own or confirmed same-product evidence')
            elif evidence['kind'] == 'confirmed_same_product' and not str(evidence.get('matching_basis', '')).strip():
                errors.append(f'$.image_tasks[{task_id}] dimension_source requires matching_basis')
            support = task.get('supporting_visual')
            if not isinstance(support, dict):
                errors.append(
                    f'$.image_tasks[{task_id}] size task requires supporting_visual'
                )
            else:
                kind = support.get('kind')
                if kind not in ('detail', 'scene', 'both', 'none'):
                    errors.append(
                        f'$.image_tasks[{task_id}].supporting_visual.kind must be '
                        'detail, scene, both, or none'
                    )
                elif kind != 'none':
                    description = str(support.get('description', '')).strip()
                    if not description or not str(support.get('source_ref', '')).strip():
                        errors.append(
                            f'$.image_tasks[{task_id}] supporting_visual requires '
                            'description and source_ref'
                        )
                    if not str(support.get('dimension_relevance', '')).strip():
                        errors.append(f'$.image_tasks[{task_id}] supporting_visual requires dimension_relevance')
                    if description and description not in instructions:
                        errors.append(
                            f'$.image_tasks[{task_id}] final instructions omit '
                            f'supporting visual: {description}'
                        )
                    for other_id, other in tasks.items():
                        if other_id == task_id or not isinstance(other, dict):
                            continue
                        own_products = task.get('product_ids', [])
                        other_products = other.get('product_ids', [])
                        if not isinstance(own_products, list) or not isinstance(other_products, list):
                            continue
                        if not set(item for item in own_products if isinstance(item, str)).intersection(
                                item for item in other_products if isinstance(item, str)):
                            continue
                        if description and description.casefold() in str(
                                other.get('instructions', '')).casefold():
                            errors.append(
                                f'$.image_tasks[{task_id}] supporting visual '
                                f'repeats task {other_id}: {description}'
                            )
            heading = task.get('size_heading', 'Product Size')
            override_reason = str(task.get('size_heading_override_reason', '')).strip()
            if heading != 'Product Size' and not override_reason:
                errors.append(
                    f'$.image_tasks[{task_id}] size heading override requires '
                    'size_heading_override_reason citing the user request'
                )
            if not isinstance(heading, str):
                errors.append(f'$.image_tasks[{task_id}].size_heading must be a string')
            elif heading and (heading not in instructions or heading not in on_image_text):
                errors.append(
                    f'$.image_tasks[{task_id}] size heading {heading!r} must appear '
                    'in final instructions and on_image_text'
                )
            if not _non_empty_strings(task.get('dimension_labels')):
                errors.append(f'$.image_tasks[{task_id}] size task requires dimension_labels')
            else:
                for label in task['dimension_labels']:
                    reason = dimension_label_error(label)
                    if reason:
                        errors.append(f'$.image_tasks[{task_id}] dimension label {label!r} {reason}')
                    if label not in instructions:
                        errors.append(f'$.image_tasks[{task_id}] must include dimension label {label!r} in final instructions')
                    if label not in on_image_text:
                        errors.append(f'$.image_tasks[{task_id}] must include dimension label {label!r} in on_image_text')
        for mapping in task.get('content_mappings', []):
            if not isinstance(mapping, dict):
                continue
            output_content = str(mapping.get('output_content', '')).strip()
            if output_content and output_content not in instructions:
                errors.append(f'$.image_tasks[{task_id}] final instructions omit mapped content: {output_content}')
        for mapping in task.get('text_mappings', []):
            if not isinstance(mapping, dict):
                continue
            output_text = str(mapping.get('output_text', '')).strip()
            if output_text and output_text not in instructions:
                errors.append(f'$.image_tasks[{task_id}] final instructions omit on-image text: {output_text}')
        if task_type == 'four_grid':
            scene_cells = task.get('scene_cells')
            if not isinstance(scene_cells, list) or len(scene_cells) != 4:
                errors.append(
                    f'$.image_tasks[{task_id}] four_grid task requires exactly '
                    'four scene_cells'
                )
            else:
                for cell in scene_cells:
                    if not isinstance(cell, dict) or not str(cell.get('output_scene', '')).strip():
                        errors.append(f'$.image_tasks[{task_id}] each scene cell requires output_scene')
                        continue
                    for field in ('output_scene', 'output_text'):
                        value = str(cell.get(field, '')).strip()
                        if value and value not in instructions:
                            errors.append(
                                f'$.image_tasks[{task_id}] final instructions omit '
                                f'four-grid {field}: {value}'
                            )

    main_covered = set()
    for task_id, task in tasks.items():
        if task.get('type') != 'main_image':
            continue
        if task.get('main_style') not in MAIN_STYLES:
            errors.append(
                f'$.image_tasks[{task_id}] main_style must be one of: '
                + ', '.join(sorted(MAIN_STYLES))
            )
        if not str(task.get('main_style_reason', '')).strip():
            errors.append(f'$.image_tasks[{task_id}] requires main_style_reason')
        product_ids = task.get('product_ids', [])
        expected_images = {
            product_images[item] for item in product_ids if item in product_images
        }
        actual_images = {
            str(item).strip() for item in task.get('product_image_ids', [])
            if str(item).strip()
        }
        if actual_images != expected_images:
            errors.append(
                f'$.image_tasks[{task_id}] main image product_image_ids must exactly '
                'match 产品内容 images for its products'
            )
        identity_lock = task.get('identity_lock')
        if not isinstance(identity_lock, dict):
            errors.append(f'$.image_tasks[{task_id}] main image requires identity_lock')
        else:
            missing = [
                field for field in IDENTITY_LOCK_FIELDS
                if not str(identity_lock.get(field, '')).strip()
            ]
            if missing:
                errors.append(
                    f'$.image_tasks[{task_id}] identity_lock omits: '
                    + ', '.join(missing)
                )
        if str(task.get('on_image_text', '')).strip():
            errors.append(f'$.image_tasks[{task_id}] main image must have no text')
        main_covered.update(item for item in product_ids if item in product_images)
    missing_main = sorted(set(product_images) - main_covered)
    if missing_main:
        errors.append(
            '$.image_tasks has no main_image task for products: ' + ', '.join(missing_main)
        )

    # primary_reference retains the first inventory for storage compatibility only.
    primary = image_brief.get('primary_reference')
    additional = image_brief.get('additional_references', [])
    if not isinstance(additional, list):
        errors.append('$.additional_references must be a list')
        return
    references = ([] if primary is None else [('$.primary_reference', primary)]) + [
        (f'$.additional_references[{i}]', ref) for i, ref in enumerate(additional)
    ]
    seen_images = {}
    for ref_path, reference in references:
        if not isinstance(reference, dict) or not str(reference.get('asin', '')).strip():
            errors.append(f'{ref_path}.asin is required')
            continue
        status = reference.get('coverage_status')
        if status not in ('complete', 'partial', 'failed'):
            errors.append(f'{ref_path}.coverage_status must be complete, partial, or failed')
        if status in ('partial', 'failed') and not str(reference.get('coverage_note', '')).strip():
            errors.append(f'{ref_path}.coverage_note must describe missing coverage or failure')
        images = reference.get('images')
        if not isinstance(images, list):
            errors.append(f'{ref_path}.images must be a list')
            continue
        if status in ('complete', 'partial') and not images:
            errors.append(f'{ref_path}.images cannot be empty for readable coverage')
        if status == 'failed' and images:
            errors.append(f'{ref_path} has images; use partial coverage instead of failed')
        for index, source in enumerate(images):
            path = f'{ref_path}.images[{index}]'
            if not isinstance(source, dict):
                errors.append(f'{path} must be an object')
                continue
            image_id = str(source.get('id', '')).strip()
            if not image_id or image_id in seen_images:
                errors.append(f'{path}.id is missing or duplicated')
                continue
            seen_images[image_id] = (reference, source)
            task_ids = source.get('mapped_task_ids', [])
            omitted = str(source.get('omitted_reason', '')).strip()
            if bool(task_ids) == bool(omitted):
                errors.append(f'{path} requires mapped_task_ids or a specific omitted_reason')
                continue
            if omitted:
                continue
            if not _non_empty_strings(task_ids) or any(item not in tasks for item in task_ids):
                errors.append(f'{path}.mapped_task_ids must cite existing tasks')
                continue
            omitted_elements = source.get('omitted_elements', [])
            if not isinstance(omitted_elements, list):
                errors.append(f'{path}.omitted_elements must be a list')
                omitted_elements = []
            exclusions = {'content': set(), 'text': set(), 'scene': set()}
            for item in omitted_elements:
                if (not isinstance(item, dict) or item.get('kind') not in exclusions
                        or not str(item.get('value', '')).strip() or not str(item.get('reason', '')).strip()):
                    errors.append(f'{path}.omitted_elements require kind, value and reason')
                    continue
                exclusions[item['kind']].add(item['value'])
            # Omitting a source cell also omits its label when repeated in text_elements.
            scene_labels_omitted = {
                str(cell.get('source_text', '')).strip()
                for cell in source.get('scene_cells', []) if isinstance(cell, dict)
                and cell.get('source_scene') in exclusions['scene']
            }
            for field, source_key, kind, message in (
                    ('content_mappings', 'content_elements', 'content', 'content'),
                    ('text_mappings', 'text_elements', 'text', 'detail text')):
                elements = source.get(source_key, [])
                if not isinstance(elements, list) or (elements and not _non_empty_strings(elements)):
                    errors.append(f'{path}.{source_key} must contain non-empty strings')
                    continue
                mapped = _mapping_sources(tasks, task_ids, field, image_id)
                if exclusions[kind] - set(elements):
                    errors.append(f'{path} has exclusions for unknown {kind}')
                if exclusions[kind] & mapped:
                    errors.append(f'{path} {kind} cannot be both mapped and omitted')
                omitted_values = exclusions[kind] | (scene_labels_omitted if kind == 'text' else set())
                missing = [item for item in elements if item not in mapped | omitted_values]
                if missing:
                    errors.append(f'{path} has unmapped {message}: ' + ', '.join(missing))
            if source.get('role') == 'four_grid':
                cells = source.get('scene_cells', [])
                if not isinstance(cells, list) or len(cells) != 4:
                    errors.append(f'{path} four_grid must record exactly four scene_cells')
                    continue
                target_cells = [cell for task_id in task_ids for cell in tasks[task_id].get('scene_cells', [])
                                if isinstance(cell, dict) and cell.get('source_image_id') == image_id]
                known_scenes = {cell.get('source_scene') for cell in cells if isinstance(cell, dict)}
                if exclusions['scene'] - known_scenes:
                    errors.append(f'{path} has exclusions for unknown scene')
                for cell_index, cell in enumerate(cells):
                    if not isinstance(cell, dict) or not str(cell.get('source_scene', '')).strip():
                        errors.append(f'{path}.scene_cells[{cell_index}] requires source_scene')
                        continue
                    scene, label = cell['source_scene'], str(cell.get('source_text', '')).strip()
                    match = next((item for item in target_cells if item.get('source_scene') == scene
                                  and item.get('source_text', '') == label), None)
                    if scene in exclusions['scene']:
                        if match:
                            errors.append(f'{path} scene cannot be both mapped and omitted: {scene}')
                        continue
                    if not match or not str(match.get('output_scene', '')).strip() or (label and not str(match.get('output_text', '')).strip()):
                        errors.append(f'{path}.scene_cells[{cell_index}] is missing a complete output scene/text mapping')

    for product_id, (image_source, source_ref) in product_image_sources.items():
        if image_source not in ('confirmed_reference_main', 'first_reference_main'):
            continue
        reference, source = seen_images.get(product_images[product_id], ({}, {}))
        if source.get('role') != 'main':
            errors.append(f'$.products[{product_id}] {image_source} image must match a recorded reference main image')
        elif str(reference.get('asin', '')).upper() not in source_ref.upper():
            errors.append(f'$.products[{product_id}] reference source_ref must cite its ASIN')

    # Enforce source identity as well as matching source strings across all links.
    for task_id, task in tasks.items():
        for field in ('content_mappings', 'text_mappings', 'scene_cells'):
            for mapping in task.get(field, []):
                if not isinstance(mapping, dict):
                    errors.append(f'$.image_tasks[{task_id}].{field} entries must be objects')
                    continue
                if field == 'scene_cells' and not mapping.get('source_scene'):
                    continue  # An original scene may have no competitor source.
                image_id = mapping.get('source_image_id')
                _, source = seen_images.get(image_id, ({}, {}))
                if not source or task_id not in source.get('mapped_task_ids', []):
                    errors.append(f'$.image_tasks[{task_id}].{field} requires a mapped source_image_id')
                if field == 'scene_cells':
                    for key in ('output_scene', 'output_text'):
                        value = str(mapping.get(key, '')).strip()
                        if value and value not in str(task.get('instructions', '')):
                            errors.append(f'$.image_tasks[{task_id}] final instructions omit scene {key}: {value}')


def validate(image_brief):
    errors, warnings = [], []
    image_strings = list(walk_strings(image_brief))

    validate_visual_contract(image_brief, errors)

    for path, value in image_strings:
        if COPY_FIELD_STRUCTURE.search(value):
            errors.append(
                f'{path} uses keyword or bullet field structure to drive an image task'
            )
        key = path.rsplit('.', 1)[-1]
        if key in IMAGE_TEXT_KEYS and len(words(value)) > 6:
            warnings.append(
                f'{path} has more than 6 words; default image text should be 1-3 words '
                'or necessary numeric labels'
            )

    return {
        'ready_for_delivery': not errors,
        'errors': errors,
        'warnings': warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image_brief_package', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    image_brief = json.loads(args.image_brief_package.read_text(encoding='utf-8'))
    result = validate(image_brief)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    raise SystemExit(0 if result['ready_for_delivery'] else 1)


if __name__ == '__main__':
    main()
