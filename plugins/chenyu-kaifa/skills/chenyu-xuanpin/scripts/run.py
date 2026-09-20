"""Single-skill Amazon product discovery workflow."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from discovery_pipeline import DiscoveryError, merge_candidates, score_candidates, table_rows
from discovery_workbook import WorkbookError, export_discovery_workbook
from playwright_collector import BrowserCollectionError, browser_status, collect, collect_sellersprite_by_asin, login_sellersprite
from strategy_router import StrategyRouteError, list_strategies, resolve_category, resolve_strategy

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"
FLOW_VERSION = "discovery-v2"
SELLERSPRITE_FIELDS = (
    "source_available_date",
    "review_count",
    "price",
    "bsr",
    "category_name",
    "estimated_sales",
    "image_url",
)


class ContractError(ValueError):
    pass


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, value) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return str(path.resolve())


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def create_task(request=None, task=None, strategy_selection=None) -> dict:
    rules = load_rules()
    task = dict(task or {})
    strategy = resolve_strategy(request, task, strategy_selection, rules)
    category = resolve_category(request, task)
    category_name = category.get("category_normalized") or category.get("category_original")
    return {
        "task_id": task.get("task_id") or f"discovery-{uuid.uuid4().hex[:12]}",
        "request": request,
        "category_or_need": category_name,
        "category_resolution": category,
        "strategy_resolution": strategy,
        "shortlist_limit": int(task.get("shortlist_limit", 20)),
        "required_outputs": ["candidate_pool", "scored_shortlist", "discovery_workbook"],
        "created_at": _now(),
    }


def _content_records(content) -> tuple[list[dict], list[dict]]:
    if isinstance(content, list):
        return list(content), []
    if not isinstance(content, dict):
        raise ContractError("discovery input must be a JSON object or list")
    if isinstance(content.get("records"), list):
        return list(content["records"]), []
    if isinstance(content.get("candidates"), list):
        return [], list(content["candidates"])
    browser = content.get("browser")
    if isinstance(browser, dict) and isinstance(browser.get("records"), list):
        return list(browser["records"]), []
    raise ContractError("discovery input has no records or candidates")


def _identity_only(records: list[dict], marketplace: str, limit: int) -> list[dict]:
    fields = (
        "marketplace",
        "asin",
        "new_release_rank",
        "ranking_type",
        "category_node",
        "observed_at",
        "source_ref",
        "source_entity_id",
    )
    output = []
    seen = set()
    for row in records:
        asin = str(row.get("asin") or "").upper()
        market = str(row.get("marketplace") or marketplace).upper()
        if not asin or market != marketplace or asin in seen:
            continue
        normalized = {field: row.get(field) for field in fields if row.get(field) is not None}
        normalized.update({"marketplace": market, "asin": asin, "source_strategy": "E"})
        output.append(normalized)
        seen.add(asin)
        if len(output) >= limit:
            break
    return output


def _merge_sellersprite(seed_records: list[dict], seller_records: list[dict]) -> list[dict]:
    by_key = {}
    for row in seller_records:
        key = (str(row.get("marketplace") or "").upper(), str(row.get("asin") or "").upper())
        if all(key):
            by_key[key] = row
    output = []
    for seed in seed_records:
        key = (seed["marketplace"], seed["asin"])
        seller = by_key.get(key)
        merged = dict(seed)
        if seller:
            for field, value in seller.items():
                if field not in {"marketplace", "asin", "new_release_rank", "ranking_type"} and value is not None:
                    merged[field] = value
            merged["enrichment_status"] = "enriched"
        else:
            merged.setdefault("enrichment_status", "missing")
        merged["source_strategy"] = "E"
        output.append(merged)
    return output


def _missing_sellersprite_fields(row: dict) -> list[str]:
    missing = []
    for field in SELLERSPRITE_FIELDS:
        if field == "source_available_date":
            if not (row.get("source_available_date") or row.get("listing_date")):
                missing.append(field)
        elif row.get(field) is None or row.get(field) == "":
            missing.append(field)
    return missing


def _apply_category_context(records: list[dict], task: dict) -> list[dict]:
    category = task.get("category_resolution") or {}
    category_name = category.get("category_normalized") or task.get("category_or_need")
    if not category_name:
        return records
    for row in records:
        if not (row.get("category_name") or row.get("category_node")):
            row["category_name"] = category_name
    return records


def _enrich_records_from_sellersprite(
    records: list[dict], payload: dict, run_dir: Path, manifest: dict
) -> list[dict]:
    discovery = dict(payload.get("discovery") or {})
    if not discovery.get("sellersprite_enrich", True):
        return records
    refresh = bool(discovery.get("refresh_sellersprite"))
    headless = bool(discovery.get("headless", True))
    output = list(records)
    for market in ("US", "DE"):
        target_asins = []
        for row in output:
            asin = str(row.get("asin") or "").upper()
            if str(row.get("marketplace") or "").upper() == market and asin and _missing_sellersprite_fields(row):
                if asin not in target_asins:
                    target_asins.append(asin)
        if not target_asins:
            continue

        raw_path = run_dir / f"05-sellersprite-{market.lower()}-raw.json"
        cached_result = _read_json(raw_path) if raw_path.exists() and not refresh else {}
        seller_records = list(cached_result.get("records") or [])
        for seller_row in seller_records:
            raw_cells = seller_row.get("raw_cells") or {}
            review_cell = next(
                (str(value) for key, value in raw_cells.items() if "评分数" in str(key)),
                "",
            )
            first_review_value = review_cell.splitlines()[0].strip() if review_cell else ""
            if seller_row.get("review_count") is None and first_review_value in {"-", "—", "–"}:
                seller_row["review_count"] = 0
        cached_asins = {str(row.get("asin") or "").upper() for row in seller_records}
        to_query = target_asins if refresh else [asin for asin in target_asins if asin not in cached_asins]
        query_results = []
        for offset in range(0, len(to_query), 100):
            chunk = to_query[offset : offset + 100]
            result = collect_sellersprite_by_asin(
                {
                    "marketplace": market,
                    "asins": chunk,
                    "headless": headless,
                    "query_timeout_ms": discovery.get("query_timeout_ms", 20000),
                    "query_delay_ms": discovery.get("query_delay_ms", 500),
                    "manual_timeout_seconds": discovery.get("manual_timeout_seconds", 180),
                }
            )
            query_results.append(result)
            seller_records.extend(result.get("records") or [])
            if result.get("collection_status") == "blocked":
                break

        deduped = {}
        for row in seller_records:
            key = (str(row.get("marketplace") or market).upper(), str(row.get("asin") or "").upper())
            if all(key):
                deduped[key] = row
        seller_records = list(deduped.values())
        enriched_asins = {key[1] for key in deduped}
        status = "complete" if all(asin in enriched_asins for asin in target_asins) else "partial"
        block_reasons = [result.get("block_reason") for result in query_results if result.get("block_reason")]
        raw_payload = {
            "collection_status": "blocked" if block_reasons else status,
            "block_reason": block_reasons[0] if block_reasons else None,
            "records": seller_records,
            "counts": {
                "requested": len(target_asins),
                "queried": len(to_query),
                "enriched": len([asin for asin in target_asins if asin in enriched_asins]),
                "missing": len([asin for asin in target_asins if asin not in enriched_asins]),
            },
        }
        manifest["artifacts"][f"sellersprite_{market.lower()}_raw"] = _write_json(raw_path, raw_payload)
        output = _merge_sellersprite(output, seller_records)
        enriched_path = run_dir / f"06-{market.lower()}-enriched.json"
        market_rows = [row for row in output if str(row.get("marketplace") or "").upper() == market]
        manifest["artifacts"][f"sellersprite_{market.lower()}"] = _write_json(
            enriched_path,
            {"collection_status": raw_payload["collection_status"], "records": market_rows, "counts": raw_payload["counts"]},
        )
        if raw_payload["collection_status"] != "complete":
            manifest["warnings"].append(
                f"{market} 卖家精灵补数未完整：{raw_payload['counts']['missing']} 个 ASIN 未补齐"
            )
    return output


def _load_input_data(payload: dict) -> tuple[list[dict], list[dict], list[str]]:
    discovery = dict(payload.get("discovery") or {})
    records = list(payload.get("discovery_records") or discovery.get("records") or [])
    candidates = list(payload.get("candidates") or discovery.get("candidates") or [])
    sources = []
    paths = list(payload.get("discovery_paths") or discovery.get("paths") or [])
    if payload.get("discovery_path"):
        paths.append(payload["discovery_path"])
    for value in paths:
        path = Path(value).expanduser().resolve()
        source_records, source_candidates = _content_records(_read_json(path))
        records.extend(source_records)
        candidates.extend(source_candidates)
        sources.append(str(path))
    return records, candidates, sources


def _manifest(task: dict, run_dir: Path) -> dict:
    path = run_dir / "00-run.json"
    if path.exists():
        return _read_json(path)
    return {
        "run_id": task["task_id"],
        "flow_version": FLOW_VERSION,
        "status": "RUNNING",
        "current_stage": "task_resolution",
        "artifacts": {},
        "warnings": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


def _save_manifest(manifest: dict, run_dir: Path) -> None:
    manifest["updated_at"] = _now()
    manifest["warnings"] = list(dict.fromkeys(manifest.get("warnings") or []))
    _write_json(run_dir / "00-run.json", manifest)


def _stop(manifest: dict, run_dir: Path, status: str, stage: str, blocking_items: list[str]) -> dict:
    manifest.update({"status": status, "current_stage": stage, "blocking_items": blocking_items})
    _save_manifest(manifest, run_dir)
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "status": status,
        "current_stage": stage,
        "blocking_items": blocking_items,
        "artifacts": dict(manifest["artifacts"]),
        "run_dir": str(run_dir.resolve()),
    }


def _live_strategy_e(task: dict, payload: dict, run_dir: Path, manifest: dict) -> list[dict]:
    discovery = dict(payload.get("discovery") or {})
    limit = max(1, min(int(discovery.get("limit_per_marketplace", 100)), 100))
    headless = bool(discovery.get("headless", True))
    urls = dict(task["category_resolution"].get("amazon_new_releases") or {})
    urls.update(discovery.get("amazon_new_releases") or {})
    records = []
    missing_urls = [market for market in task["strategy_resolution"]["source_marketplaces"] if not urls.get(market)]
    if missing_urls:
        raise ContractError("missing Amazon new-releases URL for: " + ",".join(missing_urls))

    for market in task["strategy_resolution"]["source_marketplaces"]:
        amazon_path = run_dir / f"04-amazon-{market.lower()}-asins.json"
        if amazon_path.exists() and not discovery.get("refresh"):
            amazon_result = _read_json(amazon_path)
            seed_records = amazon_result.get("records") or []
        else:
            amazon_result = collect(
                {
                    "source": "amazon_public",
                    "url": urls[market],
                    "extractor": "amazon_ranked_list",
                    "marketplace": market,
                    "query": task.get("category_or_need"),
                    "max_pages": discovery.get("max_pages", 1),
                    "headless": headless,
                }
            )
            seed_records = _identity_only(amazon_result.get("records") or [], market, limit)
            amazon_result = {
                "collection_status": amazon_result.get("collection_status"),
                "source_metadata": amazon_result.get("source_metadata"),
                "errors": amazon_result.get("errors") or [],
                "records": seed_records,
                "counts": {"records": len(seed_records)},
            }
            manifest["artifacts"][f"amazon_{market.lower()}"] = _write_json(amazon_path, amazon_result)
        if not seed_records:
            manifest["warnings"].append(f"{market} Amazon 新品榜没有得到 ASIN")
            continue
        records.extend(seed_records)
    return records


def run_discovery_flow(payload: dict) -> dict:
    requested_run_dir = payload.get("run_dir")
    saved_task = None
    if requested_run_dir:
        saved_path = Path(requested_run_dir).expanduser().resolve() / "02-task.json"
        if saved_path.exists():
            saved_task = _read_json(saved_path)
    task = saved_task or create_task(payload.get("request"), payload.get("task"), payload.get("strategy_selection"))
    run_dir = (
        Path(requested_run_dir).expanduser().resolve()
        if requested_run_dir
        else (Path.cwd() / "outputs" / "kaifa-runs" / task["task_id"]).resolve()
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(task, run_dir)
    manifest["artifacts"]["request"] = _write_json(run_dir / "01-request.json", {"request": task.get("request")})
    manifest["artifacts"]["task"] = _write_json(run_dir / "02-task.json", task)
    manifest["artifacts"]["strategy"] = _write_json(run_dir / "03-strategy-resolution.json", task["strategy_resolution"])
    _save_manifest(manifest, run_dir)

    records, candidates, sources = _load_input_data(payload)
    saved_records_path = run_dir / "07-source-records.json"
    if not records and not candidates and saved_records_path.exists():
        records = (_read_json(saved_records_path).get("records") or [])
    if not records and not candidates:
        strategy_ids = task["strategy_resolution"]["strategy_ids"]
        if strategy_ids == ["E"] and (payload.get("discovery") or {}).get("collect_live", True):
            try:
                records = _live_strategy_e(task, payload, run_dir, manifest)
            except ContractError as exc:
                return _stop(manifest, run_dir, "AWAITING_CATEGORY_INPUT", "collection", [str(exc)])
        else:
            return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "collection", ["discovery_records_or_paths"])
    if records:
        records = _apply_category_context(records, task)
        records = _enrich_records_from_sellersprite(records, payload, run_dir, manifest)
    for row in records:
        row.setdefault("source_strategy", task["strategy_resolution"]["primary_strategy"])
    if records:
        manifest["artifacts"]["source_records"] = _write_json(
            saved_records_path,
            {"records": records, "sources": sources, "count": len(records)},
        )
    candidates = candidates or merge_candidates(records)
    if not candidates:
        return _stop(manifest, run_dir, "NO_CANDIDATES", "candidate_merge", ["usable_marketplace_and_asin"])
    manifest["artifacts"]["candidate_pool"] = _write_json(
        run_dir / "08-candidate-pool.json",
        {"candidates": candidates, "count": len(candidates)},
    )
    screening = score_candidates(
        candidates,
        int(payload.get("shortlist_limit") or task.get("shortlist_limit") or 20),
        payload.get("as_of_date"),
    )
    manifest["artifacts"]["screening"] = _write_json(run_dir / "09-screening.json", screening)
    rows = table_rows(screening)
    manifest["artifacts"]["table_rows"] = _write_json(run_dir / "10-table-rows.json", {"rows": rows})
    workbook = export_discovery_workbook(payload.get("output_path") or (run_dir / "开品结果.xlsx"), rows)
    manifest["artifacts"]["workbook"] = workbook["path"]
    manifest.update({"status": "COMPLETE", "current_stage": "delivery", "blocking_items": []})
    _save_manifest(manifest, run_dir)
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "status": "COMPLETE",
        "strategy_resolution": task["strategy_resolution"],
        "category_resolution": task["category_resolution"],
        "counts": {"source_records": len(records), **screening["counts"]},
        "score_method": screening["method"],
        "workbook": workbook,
        "artifacts": dict(manifest["artifacts"]),
        "warnings": list(manifest["warnings"]),
        "run_dir": str(run_dir),
    }


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ContractError("input must be a JSON object")
    action = payload.get("skill_action") or "run_discovery_flow"
    if action == "status":
        return {
            "ok": True,
            "skill": "chenyu-xuanpin",
            "purpose": "选品、分析评分并生成开品表格",
            "actions": ["status", "list_strategies", "resolve_request", "run_discovery_flow", "resume_discovery_flow", "enrich_sellersprite", "browser_status", "browser_login_sellersprite"],
        }
    if action == "list_strategies":
        return {"ok": True, "strategies": list_strategies(load_rules())}
    if action == "resolve_request":
        return {"ok": True, "task": create_task(payload.get("request"), payload.get("task"), payload.get("strategy_selection"))}
    if action in {"run_discovery_flow", "resume_discovery_flow"}:
        return run_discovery_flow(payload)
    if action == "enrich_sellersprite":
        updated = dict(payload)
        discovery = dict(updated.get("discovery") or {})
        discovery["sellersprite_enrich"] = True
        if "refresh_sellersprite" not in discovery:
            discovery["refresh_sellersprite"] = True
        updated["discovery"] = discovery
        return run_discovery_flow(updated)
    if action == "browser_status":
        return {"ok": True, "browser": browser_status()}
    if action == "browser_login_sellersprite":
        return {"ok": True, "browser": login_sellersprite(payload)}
    raise ContractError(f"unknown skill_action: {action}")


def main() -> None:
    try:
        result = handle(json.loads(sys.stdin.buffer.read().decode("utf-8-sig")))
    except (json.JSONDecodeError, ContractError, DiscoveryError, WorkbookError, StrategyRouteError, BrowserCollectionError, OSError, KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "code": "invalid_input", "message": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
