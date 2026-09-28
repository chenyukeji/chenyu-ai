"""Runtime entrypoint for the Chenyu procurement skill."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collector_1688 import Collector1688Error, browser_status, collect_1688_suppliers


class ContractError(ValueError):
    pass


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ContractError("input must be a JSON object")
    action = payload.get("skill_action") or "status"
    if action == "status":
        return {
            "ok": True,
            "skill": "chenyu-caigou",
            "purpose": "供应商采集、比较、采购规划与供应链风险整理",
            "actions": [
                "status",
                "browser_status",
                "collect_1688_suppliers",
                "resume_1688_suppliers",
            ],
        }
    if action == "browser_status":
        return {"ok": True, "browser": browser_status()}
    if action == "collect_1688_suppliers":
        return {"ok": True, **collect_1688_suppliers(payload, resume=False)}
    if action == "resume_1688_suppliers":
        return {"ok": True, **collect_1688_suppliers(payload, resume=True)}
    raise ContractError(f"unknown skill_action: {action}")


def main() -> None:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        result = handle(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (json.JSONDecodeError, ContractError, Collector1688Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
