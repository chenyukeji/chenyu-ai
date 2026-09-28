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
