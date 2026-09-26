"""Single-skill Amazon product discovery workflow."""
from __future__ import annotations

import json
import hashlib
from itertools import zip_longest
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from discovery_pipeline import DiscoveryError, merge_candidates, score_candidates, table_rows
from discovery_workbook import WorkbookError, export_discovery_workbook
from new_releases_history import (
    HistoryDatabaseError,
    analyze_new_releases_database,
    discovery_records_from_history,
)
from playwright_collector import BrowserCollectionError, browser_status, collect, collect_sellersprite_by_asin, login_sellersprite
from strategy_router import StrategyRouteError, list_strategies, resolve_category, resolve_strategy
from category_sources import CategoryInputError, resolve_sources

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"
FLOW_VERSION = "discovery-v3"
RUN_INPUT_KEYS = {
    "skill_action", "request", "task", "strategy_selection", "run_dir",
    "discovery_records", "candidates", "discovery_paths", "discovery",
    "profile_dir", "as_of_date", "shortlist_limit", "output_path",
}
TASK_INPUT_KEYS = {"task_id", "shortlist_limit", "categories", "strategy_ids", "source_marketplaces"}
DISCOVERY_INPUT_KEYS = {
    "source", "history", "collect_live", "refresh", "refresh_sellersprite",
    "sellersprite_enrich", "headless", "limit_per_marketplace", "max_pages",
    "query_timeout_ms", "query_delay_ms", "query_poll_ms", "empty_grace_ms",
    "batch_queries", "batch_size", "manual_timeout_seconds", "profile_dir",
}
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


def _find_chenyu_ai_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if candidate.name.lower() == "chenyu-ai" and (candidate / "plugins" / "chenyu-kaifa").is_dir():
            return candidate
        child = candidate / "chenyu-ai"
        if (child / "plugins" / "chenyu-kaifa").is_dir():
            return child.resolve()
    raise ContractError("cannot locate the chenyu-ai repository; pass an explicit run_dir")


def _folder_component(value) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", str(value or "product-discovery"))
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text).strip(" .-_")
    return (text or "product-discovery")[:60].rstrip(" .-_")


def _default_run_dir(task: dict) -> Path:
    run_date = datetime.now(timezone.utc).astimezone().date().isoformat()
    product_name = _folder_component(task["category_resolution"].get("category_normalized") or task.get("request"))
    parent = _find_chenyu_ai_root() / "outputs" / "chenyu-kaifa" / "product-discovery"
    base_name = f"{run_date}_{product_name}"
    candidate = parent / base_name
    if not candidate.exists():
        return candidate
    suffix = 2
    while (parent / f"{base_name}_{suffix:02d}").exists():
        suffix += 1
    return parent / f"{base_name}_{suffix:02d}"


def create_task(request=None, task=None, strategy_selection=None) -> dict:
    rules = load_rules()
    task = dict(task or {})
    unknown = sorted(set(task) - TASK_INPUT_KEYS)
    if unknown:
        raise ContractError("unsupported task fields: " + ", ".join(unknown))
    strategy = resolve_strategy(request, task, strategy_selection, rules)
    category = resolve_category(request, task)
    return {
        "flow_version": FLOW_VERSION,
        "task_id": task.get("task_id") or f"discovery-{uuid.uuid4().hex[:12]}",
        "request": request,
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
        "image_url",
        "detail_url",
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
                if field == "image_url":
                    image_url = str(value or "").lower()
                    if "sellersprite.com/v3/webapp/static/" in image_url or image_url.endswith("/ai-guide.png"):
                        continue
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
    category_name = category.get("category_normalized")
    if not category_name:
        return records
    for row in records:
        if not (row.get("category_name") or row.get("category_node")):
            row["category_name"] = category_name
    return records


def _cacheable_empty(outcome: dict) -> bool:
    if not (outcome.get("status") == "not_found" and outcome.get("empty_verified") is True
            and outcome.get("auth_verified") is True and outcome.get("stop_reason") == "confirmed_empty"):
        return False
    try:
        observed = datetime.fromisoformat(outcome["observed_at"])
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        return 0 <= age < 86400
    except (KeyError, ValueError, TypeError):
        return False


def _enrich_records_from_sellersprite(
    records: list[dict], payload: dict, run_dir: Path, manifest: dict
) -> list[dict]:
    discovery = dict(payload.get("discovery") or {})
    if not discovery.get("sellersprite_enrich", True):
        return records
    refresh = bool(discovery.get("refresh_sellersprite"))
    headless = bool(discovery.get("headless", True))
    output = list(records)
    for row in output:
        image_url = str(row.get("image_url") or "").lower()
        if "sellersprite.com/v3/webapp/static/" in image_url or image_url.endswith("/ai-guide.png"):
            row.pop("image_url", None)
    for market in ("US", "DE"):
        warning_prefix = f"{market} 卖家精灵补数未完整："
        manifest["warnings"] = [
            warning for warning in (manifest.get("warnings") or [])
            if not str(warning).startswith(warning_prefix)
        ]
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
        cached_outcomes = list(cached_result.get("outcomes") or [])
        query_metadata = list(cached_result.get("query_metadata") or [])
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
        cached_unavailable_asins = {
            str(outcome.get("asin") or "").upper()
            for outcome in cached_outcomes
            if _cacheable_empty(outcome)
        }
        to_query = target_asins if refresh else [
            asin for asin in target_asins
            if asin not in cached_asins and asin not in cached_unavailable_asins
        ]
        query_results = []
        outcomes = [] if refresh else cached_outcomes
        for offset in range(0, len(to_query), 100):
            chunk = to_query[offset : offset + 100]
            result = collect_sellersprite_by_asin(
                {
                    "marketplace": market,
                    "asins": chunk,
                    "headless": headless,
                    "query_timeout_ms": discovery.get("query_timeout_ms", 8000),
                    "query_delay_ms": discovery.get("query_delay_ms", 200),
                    "query_poll_ms": discovery.get("query_poll_ms", 200),
                    "empty_grace_ms": discovery.get("empty_grace_ms", 800),
                    "batch_queries": discovery.get("batch_queries", True),
                    "batch_size": discovery.get("batch_size", 60),
                    "manual_timeout_seconds": discovery.get("manual_timeout_seconds", 180),
                    "profile_dir": discovery.get("profile_dir") or payload.get("profile_dir"),
                }
            )
            query_results.append(result)
            seller_records.extend(result.get("records") or [])
            outcomes.extend(result.get("outcomes") or [])
            if result.get("source_metadata"):
                query_metadata.append(result["source_metadata"])
            if result.get("collection_status") == "blocked":
                break

        deduped = {}
        for row in seller_records:
            key = (str(row.get("marketplace") or market).upper(), str(row.get("asin") or "").upper())
            if all(key):
                deduped[key] = row
        seller_records = list(deduped.values())
        outcome_by_asin = {}
        for outcome in outcomes:
            asin = str(outcome.get("asin") or "").upper()
            if asin:
                outcome_by_asin[asin] = outcome
        outcomes = list(outcome_by_asin.values())
        enriched_asins = {key[1] for key in deduped}
        status = "complete" if all(asin in enriched_asins for asin in target_asins) else "partial"
        block_reasons = [result.get("block_reason") for result in query_results if result.get("block_reason")]
        raw_payload = {
            "collection_status": "blocked" if block_reasons else status,
            "block_reason": block_reasons[0] if block_reasons else None,
            "records": seller_records,
            "outcomes": outcomes,
            "query_metadata": query_metadata,
            "counts": {
                "requested": len(target_asins),
                "queried": len(to_query),
                "skipped_cached_unavailable": len([
                    asin for asin in target_asins
                    if asin in cached_unavailable_asins and asin not in cached_asins
                ]),
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
        if block_reasons:
            manifest.setdefault("enrichment_blocking_items", []).extend(block_reasons)
        if raw_payload["collection_status"] != "complete":
            manifest["enrichment_incomplete"] = True
            manifest["warnings"].append(
                f"{market} 卖家精灵补数未完整：{raw_payload['counts']['missing']} 个 ASIN 未补齐，相关商品标记待补数据。"
            )
        if block_reasons:
            break
    return output


def _load_input_data(payload: dict) -> tuple[list[dict], list[dict], list[str]]:
    records = list(payload.get("discovery_records") or [])
    candidates = list(payload.get("candidates") or [])
    sources = []
    paths = list(payload.get("discovery_paths") or [])
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


def _record_timing(manifest: dict, stage: str, started: float) -> None:
    manifest.setdefault("timings_ms", {})[stage] = round((time.perf_counter() - started) * 1000)


def _stop(manifest: dict, run_dir: Path, status: str, stage: str, blocking_items: list[str]) -> dict:
    manifest.update({"status": status, "current_stage": stage, "blocking_items": blocking_items})
    _save_manifest(manifest, run_dir)
    return {
        "ok": status != "AWAITING_ENRICHMENT",
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
    sources = resolve_sources(task["category_resolution"], task["strategy_resolution"]["source_marketplaces"])
    manifest["artifacts"]["category_sources"] = _write_json(run_dir / "04-category-sources.json", sources)
    batches = {}
    for source in sources:
        market = source["marketplace"]
        cache_input = {**source, "max_pages": discovery.get("max_pages", 1), "limit": limit}
        digest = hashlib.sha256(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()[:16]
        amazon_path = run_dir / f"04-amazon-{market.lower()}-{digest}-asins.json"
        seed_records = []
        if amazon_path.exists() and not discovery.get("refresh"):
            amazon_result = _read_json(amazon_path)
            seed_records = amazon_result.get("records") or []
        if not seed_records:
            amazon_result = collect({
                "source": "amazon_public", "url": source["url"],
                "extractor": "amazon_ranked_list", "marketplace": market,
                "query": source["category"], "max_pages": discovery.get("max_pages", 1),
                "headless": headless,
            })
            seed_records = _identity_only(amazon_result.get("records") or [], market, limit)
            for row in seed_records:
                row.setdefault("category_name", source["category"])
                row.setdefault("source_ref", source["url"])
            amazon_result = {
                "source": source, "collection_status": amazon_result.get("collection_status"),
                "source_metadata": amazon_result.get("source_metadata"),
                "errors": amazon_result.get("errors") or [], "records": seed_records,
                "counts": {"records": len(seed_records)},
            }
            _write_json(amazon_path, amazon_result)
        manifest["artifacts"][f"amazon_{market.lower()}_{digest}"] = str(amazon_path.resolve())
        if not seed_records:
            manifest["warnings"].append(f"{market} / {source['category']} Amazon 新品榜没有得到 ASIN")
        batches.setdefault(market, []).append(seed_records)
    records = []
    for market, category_batches in batches.items():
        # Round robin retains multiple categories within the existing per-market limit.
        selected = {}
        for group in zip_longest(*category_batches):
            for row in group:
                if row is None:
                    continue
                asin = row["asin"]
                if asin not in selected and len(selected) < limit:
                    selected[asin] = dict(row)
                if asin in selected:
                    refs = selected[asin].setdefault("source_refs", [])
                    if row.get("source_ref") and row["source_ref"] not in refs:
                        refs.append(row["source_ref"])
        market_records = list(selected.values())
        manifest["artifacts"][f"amazon_{market.lower()}"] = _write_json(
            run_dir / f"04-amazon-{market.lower()}-asins.json",
            {"records": market_records, "counts": {"records": len(market_records)}},
        )
        records.extend(market_records)
    return records


def _history_database_source(task: dict, payload: dict, run_dir: Path, manifest: dict) -> list[dict]:
    discovery = dict(payload.get("discovery") or {})
    history = dict(discovery.get("history") or {})
    history.setdefault("days", 10)
    history.setdefault("limit", 100)

    analysis_payload = {
        "history": history,
        "marketplaces": task["strategy_resolution"]["source_marketplaces"],
        "as_of_date": payload.get("as_of_date"),
    }
    report = analyze_new_releases_database(analysis_payload)
    manifest["artifacts"]["new_releases_history"] = _write_json(
        run_dir / "04-new-releases-history.json",
        report,
    )
    manifest["warnings"].extend(report.get("warnings") or [])
    limit = max(1, min(int(history.get("limit", 100)), 1000))
    return discovery_records_from_history(report, limit=limit)


def run_discovery_flow(payload: dict) -> dict:
    flow_started = time.perf_counter()
    unknown_input = sorted(set(payload) - RUN_INPUT_KEYS)
    if unknown_input:
        raise ContractError("unsupported input fields: " + ", ".join(unknown_input))
    requested_run_dir = payload.get("run_dir")
    saved_task = None
    if requested_run_dir:
        saved_path = Path(requested_run_dir).expanduser().resolve() / "02-task.json"
        if saved_path.exists():
            saved_task = _read_json(saved_path)
    task_updates = payload.get("task") or {}
    discovery = dict(payload.get("discovery") or {})
    unknown_discovery = sorted(set(discovery) - DISCOVERY_INPUT_KEYS)
    if unknown_discovery:
        raise ContractError("unsupported discovery fields: " + ", ".join(unknown_discovery))
    if saved_task:
        if saved_task.get("flow_version") != FLOW_VERSION:
            raise ContractError("run_dir flow_version does not match current workflow")
        if task_updates or payload.get("strategy_selection"):
            updated = {"task_id": saved_task["task_id"], "shortlist_limit": saved_task["shortlist_limit"],
                       "categories": saved_task["category_resolution"]["categories"], **task_updates}
            task = create_task(saved_task.get("request"), updated,
                               payload.get("strategy_selection") or saved_task["strategy_resolution"])
            task["created_at"] = saved_task["created_at"]
        else:
            task = saved_task
    else:
        task = create_task(payload.get("request"), task_updates, payload.get("strategy_selection"))
    run_dir = (
        Path(requested_run_dir).expanduser().resolve()
        if requested_run_dir
        else _default_run_dir(task).resolve()
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(task, run_dir)
    for stale in ("enrichment_blocking_items", "enrichment_incomplete", "blocking_items"):
        manifest.pop(stale, None)
    manifest["warnings"] = [warning for warning in manifest.get("warnings", []) if "卖家精灵补数未完整" not in warning]
    manifest["timings_ms"] = {}
    manifest["artifacts"]["request"] = _write_json(run_dir / "01-request.json", {"request": task.get("request")})
    manifest["artifacts"]["task"] = _write_json(run_dir / "02-task.json", task)
    manifest["artifacts"]["strategy"] = _write_json(run_dir / "03-strategy-resolution.json", task["strategy_resolution"])
    _save_manifest(manifest, run_dir)

    stage_started = time.perf_counter()
    records, candidates, sources = _load_input_data(payload)
    _record_timing(manifest, "input_loading", stage_started)
    saved_records_path = run_dir / "07-source-records.json"
    source_scope = {
        "category_resolution": task["category_resolution"],
        "marketplaces": task["strategy_resolution"]["source_marketplaces"],
        "discovery": {key: value for key, value in discovery.items()
                      if key not in {"refresh", "refresh_sellersprite", "sellersprite_enrich"}},
    }
    use_history_database = discovery.get("source") == "new_releases_db"
    if not records and not candidates and use_history_database:
        stage_started = time.perf_counter()
        records = _history_database_source(task, payload, run_dir, manifest)
        _record_timing(manifest, "history_database_analysis", stage_started)
        if not records:
            return _stop(
                manifest,
                run_dir,
                "NO_HISTORY_CANDIDATES",
                "history_database_analysis",
                ["NEW_REPEAT_OR_RISING_signals"],
            )
    refresh_live_e = (
        bool(discovery.get("refresh"))
        and task["strategy_resolution"]["strategy_ids"] == ["E"]
        and discovery.get("collect_live", True)
    )
    if not records and not candidates and saved_records_path.exists() and not refresh_live_e:
        saved_records = _read_json(saved_records_path)
        if saved_records.get("source_scope") == source_scope:
            records = saved_records.get("records") or []
    if not records and not candidates:
        strategy_ids = task["strategy_resolution"]["strategy_ids"]
        if strategy_ids == ["E"] and (payload.get("discovery") or {}).get("collect_live", True):
            try:
                stage_started = time.perf_counter()
                records = _live_strategy_e(task, payload, run_dir, manifest)
                _record_timing(manifest, "amazon_collection", stage_started)
            except (ContractError, CategoryInputError) as exc:
                return _stop(manifest, run_dir, "AWAITING_CATEGORY_INPUT", "collection", [str(exc)])
        else:
            return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "collection", ["discovery_records_or_paths"])
    if records:
        records = _apply_category_context(records, task)
        stage_started = time.perf_counter()
        records = _enrich_records_from_sellersprite(records, payload, run_dir, manifest)
        _record_timing(manifest, "sellersprite_enrichment", stage_started)
    for row in records:
        row.setdefault("source_strategy", task["strategy_resolution"]["primary_strategy"])
    if records:
        manifest["artifacts"]["source_records"] = _write_json(
            saved_records_path,
            {"records": records, "sources": sources, "count": len(records), "source_scope": source_scope},
        )
    if manifest.get("enrichment_blocking_items"):
        return _stop(manifest, run_dir, "AWAITING_ENRICHMENT", "sellersprite_enrichment", manifest["enrichment_blocking_items"])
    stage_started = time.perf_counter()
    candidates = candidates or merge_candidates(records)
    _record_timing(manifest, "candidate_merge", stage_started)
    if not candidates:
        return _stop(manifest, run_dir, "NO_CANDIDATES", "candidate_merge", ["usable_marketplace_and_asin"])
    manifest["artifacts"]["candidate_pool"] = _write_json(
        run_dir / "08-candidate-pool.json",
        {"candidates": candidates, "count": len(candidates)},
    )
    stage_started = time.perf_counter()
    screening = score_candidates(
        candidates,
        int(payload.get("shortlist_limit") or task.get("shortlist_limit") or 20),
        payload.get("as_of_date"),
    )
    _record_timing(manifest, "scoring", stage_started)
    manifest["artifacts"]["screening"] = _write_json(run_dir / "09-screening.json", screening)
    if manifest.get("enrichment_incomplete") and not any(row.get("score_status") != "insufficient_data" and row.get("missing_data") == [] for row in screening["results"]):
        return _stop(manifest, run_dir, "AWAITING_ENRICHMENT", "scoring", ["没有足够数据的有效候选，不能交付待补数据表"])
    pending_count = sum(bool(row["missing_data"]) for row in screening["results"])
    if pending_count:
        manifest["warnings"].append(f"{pending_count} 个商品缺少关键评分字段，已标记待补数据，不作选品结论。")
    rows = table_rows(screening)
    manifest["artifacts"]["table_rows"] = _write_json(run_dir / "10-table-rows.json", {"rows": rows})
    stage_started = time.perf_counter()
    workbook = export_discovery_workbook(payload.get("output_path") or (run_dir / "开品结果.xlsx"), rows)
    _record_timing(manifest, "workbook_export", stage_started)
    _record_timing(manifest, "total", flow_started)
    manifest["artifacts"]["workbook"] = workbook["path"]
    delivery_status = "PARTIAL" if pending_count or manifest.get("enrichment_incomplete") else "COMPLETE"
    manifest.update({"status": delivery_status, "current_stage": "delivery", "blocking_items": []})
    _save_manifest(manifest, run_dir)
    return {
        "ok": True,
        "run_id": manifest["run_id"],
        "status": delivery_status,
        "strategy_resolution": task["strategy_resolution"],
        "category_resolution": task["category_resolution"],
        "counts": {"source_records": len(records), **screening["counts"]},
        "score_method": screening["method"],
        "workbook": workbook,
        "artifacts": dict(manifest["artifacts"]),
        "warnings": list(manifest["warnings"]),
        "timings_ms": dict(manifest["timings_ms"]),
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
            "actions": ["status", "list_strategies", "resolve_request", "analyze_new_releases_db", "run_discovery_flow", "resume_discovery_flow", "enrich_sellersprite", "browser_status", "browser_login_sellersprite"],
        }
    if action == "list_strategies":
        return {"ok": True, "strategies": list_strategies(load_rules())}
    if action == "resolve_request":
        return {"ok": True, "task": create_task(payload.get("request"), payload.get("task"), payload.get("strategy_selection"))}
    if action == "analyze_new_releases_db":
        return analyze_new_releases_database(payload)
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
    except (json.JSONDecodeError, ContractError, CategoryInputError, DiscoveryError, WorkbookError, StrategyRouteError, BrowserCollectionError, HistoryDatabaseError, OSError, KeyError, TypeError, ValueError) as exc:
        result = {"ok": False, "code": "invalid_input", "message": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
