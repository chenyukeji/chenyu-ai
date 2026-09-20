from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZUOTU = ROOT / "plugins" / "chenyu-meigong" / "skills" / "chenyu-zuotu"


def test_main_image_contract_requires_pure_white_background():
    skill = (ZUOTU / "SKILL.md").read_text(encoding="utf-8")
    production = (ZUOTU / "references" / "production-and-review.md").read_text(
        encoding="utf-8"
    )

    for text in (skill, production):
        assert "#FFFFFF" in text
        assert "RGB 255,255,255" in text
        assert "product color applies only to the product" in text

    assert "不能用`blush white`" in skill
    assert "任何粉色/米色/灰色底" in production


def test_task_schema_classifies_main_images_before_prompting():
    skill = (ZUOTU / "SKILL.md").read_text(encoding="utf-8")
    task_reference = (ZUOTU / "references" / "input-and-tasks.md").read_text(
        encoding="utf-8"
    )

    assert "`image_type`" in skill
    assert '"image_type": "main_image"' in task_reference
    assert "产品颜色不得扩展到背景或环境光" in task_reference
