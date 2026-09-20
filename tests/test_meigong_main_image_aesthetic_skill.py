from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chenyu-meigong"
SKILL = PLUGIN / "skills" / "chenyu-zhutu-youhua"


def test_main_image_aesthetic_skill_is_packaged_and_routed():
    assert (SKILL / "SKILL.md").is_file()
    assert (SKILL / "agents" / "openai.yaml").is_file()
    assert (SKILL / "assets" / "icon.svg").is_file()

    router = (PLUGIN / "skills" / "chenyu-meigong" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "../chenyu-zhutu-youhua/SKILL.md" in router


def test_main_image_aesthetic_skill_has_distinct_decision_boundary():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    assert "主动参与美术决策" in text
    assert "视觉重心与主体张力" in text
    assert "比例、层次与节奏" in text
    assert "产品设计和售卖事实" in text
    assert "从素材重新制作主图或整套图片使用 `chenyu-zuotu`" in text
    assert "局部修改且不希望改变构图时使用 `chenyu-jingxiu`" in text
