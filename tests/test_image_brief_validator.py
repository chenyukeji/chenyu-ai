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
    return {
        'products': [
            {'id': 'V1', 'product_content_image_id': 'product-v1'}
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
                    'text_elements': [], 'mapped_task_ids': ['T3'],
                    'scene_cells': [
                        {'source_scene': 'kitchen', 'source_text': 'Kitchen'},
                        {'source_scene': 'office', 'source_text': 'Office'},
                        {'source_scene': 'travel', 'source_text': 'Travel'},
                        {'source_scene': 'bedroom', 'source_text': 'Bedroom'},
                    ],
                },
            ],
        },
        'image_tasks': [
            {
                'id': 'T1', 'type': 'main_image', 'product_ids': ['V1'],
                'product_image_ids': ['product-v1'], 'on_image_text': '',
                'instructions': '纯白背景，完整展示售卖产品，主体居中。',
                'identity_lock': {
                    'shape_structure': '与产品内容图片完全一致',
                    'color_pattern': '与产品内容图片完全一致',
                    'quantity_components': '与产品内容图片完全一致',
                    'accessories_packaging': '与产品内容图片完全一致',
                },
                'content_mappings': [
                    {'source_content': 'white background arrangement',
                     'output_content': 'white background arrangement with V1 product'}
                ],
                'text_mappings': [], 'scene_cells': [],
            },
            {
                'id': 'T2', 'type': 'detail', 'product_ids': ['V1'],
                'instructions': '放大过滤层结构，保留完整结构说明文字。',
                'content_mappings': [
                    {'source_content': 'close-up filter layers',
                     'output_content': 'close-up of confirmed V1 filter layers'}
                ],
                'text_mappings': [
                    {'source_text': 'Activated Carbon Layer',
                     'output_text': 'Activated Carbon Layer'}
                ],
                'scene_cells': [],
            },
            {
                'id': 'T3', 'type': 'four_grid', 'product_ids': ['V1'],
                'instructions': '四格分别展示厨房、办公室、旅行和卧室场景。',
                'content_mappings': [
                    {'source_content': 'four use scenes',
                     'output_content': 'four confirmed use scenes'}
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


def test_dynamic_three_task_plan_is_valid():
    result = VALIDATOR.validate(package())
    assert result['ready_for_delivery'], result['errors']


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
    assert any('main source image must map to a main_image task' in item
               for item in result['errors'])


def test_detail_text_and_four_grid_scene_text_cannot_be_dropped():
    data = package()
    data['image_tasks'][1]['text_mappings'] = []
    data['image_tasks'][2]['scene_cells'][3]['output_text'] = ''
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
