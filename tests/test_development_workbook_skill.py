import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/chenyu-kaifa"
SKILL = PLUGIN / "skills/chenyu-kaifawendang"


def load_validator():
    path = SKILL / "scripts/validate_development_workbooks.py"
    spec = importlib.util.spec_from_file_location("development_workbook_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_manifests_match_and_expose_new_skill_capability():
    outer = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    inner = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert outer["version"] == inner["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", outer["version"])
    assert "One-product-per-workbook development documentation" in outer["interface"]["capabilities"]
    assert "One-product-per-workbook development documentation" in inner["interface"]["capabilities"]


def test_sanitized_template_obeys_development_workbook_contract():
    validator = load_validator()
    template = SKILL / "assets/晨玙产品开发文档母版.xlsx"
    report = validator.inspect_workbook(template, template=True)
    assert report["errors"] == []
    assert [sheet["name"] for sheet in report["sheets"]] == [
        "参考产品信息调研",
        "产品确认",
        "产品详情母版",
    ]


def test_skill_contract_requires_one_workbook_per_product():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "每个产品必须独立生成一个 Excel 文件" in text
    assert "同一核心产品的颜色、尺寸、数量或图案变体保留在同一个文件" in text


def test_confirmation_requires_available_competitor_links():
    validator = load_validator()
    research = [
        {12: "https://www.amazon.com/dp/B0F9FG1GV5"},
        {12: "https://www.amazon.com/example/dp/B0FR4P2J4W/ref=tracking?tag=example"},
    ]
    errors = validator._confirmation_link_errors(research, {9: "/", 10: "/"})
    assert any("亚马逊链接为空" in error for error in errors)
    assert any("亚马逊链接2为空" in error for error in errors)
    assert any("未带入" in error for error in errors)

    assert validator._confirmation_link_errors(
        research,
        {9: research[0][12], 10: "https://www.amazon.com/dp/B0FR4P2J4W", 11: "/"},
    ) == []
    assert validator._confirmation_link_errors(
        research,
        {9: "https://www.amazon.com/dp/B0OWNASIN01", 10: research[0][12], 11: "B0OWNASIN01"},
    ) == []
    assert "产品确认的两条亚马逊链接重复" in validator._confirmation_link_errors(
        research,
        {9: research[0][12], 10: research[0][12] + "?tag=tracking"},
    )


def test_detail_supplier_image_stays_in_variant_row():
    validator = load_validator()
    rows = {2: {2: "绿色皮革款", 3: "", 5: ""}}
    assert validator._detail_image_errors(rows, {(3, 2), (5, 2)}) == []

    misplaced = validator._detail_image_errors(rows, {(3, 3), (5, 3)})
    assert any("缺少同一行图片" in error for error in misplaced)
    assert any("应放入对应变体的数据行" in error for error in misplaced)

    text_in_image_cell = validator._detail_image_errors(
        {2: {2: "绿色皮革款", 3: "供应商产品名称：/", 5: ""}},
        {(3, 2), (5, 2)},
    )
    assert any("应只放图片" in error for error in text_in_image_cell)
