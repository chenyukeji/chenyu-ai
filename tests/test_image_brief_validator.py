import copy
import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / 'plugins/chenyu-yunying/skills/chenyu-zuotuyaoqiu/scripts/'
    / 'validate_image_brief_boundaries.py'
)
SPEC = importlib.util.spec_from_file_location('validate_image_brief_boundaries', SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def package():
    data = {
        'products': [
            {'id': 'V1', 'product_content_image_id': 'product-v1',
             'product_content_image_source': 'own_main',
             'product_content_image_source_ref': 'development workbook embedded image B2',
             'own_main_image_id': 'product-v1', 'supplier_image_id': ''}
        ],
        'primary_reference': {
            'asin': 'B012345678',
            'images': [
                {
                    'id': 'source-main', 'role': 'main',
                    'content_elements': ['white background arrangement'],
                    'text_elements': [], 'mapped_task_ids': ['T1'],
                },
                {
                    'id': 'source-detail', 'role': 'detail',
                    'content_elements': ['close-up filter layers'],
                    'text_elements': ['Activated Carbon Layer'],
                    'mapped_task_ids': ['T2'],
                },
                {
                    'id': 'source-scenes', 'role': 'four_grid',
                    'content_elements': ['four use scenes'],
                    'text_elements': [], 'mapped_task_ids': ['T5'],
                    'scene_cells': [
                        {'source_scene': 'kitchen', 'source_text': 'Kitchen'},
                        {'source_scene': 'office', 'source_text': 'Office'},
                        {'source_scene': 'travel', 'source_text': 'Travel'},
                        {'source_scene': 'bedroom', 'source_text': 'Bedroom'},
                    ],
                },
            ],
        },
        'additional_references': [],
        'image_tasks': [
            {
                'id': 'T1', 'type': 'main_image', 'product_ids': ['V1'],
                'product_image_ids': ['product-v1'], 'on_image_text': '',
                'main_style': 'clean_white',
                'main_style_reason': '产品轮廓在白底缩略图里清楚可辨',
                'instructions': '纯白背景，完整展示售卖产品，主体居中。',
                'identity_lock': {
                    'shape_structure': '与产品内容图片完全一致',
                    'color_pattern': '与产品内容图片完全一致',
                    'quantity_components': '与产品内容图片完全一致',
                    'accessories_packaging': '与产品内容图片完全一致',
                },
                'content_mappings': [
                    {'source_content': 'white background arrangement',
                     'output_content': '纯白背景，完整展示售卖产品'}
                ],
                'text_mappings': [], 'scene_cells': [],
            },
            {
                'id': 'T2', 'type': 'closeup_scene', 'product_ids': ['V1'],
                'scene_mode': '厨房环境局部虚化，产品近照为主体',
                'instructions': '放大过滤层结构，标签写 Activated Carbon Layer。',
                'content_mappings': [
                    {'source_content': 'close-up filter layers',
                     'output_content': '放大过滤层结构'}
                ],
                'text_mappings': [
                    {'source_text': 'Activated Carbon Layer',
                     'output_text': 'Activated Carbon Layer'}
                ],
                'scene_cells': [],
            },
            {
                'id': 'T3', 'type': 'size', 'product_ids': ['V1'],
                'dimension_labels': ['9.5 cm / 3.74 in', '4.5 cm / 1.77 in', '0.9 cm / 0.35 in'],
                'on_image_text': 'Product Size；9.5 cm / 3.74 in；4.5 cm / 1.77 in；0.9 cm / 0.35 in',
                'supporting_visual': {'kind': 'detail', 'description': '边缘接口纹理局部',
                                      'source_ref': 'V1 original close-up'},
                'instructions': '顶部写 Product Size；标注三个测量方向：9.5 cm / 3.74 in、4.5 cm / 1.77 in、0.9 cm / 0.35 in；角落展示边缘接口纹理局部。',
                'content_mappings': [], 'text_mappings': [], 'scene_cells': [],
            },
            {
                'id': 'T-M1', 'type': 'feature', 'product_ids': ['V1'],
                'instructions': '依据竞品细节内容，展示本品已确认的滤层结构。',
                'content_mappings': [], 'text_mappings': [], 'scene_cells': [],
            },
            {
                'id': 'T4', 'type': 'key_scene', 'product_ids': ['V1'],
                'scene_mode': '冰箱冷藏室中的核心使用场景',
                'instructions': '用单一核心场景突出产品的实际使用位置。',
                'content_mappings': [], 'text_mappings': [], 'scene_cells': [],
            },
            {
                'id': 'T5', 'type': 'four_grid', 'product_ids': ['V1'],
                'instructions': '四格分别展示厨房、办公室、旅行和卧室场景，每格写 Kitchen、Office、Travel、Bedroom。',
                'content_mappings': [
                    {'source_content': 'four use scenes',
                     'output_content': '厨房、办公室、旅行和卧室场景'}
                ],
                'text_mappings': [],
                'scene_cells': [
                    {'source_scene': 'kitchen', 'source_text': 'Kitchen',
                     'output_scene': '厨房', 'output_text': 'Kitchen'},
                    {'source_scene': 'office', 'source_text': 'Office',
                     'output_scene': '办公室', 'output_text': 'Office'},
                    {'source_scene': 'travel', 'source_text': 'Travel',
                     'output_scene': '旅行', 'output_text': 'Travel'},
                    {'source_scene': 'bedroom', 'source_text': 'Bedroom',
                     'output_scene': '卧室', 'output_text': 'Bedroom'},
                ],
            },
        ],
    }

    data['products'][0]['visual_direction'] = '白底配灰绿标题，左侧主体右侧信息，柔光展现表面，统一短标签层级。'
    data['primary_reference']['coverage_status'] = 'complete'
    questions = [
        ('售卖什么产品？', '外形与售卖件数'),
        ('内部结构是什么？', '过滤层的组成'),
        ('能否放入目标位置？', '三个测量方向及接口位置'),
        ('怎样安装？', '安装动作顺序'),
        ('在哪里使用？', '冷藏室内的放置位置'),
        ('还有哪些适用环境？', '四种不同环境的用途'),
    ]
    for task, (question, information) in zip(data['image_tasks'], questions):
        task['buyer_question'], task['new_information'] = question, information
        task.setdefault('on_image_text', '')
        for field in ('content_mappings', 'text_mappings'):
            for mapping in task[field]:
                mapping['source_image_id'] = {'T1': 'source-main', 'T2': 'source-detail', 'T5': 'source-scenes'}[task['id']]
        for cell in task.get('scene_cells', []):
            cell['source_image_id'] = 'source-scenes'
    data['image_tasks'][3]['type'] = 'process'
    data['image_tasks'][3]['instructions'] = '分步展示放置产品的动作顺序。'
    data['image_tasks'][2]['dimension_source'] = {'kind': 'development', 'source_ref': '开发资料 V1 三方向尺寸'}
    data['image_tasks'][2]['supporting_visual']['dimension_relevance'] = '接口定位帮助理解测量起点'
    return data


def test_dynamic_six_task_plan_is_valid():
    result = VALIDATOR.validate(package())
    assert result['ready_for_delivery'], result['errors']


def test_first_link_main_image_is_valid_fallback_with_source_trace():
    data = package()
    product = data['products'][0]
    product['own_main_image_id'] = ''
    product['supplier_image_id'] = ''
    product['product_content_image_id'] = 'source-main'
    product['product_content_image_source'] = 'first_reference_main'
    product['matching_basis'] = '采购资料确认同款及当前规格'
    product['product_content_image_source_ref'] = 'B012345678 main image'
    data['image_tasks'][0]['product_image_ids'] = ['source-main']
    assert VALIDATOR.validate(data)['ready_for_delivery']

    product['product_content_image_id'] = 'source-detail'
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('first_reference_main image must match' in item
               for item in result['errors'])


def test_supplier_image_takes_priority_when_own_main_is_absent():
    data = package()
    product = data['products'][0]
    product['own_main_image_id'] = ''
    product['supplier_image_id'] = 'supplier-v1'
    product['product_content_image_id'] = 'supplier-v1'
    product['product_content_image_source'] = 'supplier'
    product['product_content_image_source_ref'] = 'supplier listing / V1 variant image'
    data['image_tasks'][0]['product_image_ids'] = ['supplier-v1']
    assert VALIDATOR.validate(data)['ready_for_delivery']

    product['product_content_image_source'] = 'first_reference_main'
    result = VALIDATOR.validate(data)
    assert any('must choose image source in' in item for item in result['errors'])


def test_product_image_source_is_required():
    data = package()
    del data['products'][0]['product_content_image_source']
    data['products'][0]['product_content_image_source_ref'] = ''
    result = VALIDATOR.validate(data)
    assert any('product_content_image_source must be' in item for item in result['errors'])
    assert any('product_content_image_source_ref is required' in item
               for item in result['errors'])


def test_main_image_requires_a_valid_visual_choice():
    data = package()
    data['image_tasks'][0]['main_style'] = 'scene_hero'
    data['image_tasks'][0]['main_style_reason'] = '桌旗垂落场景展示材质与使用效果'
    assert VALIDATOR.validate(data)['ready_for_delivery']

    data['image_tasks'][0]['main_style'] = 'unsupported'
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('main_style' in error for error in result['errors'])

    data['image_tasks'][0]['main_style'] = 'scene_hero'
    data['image_tasks'][0]['main_style_reason'] = ''
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('main_style_reason' in error for error in result['errors'])


def test_main_image_must_use_exact_product_content_image_and_identity_lock():
    data = package()
    main = data['image_tasks'][0]
    main['product_image_ids'] = ['source-main']
    del main['identity_lock']['quantity_components']
    data['primary_reference']['images'][0]['mapped_task_ids'] = ['T2']
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('must exactly match 产品内容 images' in item for item in result['errors'])
    assert any('identity_lock omits: quantity_components' in item
               for item in result['errors'])


def test_detail_text_and_four_grid_scene_text_cannot_be_dropped():
    data = package()
    data['image_tasks'][1]['text_mappings'] = []
    data['image_tasks'][5]['scene_cells'][3]['output_text'] = ''
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('unmapped detail text: Activated Carbon Layer' in item
               for item in result['errors'])
    assert any('missing a complete output scene/text mapping' in item
               for item in result['errors'])


def test_execution_instructions_do_not_narrate_reference_images():
    data = copy.deepcopy(package())
    data['image_tasks'][1]['instructions'] = '参考图片1用于展示过滤层结构。'
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('narrates source-image usage' in item for item in result['errors'])


def test_default_count_is_per_product_with_explicit_exception():
    data = package()
    assert VALIDATOR.validate(data)['ready_for_delivery']

    five_tasks = copy.deepcopy(data)
    five_tasks['image_tasks'].pop(3)
    result = VALIDATOR.validate(five_tasks)
    assert not result['ready_for_delivery']
    assert any('must contain 6-8 tasks for product V1; found 5' in item
               for item in result['errors'])

    for task_id, task_type in [('T-M2', 'process'), ('T-M3', 'detail')]:
        data['image_tasks'].insert(-2, {
            'id': task_id, 'type': task_type, 'product_ids': ['V1'],
            'instructions': '展示有依据的独立信息。',
            'buyer_question': task_id + ' 所需判断？', 'new_information': task_id + ' 新增信息',
            'content_mappings': [], 'text_mappings': [], 'scene_cells': [],
        })
    assert VALIDATOR.validate(data)['ready_for_delivery']

    data['image_tasks'].insert(-2, {
        'id': 'T-M4', 'type': 'advantage', 'product_ids': ['V1'],
        'instructions': '增加第四张中间优势图。',
        'content_mappings': [], 'text_mappings': [], 'scene_cells': [],
    })
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('must contain 6-8 tasks for product V1; found 9' in item
               for item in result['errors'])


def test_required_scene_and_size_metadata_cannot_be_missing():
    data = package()
    data['image_tasks'][1]['scene_mode'] = ''
    data['image_tasks'][2]['dimension_labels'] = []
    data['image_tasks'][4]['scene_mode'] = ''
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('closeup_scene requires scene_mode' in item for item in result['errors'])
    assert any('size task requires dimension_labels' in item for item in result['errors'])
    assert any('key_scene requires scene_mode' in item for item in result['errors'])


def test_size_labels_require_both_units_and_correct_conversion():
    data = package()
    data['image_tasks'][2]['dimension_labels'] = ['45–60 cm']
    result = VALIDATOR.validate(data)
    assert any('must pair one cm value/range' in item for item in result['errors'])
    data['image_tasks'][2]['dimension_labels'] = ['45–60 cm / 20–24 in']
    result = VALIDATOR.validate(data)
    assert any('do not convert using 2.54' in item for item in result['errors'])


def test_competitor_descriptions_can_merge_into_one_final_image():
    data = package()
    data['additional_references'] = [{
        'asin': 'B0OTHER123', 'coverage_status': 'complete',
        'images': [
            {'id': 'fleece-closeup', 'role': 'detail',
             'content_elements': ['fleece interior close-up'],
             'text_elements': ['Warm Fabric'], 'mapped_task_ids': ['T2']},
            {'id': 'stitched-edge', 'role': 'detail',
             'content_elements': ['stitched opening'],
             'text_elements': ['Comfort Fit'], 'mapped_task_ids': ['T2']},
        ],
    }]
    task = data['image_tasks'][1]
    task['content_mappings'].extend([
        {'source_image_id': 'fleece-closeup', 'source_content': 'fleece interior close-up', 'output_content': '本品绒布内里'},
        {'source_image_id': 'stitched-edge', 'source_content': 'stitched opening', 'output_content': '本品缝线开口'},
    ])
    task['text_mappings'].extend([
        {'source_image_id': 'fleece-closeup', 'source_text': 'Warm Fabric', 'output_text': 'Fleece Lining'},
        {'source_image_id': 'stitched-edge', 'source_text': 'Comfort Fit', 'output_text': 'Under Helmet'},
    ])
    task['instructions'] += ' 展示本品绒布内里与本品缝线开口；同一张图加入 Fleece Lining 和 Under Helmet 两个短标签。'
    assert VALIDATOR.validate(data)['ready_for_delivery']
    task['instructions'] = task['instructions'].replace('Under Helmet', '')
    result = VALIDATOR.validate(data)
    assert any('final instructions omit on-image text: Under Helmet' in item
               for item in result['errors'])
    task['instructions'] += ' Under Helmet'
    task['text_mappings'].pop()
    result = VALIDATOR.validate(data)
    assert any('has unmapped detail text: Comfort Fit' in item
               for item in result['errors'])


def test_size_heading_and_labels_must_reach_final_instructions():
    data = package()
    size = data['image_tasks'][2]
    size['instructions'] = size['instructions'].replace('Product Size', '')
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('size heading' in item for item in result['errors'])

    size['instructions'] = package()['image_tasks'][2]['instructions']
    size['on_image_text'] = size['on_image_text'].replace('Product Size', '')
    result = VALIDATOR.validate(data)
    assert any('size heading' in item for item in result['errors'])

    size['on_image_text'] = 'Dimensions；9.5 cm / 3.74 in；4.5 cm / 1.77 in；0.9 cm / 0.35 in'
    size['instructions'] = size['instructions'].replace('Product Size', 'Dimensions')
    size['size_heading'] = 'Dimensions'
    size['size_heading_override_reason'] = 'User explicitly requested Dimensions'
    assert VALIDATOR.validate(data)['ready_for_delivery']


def test_mapped_competitor_content_and_scene_copy_must_reach_final_instructions():
    data = package()
    data['image_tasks'][1]['instructions'] = '标签写 Activated Carbon Layer。'
    data['image_tasks'][5]['instructions'] = '四格展示厨房、办公室、旅行和卧室场景。'
    result = VALIDATOR.validate(data)
    assert not result['ready_for_delivery']
    assert any('final instructions omit mapped content: 放大过滤层结构' in item
               for item in result['errors'])
    assert any('final instructions omit four-grid output_text: Bedroom' in item
               for item in result['errors'])


def test_size_visual_adds_distinct_evidence_or_explains_pure_size():
    data = package()
    size = data['image_tasks'][2]
    del size['supporting_visual']
    result = VALIDATOR.validate(data)
    assert any('size task requires supporting_visual' in item for item in result['errors'])

    size['supporting_visual'] = {'kind': 'scene', 'description': '厨房台面使用局部',
                                 'source_ref': 'V1 verified use photo',
                                 'dimension_relevance': '展示安装空间与产品尺寸的关系'}
    result = VALIDATOR.validate(data)
    assert any('final instructions omit supporting visual' in item for item in result['errors'])
    size['instructions'] += ' 厨房台面使用局部。'
    assert VALIDATOR.validate(data)['ready_for_delivery']

    data['image_tasks'][4]['instructions'] += ' 厨房台面使用局部。'
    result = VALIDATOR.validate(data)
    assert any('supporting visual repeats task T4' in item for item in result['errors'])

    size['supporting_visual'] = {'kind': 'none'}
    assert VALIDATOR.validate(data)['ready_for_delivery']
    size['instructions'] = size['instructions'].replace(' 厨房台面使用局部。', '')
    assert VALIDATOR.validate(data)['ready_for_delivery']


def test_flexible_order_and_optional_scenes_with_pure_size():
    data = package()
    # Six tasks may use a size image second and have no final four-grid or scene.
    data['image_tasks'][1], data['image_tasks'][2] = data['image_tasks'][2], data['image_tasks'][1]
    size = data['image_tasks'][1]
    size['supporting_visual'] = {'kind': 'none'}
    for task in data['image_tasks']:
        if task['type'] in ('closeup_scene', 'key_scene', 'four_grid'):
            task['type'] = 'detail'
            task.pop('scene_mode', None)
    assert VALIDATOR.validate(data)['ready_for_delivery']


def test_short_plan_requires_reason_but_not_filler():
    data = package()
    data['image_tasks'].pop(3)
    data['products'][0]['task_count_reason'] = '五个独立问题已覆盖，追加特点图会重复过滤层结构'
    assert VALIDATOR.validate(data)['ready_for_delivery']


def test_all_links_have_equal_selection_and_omission_rules():
    data = package()
    primary = data['primary_reference']
    main = primary['images'].pop(0)
    main['id'] = 'better-main'
    data['additional_references'] = [{'asin': 'B0BETTER12', 'coverage_status': 'complete', 'images': [main]}]
    # First link has a poorer main; it is evaluated and omitted.
    primary['images'].insert(0, {'id': 'poor-main', 'role': 'main', 'omitted_reason': '主体过小，另一来源构图更清楚'})
    data['image_tasks'][0]['content_mappings'][0]['source_image_id'] = 'better-main'
    product = data['products'][0]
    product.update(own_main_image_id='', product_content_image_source='confirmed_reference_main',
                   product_content_image_id='better-main', product_content_image_source_ref='B0BETTER12 当前变体主图',
                   matching_basis='采购确认对应同款同规格')
    data['image_tasks'][0]['product_image_ids'] = ['better-main']
    assert VALIDATOR.validate(data)['ready_for_delivery']
    del product['matching_basis']
    assert not VALIDATOR.validate(data)['ready_for_delivery']


def test_partial_content_selection_requires_specific_reason():
    data = package()
    source = data['primary_reference']['images'][1]
    source['text_elements'].append('Premium Quality')
    assert not VALIDATOR.validate(data)['ready_for_delivery']
    source['omitted_elements'] = [{'kind': 'text', 'value': 'Premium Quality', 'reason': '泛化品质口号，结构图无法直接证明'}]
    assert VALIDATOR.validate(data)['ready_for_delivery']
    source['omitted_elements'][0]['reason'] = ''
    assert not VALIDATOR.validate(data)['ready_for_delivery']


def test_source_grid_can_be_reduced_without_forcing_final_grid():
    data = package()
    source = data['primary_reference']['images'][2]
    task = data['image_tasks'][5]
    source['text_elements'] = ['Kitchen', 'Office', 'Travel', 'Bedroom']
    task['type'] = 'scene'
    task['scene_mode'] = '保留有依据的厨房用途'
    task['instructions'] = '厨房场景，短标签 Kitchen。'
    task['scene_cells'] = task['scene_cells'][:1]
    task['content_mappings'] = []
    source['omitted_elements'] = [
        {'kind': 'content', 'value': 'four use scenes', 'reason': '其余用途不适用本品'},
        *[{'kind': 'scene', 'value': name, 'reason': '无本品使用依据'} for name in ('office', 'travel', 'bedroom')],
    ]
    assert VALIDATOR.validate(data)['ready_for_delivery']
    source['omitted_elements'].pop()
    assert not VALIDATOR.validate(data)['ready_for_delivery']


def test_matching_words_from_another_source_do_not_satisfy_coverage():
    data = package()
    source = copy.deepcopy(data['primary_reference']['images'][1])
    source['id'] = 'other-detail'
    data['additional_references'] = [{'asin': 'B0OTHER123', 'coverage_status': 'complete', 'images': [source]}]
    result = VALIDATOR.validate(data)
    assert any('additional_references[0]' in error and 'unmapped' in error for error in result['errors'])


def test_no_reference_assets_and_failed_link_are_supported():
    data = package()
    data['primary_reference'] = None
    for task in data['image_tasks']:
        task['content_mappings'] = []
        task['text_mappings'] = []
        for cell in task['scene_cells']:
            for key in ('source_image_id', 'source_scene', 'source_text'):
                cell.pop(key, None)
    assert VALIDATOR.validate(data)['ready_for_delivery']
    data['additional_references'] = [{'asin': 'B0FAILED12', 'coverage_status': 'failed', 'images': []}]
    assert not VALIDATOR.validate(data)['ready_for_delivery']
    data['additional_references'][0]['coverage_note'] = '补查后仍访问失败，主图/图册/A+ 均未读到'
    assert VALIDATOR.validate(data)['ready_for_delivery']


def test_visual_direction_duplicate_information_and_dimension_evidence():
    data = package()
    data['products'][0]['visual_direction'] = ''
    data['image_tasks'][3]['new_information'] = data['image_tasks'][1]['new_information']
    data['image_tasks'][2]['dimension_source']['kind'] = 'similar_competitor'
    data['image_tasks'][2]['supporting_visual']['dimension_relevance'] = ''
    errors = VALIDATOR.validate(data)['errors']
    for expected in ('visual_direction', 'repeats new_information', 'dimension_source', 'dimension_relevance'):
        assert any(expected in error for error in errors)


def test_multiple_products_are_not_limited_to_eight_total_tasks():
    data = package()
    variant = copy.deepcopy(data['products'][0])
    variant['id'] = 'V2'
    data['products'].append(variant)
    extra = copy.deepcopy(data['image_tasks'])
    for task in extra:
        task['id'] += '-V2'
        task['product_ids'] = ['V2']
        task['content_mappings'] = []
        task['text_mappings'] = []
        for cell in task['scene_cells']:
            for key in ('source_image_id', 'source_scene', 'source_text'):
                cell.pop(key, None)
    data['image_tasks'].extend(extra)
    assert len(data['image_tasks']) == 12
    assert VALIDATOR.validate(data)['ready_for_delivery']
