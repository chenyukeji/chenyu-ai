"""Check that an image brief does not reuse Listing copy or SEO structure."""
import argparse
import json
import re
import unicodedata
from pathlib import Path


LISTING_FIELDS = {'title', 'item_name', 'item_highlights', 'bullets', 'description', 'search_terms'}
IMAGE_TEXT_KEYS = {'on_image_text', 'image_text', 'overlay_text', '上图文字', '图片文案'}
LISTING_STRUCTURE_LEAK = re.compile(
    r'(?i)\b(?:search terms|seo keywords?|keyword coverage|bullet point [1-5]|bullet [1-5])\b'
    r'|(?:搜索词|关键词覆盖|五点[一二三四五1-5]|卖点[一二三四五1-5])'
)
REFERENCE_NARRATION = re.compile(
    r'(?:参考图(?:片)?\s*\d*\s*(?:用于|作为|展示|提供)|'
    r'按照参考图(?:片)?|照着参考图(?:片)?|同款产品参考|版式参考)'
)
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


def listing_strings(value, path='$'):
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f'{path}.{key}'
            if key in LISTING_FIELDS:
                yield from walk_strings(item, next_path)
            else:
                yield from listing_strings(item, next_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from listing_strings(item, f'{path}[{index}]')


def ngrams(value, size=8):
    tokens = words(value)
    return {
        tuple(tokens[index:index + size])
        for index in range(max(0, len(tokens) - size + 1))
    }


def _non_empty_strings(value):
    return (
        isinstance(value, list) and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _mapping_sources(tasks, task_ids, field):
    values = set()
    for task_id in task_ids:
        task = tasks.get(task_id, {})
        for item in task.get(field, []):
            if isinstance(item, dict):
                source_key = 'source_content' if field == 'content_mappings' else 'source_text'
                output_key = 'output_content' if field == 'content_mappings' else 'output_text'
                if str(item.get(source_key, '')).strip() and str(item.get(output_key, '')).strip():
                    values.add(str(item[source_key]).strip())
    return values


def validate_visual_contract(image_brief, errors):
    """Validate product identity and first-link image-content coverage."""
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
        if image_source not in ('own_main', 'supplier', 'first_reference_main'):
            errors.append(
                f'$.products[{index}].product_content_image_source must be '
                'own_main, supplier, or first_reference_main'
            )
        source_ref = str(product.get('product_content_image_source_ref', '')).strip()
        if not source_ref:
            errors.append(f'$.products[{index}].product_content_image_source_ref is required')
        product_image_sources[product_id] = (image_source, source_ref)
        if 'own_main_image_id' not in product or 'supplier_image_id' not in product:
            errors.append(
                f'$.products[{index}] must record own_main_image_id and '
                'supplier_image_id candidate checks (empty when unavailable)'
            )
        own_main_id = str(product.get('own_main_image_id', '')).strip()
        supplier_id = str(product.get('supplier_image_id', '')).strip()
        expected_source = 'own_main' if own_main_id else (
            'supplier' if supplier_id else 'first_reference_main'
        )
        if image_source != expected_source:
            errors.append(
                f'$.products[{index}] must choose image source in '
                'own_main → supplier → first_reference_main order'
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

    for product_id in product_images:
        product_tasks = [
            task for task in task_list
            if isinstance(task, dict) and product_id in task.get('product_ids', [])
        ]
        if not 6 <= len(product_tasks) <= 8:
            errors.append(
                f'$.image_tasks must contain 6-8 tasks for product {product_id}; '
                f'found {len(product_tasks)}'
            )
            continue
        task_types = [task.get('type') for task in product_tasks]
        if task_types[:3] != ['main_image', 'closeup_scene', 'size']:
            errors.append(
                f'$.image_tasks for product {product_id} must start with '
                'main_image, closeup_scene, size'
            )
        if task_types[-2:] != ['key_scene', 'four_grid']:
            errors.append(
                f'$.image_tasks for product {product_id} must end with '
                'key_scene, four_grid'
            )
        middle_types = task_types[3:-2]
        allowed_middle = {'feature', 'advantage', 'process', 'detail'}
        invalid_middle = [item for item in middle_types if item not in allowed_middle]
        if invalid_middle:
            errors.append(
                f'$.image_tasks for product {product_id} has unsupported middle task '
                'types: ' + ', '.join(map(str, invalid_middle))
            )

    for task_id, task in tasks.items():
        task_type = task.get('type')
        if task_type in ('closeup_scene', 'key_scene'):
            if not str(task.get('scene_mode', '')).strip():
                errors.append(
                    f'$.image_tasks[{task_id}] {task_type} requires scene_mode'
                )
        if task_type == 'size' and not _non_empty_strings(task.get('dimension_labels')):
            errors.append(
                f'$.image_tasks[{task_id}] size task requires dimension_labels'
            )
        elif task_type == 'size':
            for label in task['dimension_labels']:
                reason = dimension_label_error(label)
                if reason:
                    errors.append(f'$.image_tasks[{task_id}] dimension label {label!r} {reason}')
                if label not in str(task.get('instructions', '')):
                    errors.append(f'$.image_tasks[{task_id}] must include dimension label {label!r} in final instructions')
        final_copy = str(task.get('instructions', '')) + ' ' + str(task.get('on_image_text', ''))
        for mapping in task.get('text_mappings', []):
            if not isinstance(mapping, dict):
                continue
            output_text = str(mapping.get('output_text', '')).strip()
            if output_text and output_text not in final_copy:
                errors.append(f'$.image_tasks[{task_id}] final instructions omit on-image text: {output_text}')
        if task_type == 'four_grid':
            scene_cells = task.get('scene_cells')
            if not isinstance(scene_cells, list) or len(scene_cells) != 4:
                errors.append(
                    f'$.image_tasks[{task_id}] four_grid task requires exactly '
                    'four scene_cells'
                )

    main_covered = set()
    for task_id, task in tasks.items():
        if task.get('type') != 'main_image':
            continue
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

    primary = image_brief.get('primary_reference')
    if not isinstance(primary, dict):
        errors.append('$.primary_reference must record the first product link image inventory')
        return
    if not str(primary.get('asin', '')).strip():
        errors.append('$.primary_reference.asin is required')
    images = primary.get('images')
    if not isinstance(images, list) or not images:
        errors.append('$.primary_reference.images must contain the first link gallery')
        return
    first_reference_main_ids = {
        str(source.get('id', '')).strip()
        for source in images if isinstance(source, dict) and source.get('role') == 'main'
    }
    primary_asin = str(primary.get('asin', '')).strip()
    for product_id, (image_source, source_ref) in product_image_sources.items():
        if image_source == 'first_reference_main':
            if product_images[product_id] not in first_reference_main_ids:
                errors.append(
                    f'$.products[{product_id}] first_reference_main image must match '
                    'primary_reference main image id'
                )
            if primary_asin and primary_asin.upper() not in source_ref.upper():
                errors.append(
                    f'$.products[{product_id}] first_reference_main source_ref must cite '
                    'primary_reference ASIN'
                )
    seen_image_ids = set()
    has_main = False
    for index, source in enumerate(images):
        path = f'$.primary_reference.images[{index}]'
        if not isinstance(source, dict):
            errors.append(f'{path} must be an object')
            continue
        image_id = str(source.get('id', '')).strip()
        if not image_id:
            errors.append(f'{path}.id is required')
        elif image_id in seen_image_ids:
            errors.append(f'{path}.id is duplicated: {image_id}')
        seen_image_ids.add(image_id)
        role = str(source.get('role', '')).strip()
        if role == 'main':
            has_main = True
        mapped_task_ids = source.get('mapped_task_ids', [])
        omitted_reason = str(source.get('omitted_reason', '')).strip()
        if mapped_task_ids and omitted_reason:
            errors.append(f'{path} cannot be both mapped and omitted')
        if not mapped_task_ids and not omitted_reason:
            errors.append(f'{path} requires mapped_task_ids or a specific omitted_reason')
            continue
        if mapped_task_ids and not _non_empty_strings(mapped_task_ids):
            errors.append(f'{path}.mapped_task_ids must be non-empty strings')
            continue
        unknown_tasks = [item for item in mapped_task_ids if item not in tasks]
        if unknown_tasks:
            errors.append(f'{path} maps to unknown tasks: ' + ', '.join(unknown_tasks))
            continue
        if role == 'main' and not any(
                tasks.get(task_id, {}).get('type') == 'main_image'
                for task_id in mapped_task_ids):
            errors.append(f'{path} main source image must map to a main_image task')
        if omitted_reason:
            continue
        content_elements = source.get('content_elements', [])
        text_elements = source.get('text_elements', [])
        if content_elements and not _non_empty_strings(content_elements):
            errors.append(f'{path}.content_elements must contain non-empty strings')
        if text_elements and not _non_empty_strings(text_elements):
            errors.append(f'{path}.text_elements must contain non-empty strings')
        mapped_content = _mapping_sources(tasks, mapped_task_ids, 'content_mappings')
        mapped_text = _mapping_sources(tasks, mapped_task_ids, 'text_mappings')
        missing_content = [item for item in content_elements if item not in mapped_content]
        missing_text = [item for item in text_elements if item not in mapped_text]
        if missing_content:
            errors.append(f'{path} has unmapped content: ' + ', '.join(missing_content))
        if missing_text:
            errors.append(f'{path} has unmapped detail text: ' + ', '.join(missing_text))
        scene_cells = source.get('scene_cells', [])
        if role == 'four_grid':
            if not isinstance(scene_cells, list) or len(scene_cells) != 4:
                errors.append(f'{path} four_grid must record exactly four scene_cells')
                continue
            target_cells = []
            for task_id in mapped_task_ids:
                target_cells.extend(tasks.get(task_id, {}).get('scene_cells', []))
            for cell_index, cell in enumerate(scene_cells):
                if not isinstance(cell, dict):
                    errors.append(f'{path}.scene_cells[{cell_index}] must be an object')
                    continue
                source_scene = str(cell.get('source_scene', '')).strip()
                source_text = str(cell.get('source_text', '')).strip()
                if not source_scene:
                    errors.append(
                        f'{path}.scene_cells[{cell_index}] requires source_scene'
                    )
                    continue
                match = next((item for item in target_cells if isinstance(item, dict)
                              and str(item.get('source_scene', '')).strip() == source_scene
                              and str(item.get('source_text', '')).strip() == source_text), None)
                if (not match or not str(match.get('output_scene', '')).strip()
                        or (source_text and not str(match.get('output_text', '')).strip())):
                    errors.append(
                        f'{path}.scene_cells[{cell_index}] is missing a complete output '
                        'scene/text mapping'
                    )
    if not has_main:
        errors.append('$.primary_reference.images must include the first link main image')

    additional = image_brief.get('additional_references')
    if not isinstance(additional, list):
        errors.append('$.additional_references must list other competitor image inventories (empty when none)')
        return
    for ref_index, reference in enumerate(additional):
        ref_path = f'$.additional_references[{ref_index}]'
        if not isinstance(reference, dict) or not str(reference.get('asin', '')).strip():
            errors.append(f'{ref_path}.asin is required')
            continue
        ref_images = reference.get('images')
        if not isinstance(ref_images, list) or not ref_images:
            errors.append(f'{ref_path}.images must record useful images from this link')
            continue
        for image_index, source in enumerate(ref_images):
            path = f'{ref_path}.images[{image_index}]'
            if not isinstance(source, dict):
                errors.append(f'{path} must be an object')
                continue
            image_id = str(source.get('id', '')).strip()
            if not image_id or image_id in seen_image_ids:
                errors.append(f'{path}.id is missing or duplicated')
            seen_image_ids.add(image_id)
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
            for field, source_key, message in (
                    ('content_mappings', 'content_elements', 'content'),
                    ('text_mappings', 'text_elements', 'detail text')):
                elements = source.get(source_key, [])
                if elements and not _non_empty_strings(elements):
                    errors.append(f'{path}.{source_key} must contain non-empty strings')
                    continue
                mapped = _mapping_sources(tasks, task_ids, field)
                missing = [item for item in elements if item not in mapped]
                if missing:
                    errors.append(f'{path} has unmapped {message}: ' + ', '.join(missing))


def validate(image_brief, listing_package=None):
    errors, warnings = [], []
    image_strings = list(walk_strings(image_brief))

    validate_visual_contract(image_brief, errors)

    for path, value in image_strings:
        if LISTING_STRUCTURE_LEAK.search(value):
            errors.append(
                f'{path} uses Listing/SEO field structure to drive an image task'
            )
        key = path.rsplit('.', 1)[-1]
        if key in IMAGE_TEXT_KEYS and len(words(value)) > 6:
            warnings.append(
                f'{path} has more than 6 words; default image text should be 1-3 words '
                'or necessary numeric labels'
            )

    if listing_package is not None:
        listing_ngrams = {}
        for path, value in listing_strings(listing_package):
            for gram in ngrams(value):
                listing_ngrams.setdefault(gram, path)
        for image_path, value in image_strings:
            for gram in ngrams(value):
                if gram in listing_ngrams:
                    phrase = ' '.join(gram)
                    errors.append(
                        f'{image_path} copies Listing wording from '
                        f'{listing_ngrams[gram]}: {phrase}'
                    )
                    break

    return {
        'ready_for_delivery': not errors,
        'errors': errors,
        'warnings': warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('image_brief_package', type=Path)
    parser.add_argument('--listing-package', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    image_brief = json.loads(args.image_brief_package.read_text(encoding='utf-8'))
    listing_package = None
    if args.listing_package:
        listing_package = json.loads(args.listing_package.read_text(encoding='utf-8'))
    result = validate(image_brief, listing_package)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + '\n', encoding='utf-8')
    print(payload)
    raise SystemExit(0 if result['ready_for_delivery'] else 1)


if __name__ == '__main__':
    main()
