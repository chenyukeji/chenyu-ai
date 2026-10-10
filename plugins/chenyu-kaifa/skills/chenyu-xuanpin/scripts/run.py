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
from sellersprite_j import collect_recent_fbm
from sellersprite_h import collect_monthly_surges
import strategy_h
import strategy_evidence
from strategy_inputs import read_input
from strategy_j import (
    ai_analysis_requests, apply_ai_analyses, qualify_recent_fbm,
    score_recent_fbm, table_rows_recent_fbm,
)
from strategy_router import StrategyRouteError, list_strategies, resolve_category, resolve_strategy
from category_sources import CategoryInputError, resolve_sources

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"
FLOW_VERSION = "discovery-v4"
RUN_INPUT_KEYS = {
    "skill_action", "request", "task", "strategy_selection", "run_dir",
    "discovery_records", "candidates", "discovery_paths", "discovery",
    "profile_dir", "as_of_date", "shortlist_limit", "output_path", "j_ai_analyses",
}
TASK_INPUT_KEYS = {"task_id", "shortlist_limit", "categories", "strategy_ids", "source_marketplaces"}
DISCOVERY_INPUT_KEYS = {
    "source", "history", "collect_live", "refresh", "refresh_sellersprite",
    "sellersprite_enrich", "headless", "limit_per_marketplace", "max_pages",
    "query_timeout_ms", "query_delay_ms", "query_poll_ms", "empty_grace_ms",
    "batch_queries", "batch_size", "manual_timeout_seconds", "profile_dir",
    "j_min_monthly_sales", "j_keyword", "j_enrich_details",
    "h_following_months", "h_min_monthly_sales", "h_min_growth_percent", "h_keyword",
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
SKIPPED_ENRICHMENT_REASONS = {"query_parse_error"}


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
        merged["source_strategy"] = seed.get("source_strategy", "E")
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
        skipped = [
            {"marketplace": market, "asin": asin, "reason": outcome.get("stop_reason")}
            for asin, outcome in outcome_by_asin.items()
            if asin in target_asins and asin not in enriched_asins
            and outcome.get("status") == "query_failed"
            and outcome.get("stop_reason") in SKIPPED_ENRICHMENT_REASONS
        ]
        manifest.setdefault("skipped_asins", []).extend(skipped)
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
                "skipped": len(skipped),
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
            if skipped:
                manifest["warnings"].append(
                    f"{market} 卖家精灵补数未完整：{len(skipped)} 个 ASIN 解析失败，已跳过并保留原始查询证据。"
                )
            pending = raw_payload["counts"]["missing"] - len(skipped)
            if pending:
                manifest["warnings"].append(
                    f"{market} 卖家精灵补数未完整：{pending} 个 ASIN 未补齐，相关商品标记待补数据。"
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
        content, path = read_input(value)
        source_records, source_candidates = _content_records(content)
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


def _live_strategy_j(task: dict, payload: dict, run_dir: Path, manifest: dict) -> list[dict]:
    discovery = dict(payload.get("discovery") or {})
    records = []
    for market in task["strategy_resolution"]["source_marketplaces"]:
        query = {
            "marketplace": market,
            "min_monthly_sales": discovery.get("j_min_monthly_sales", 100),
            "keyword": discovery.get("j_keyword"),
            "max_pages": discovery.get("max_pages", 3),
            "headless": discovery.get("headless", True),
            "profile_dir": discovery.get("profile_dir") or payload.get("profile_dir"),
        }
        digest = hashlib.sha256(json.dumps({
            key: query[key] for key in ("marketplace", "min_monthly_sales", "keyword", "max_pages")
        }, sort_keys=True).encode()).hexdigest()[:12]
        path = run_dir / f"04-sellersprite-j-{market.lower()}-{digest}.json"
        cached = _read_json(path) if path.exists() and not discovery.get("refresh") else {}
        if cached.get("collection_status") == "complete":
            result = cached
        else:
            try:
                result = collect_recent_fbm(query)
            except Exception as exc:
                result = {
                    "collection_status": "blocked",
                    "block_reason": f"j_product_research_{type(exc).__name__}: {str(exc)[:180]}",
                    "records": [],
                }
            _write_json(path, result)
        manifest["artifacts"][f"sellersprite_j_{market.lower()}"] = str(path.resolve())
        if result.get("collection_status") == "blocked":
            manifest.setdefault("enrichment_blocking_items", []).append(
                f"{market}: {result.get('block_reason') or 'SellerSprite product research blocked'}"
            )
            break
        if result.get("collection_status") != "complete":
            manifest["enrichment_incomplete"] = True
            manifest["warnings"].append(f"{market} 卖家精灵选产品仅采集到部分可见结果，覆盖范围有限。")
        records.extend(result.get("records") or [])
    return records


def _enrich_j_shortlist_details(screening: dict, payload: dict, run_dir: Path, manifest: dict) -> None:
    """Add visible Amazon feature bullets without replacing SellerSprite screening facts."""
    discovery = dict(payload.get("discovery") or {})
    if discovery.get("j_enrich_details", True) is False:
        return
    outcomes = []
    for scored in screening["results"][:screening["counts"]["shortlisted"]]:
        row = scored["primary_listing"]
        if row.get("feature_bullets") or row.get("product_advantages"):
            continue
        site, asin = row["marketplace"], row["asin"]
        domain = "amazon.de" if site == "DE" else "amazon.com"
        url = f"https://www.{domain}/dp/{asin}"
        path = run_dir / f"08-j-product-detail-{site.lower()}-{asin}.json"
        if path.exists() and not discovery.get("refresh"):
            result = _read_json(path)
        else:
            try:
                result = collect({
                    "source": "amazon_public",
                    "url": url,
                    "extractor": "amazon_product",
                    "marketplace": site,
                    "max_pages": 1,
                    "headless": discovery.get("headless", True),
                })
            except Exception as exc:
                result = {
                    "collection_status": "blocked",
                    "block_reason": f"product_detail_{type(exc).__name__}: {str(exc)[:180]}",
                    "records": [],
                }
            _write_json(path, result)
        detail = next(
            (item for item in result.get("records") or []
             if str(item.get("asin") or "").upper() == asin),
            None,
        )
        bullets = [str(value).strip() for value in (detail or {}).get("feature_bullets") or []
                   if str(value).strip()]
        if bullets:
            row["feature_bullets"] = bullets[:10]
            row["detail_source_ref"] = detail.get("source_ref") or url
        outcomes.append({
            "candidate_id": scored["candidate_id"],
            "status": "enriched" if bullets else "unavailable",
            "source_path": str(path.resolve()),
        })
    if outcomes:
        manifest["artifacts"]["j_product_details"] = _write_json(
            run_dir / "08-j-product-details.json", {"outcomes": outcomes}
        )
        unavailable = sum(item["status"] == "unavailable" for item in outcomes)
        if unavailable:
            warning = (
                f"{unavailable} 个 J 候选未取得商品详情要点；AI 仅能根据已核实标题和指标分析，并须标注推断。"
            )
            if warning not in manifest["warnings"]:
                manifest["warnings"].append(warning)


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


def _run_evidence_strategy(task, payload, records, candidates, sources, source_scope, run_dir, manifest):
    strategy = task["strategy_resolution"]["primary_strategy"]
    markets = task["strategy_resolution"]["source_marketplaces"]
    discovery = dict(payload.get("discovery") or {})
    selection = task["strategy_resolution"]
    following = (selection.get("parameters") or {}).get("h_following_months", discovery.get("h_following_months", 2))
    months = strategy_h.target_months(payload.get("as_of_date"), following) if strategy == "H" else []
    if candidates:
        return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "strategy_evidence", ["该策略需要带原始证据的 discovery_records 或 discovery_paths，不能直接导入已评分候选"])
    coverage = list(manifest.get("strategy_coverage") or [])
    if strategy == "H" and not records and discovery.get("collect_live", True):
        for market in markets:
            try:
                result = collect_monthly_surges({
                    "marketplace": market, "months": months,
                    "min_monthly_sales": discovery.get("h_min_monthly_sales", 300),
                    "min_growth_percent": discovery.get("h_min_growth_percent", 10),
                    "keyword": discovery.get("h_keyword"), "max_pages": discovery.get("max_pages", 3),
                    "headless": discovery.get("headless", True),
                    "profile_dir": discovery.get("profile_dir") or payload.get("profile_dir"),
                })
            except Exception as exc:
                result = {"collection_status": "blocked", "records": [],
                          "block_reason": f"historical_monthly_collection_{type(exc).__name__}: {str(exc)[:180]}"}
            manifest["artifacts"][f"historical_months_{market.lower()}"] = _write_json(run_dir / f"04-h-{market.lower()}.json", result)
            coverage.append({"marketplace": market, "status": result.get("collection_status"), "months": result.get("coverage", [])})
            if result.get("collection_status") != "complete":
                manifest["warnings"].append(f"{market} 历史窗口采集未完整：{result.get('block_reason') or '分页或历史月份覆盖有限'}")
            records.extend(result.get("records") or [])
    if not records:
        help_text = ("请提供卖家精灵目标月份的销量飙升榜记录，或配置可访问历史月份的账号。目标月份：" + "、".join(months)) if strategy == "H" else strategy_evidence.INPUT_HELP[strategy]
        return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "strategy_evidence", [help_text, *manifest["warnings"]])
    if strategy == "H" and not coverage:
        for market in markets:
            present = {str(row.get("history_month") or row.get("month") or "")[:7] for row in records if str(row.get("marketplace") or "").upper() == market}
            missing = [month for month in months if month not in present]
            coverage.append({"marketplace": market, "status": "partial" if missing else "complete", "missing_months": missing})
            if missing:
                manifest["warnings"].append(f"{market} 导入资料未覆盖：{'、'.join(missing)}；缺少记录不代表零销量。")
    manifest["artifacts"]["source_records"] = _write_json(run_dir / "07-source-records.json", {"records": records, "sources": sources, "source_scope": source_scope, "coverage": coverage})
    limit = max(1, min(int(payload.get("shortlist_limit") or task.get("shortlist_limit") or 20), 1000))
    if strategy == "H":
        report = strategy_h.analyze_monthly_surge(records, months, markets,
            min_sales=float(discovery.get("h_min_monthly_sales", 300)),
            min_growth=float(discovery.get("h_min_growth_percent", 10)), shortlist_limit=limit)
        rows = strategy_h.table_rows(report)
        headers = ["站点", "产品名称", "ASIN", "所在品类", "历史命中月份", "月度销量与增长", "命中月份最高月销量", "最大环比增长率", "图片", "结论", "理由", "亚马逊产品链接", "来源链接"]
    else:
        report = strategy_evidence.analyze_evidence(strategy, records, markets, limit)
        rows = strategy_evidence.table_rows(report, load_rules()["strategy_registry"][strategy]["name"])
        headers = ["站点", "产品名称", "ASIN", "所在品类", "预估月销量", "售价（当地币种）", "Review数量", "图片", "策略", "策略证据", "结论", "理由", "亚马逊产品链接", "来源链接"]
    manifest["artifacts"]["screening"] = _write_json(run_dir / "09-screening.json", report)
    if not rows:
        return _stop(manifest, run_dir, "NO_QUALIFIED_CANDIDATES", "strategy_evidence", ["输入中没有满足该策略且证据完整的候选；原因见筛选记录"])
    manifest["artifacts"]["table_rows"] = _write_json(run_dir / "10-table-rows.json", {"rows": rows})
    workbook = export_discovery_workbook(payload.get("output_path") or (run_dir / "开品结果.xlsx"), rows, headers=headers)
    manifest["artifacts"]["workbook"] = workbook["path"]
    status = "PARTIAL" if any(x["status"] != "complete" for x in coverage) else "COMPLETE"
    manifest.update({"status": status, "current_stage": "delivery", "blocking_items": []})
    _save_manifest(manifest, run_dir)
    return {"ok": True, "status": status, "run_id": manifest["run_id"], "run_dir": str(run_dir),
            "workbook": workbook, "strategy_resolution": task["strategy_resolution"],
            "counts": {"source_records": len(records), "qualified": report["count"], "shortlisted": len(rows), "rejected": len(report["rejected"])},
            "score_method": report["method"], "warnings": manifest["warnings"], "artifacts": manifest["artifacts"]}


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
    previous_enrichment_incomplete = bool(manifest.get("enrichment_incomplete"))
    for stale in ("enrichment_blocking_items", "enrichment_incomplete", "blocking_items", "strategy_coverage", "skipped_asins"):
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
        "as_of_date": payload.get("as_of_date"),
        "category_resolution": task["category_resolution"],
        "marketplaces": task["strategy_resolution"]["source_marketplaces"],
        "strategies": task["strategy_resolution"]["strategy_ids"],
        "discovery": {key: value for key, value in discovery.items()
                      if key not in {"refresh", "refresh_sellersprite", "sellersprite_enrich"}},
    }
    if task["strategy_resolution"]["strategy_ids"] == ["H"]:
        parameters = task["strategy_resolution"].get("parameters") or {}
        source_scope["historical_months"] = strategy_h.target_months(payload.get("as_of_date"), parameters.get("h_following_months", discovery.get("h_following_months", 2)))
    use_history_database = discovery.get("source") == "new_releases_db"
    if use_history_database and task["strategy_resolution"]["strategy_ids"] != ["E"]:
        raise ContractError("新品榜历史数据库仅适用于 E；H 使用卖家精灵历史月份销量飙升榜")
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
    refresh_live = (
        bool(discovery.get("refresh"))
        and task["strategy_resolution"]["strategy_ids"] in (["E"], ["J"], ["H"])
        and discovery.get("collect_live", True)
    )
    if (not records and not candidates and saved_records_path.exists() and not refresh_live
            and not (task["strategy_resolution"]["strategy_ids"] == ["J"] and previous_enrichment_incomplete)):
        saved_records = _read_json(saved_records_path)
        if saved_records.get("source_scope") == source_scope:
            records = saved_records.get("records") or []
            manifest["strategy_coverage"] = saved_records.get("coverage") or []
    strategy_ids = task["strategy_resolution"]["strategy_ids"]
    if len(strategy_ids) > 1 and any(item in {"H", "I", "C", "K"} for item in strategy_ids):
        raise ContractError("新策略需逐项运行；请为每次调用明确指定一个 strategy_id，分别保留来源证据")
    if len(strategy_ids) == 1 and strategy_ids[0] in {"H", "I", "C", "K"}:
        return _run_evidence_strategy(task, payload, records, candidates, sources, source_scope, run_dir, manifest)
    if not records and not candidates and strategy_ids == ["J"] and discovery.get("collect_live", True):
        stage_started = time.perf_counter()
        records = _live_strategy_j(task, payload, run_dir, manifest)
        _record_timing(manifest, "sellersprite_j_collection", stage_started)
    if strategy_ids == ["J"] and manifest.get("enrichment_blocking_items"):
        if not records:
            return _stop(manifest, run_dir, "AWAITING_ENRICHMENT", "sellersprite_j_collection",
                         manifest["enrichment_blocking_items"])
        manifest["enrichment_incomplete"] = True
        manifest["warnings"].append(
            "部分站点卖家精灵采集受阻，仅交付已核实的站点候选：" +
            "、".join(manifest["enrichment_blocking_items"])
        )
    if strategy_ids == ["J"]:
        if not records and not candidates and not discovery.get("collect_live", True):
            return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "j_candidate_input",
                         ["J 已关闭实时采集，请提供卖家精灵产品记录"])
        if candidates and not records:
            return _stop(manifest, run_dir, "AWAITING_DISCOVERY_INPUT", "j_candidate_input",
                         ["J 需要含站点、ASIN、上架日期、FBM 和月销量的产品记录"])
        if records:
            manifest["artifacts"]["source_records"] = _write_json(
                saved_records_path, {"records": records, "sources": sources,
                                     "count": len(records), "source_scope": source_scope}
            )
        eligibility = qualify_recent_fbm(
            records, as_of_date=payload.get("as_of_date"),
            min_monthly_sales=int(discovery.get("j_min_monthly_sales", 100)),
        )
        manifest["artifacts"]["j_eligibility"] = _write_json(
            run_dir / "08-j-eligibility.json", eligibility
        )
        qualified = eligibility["accepted"]
        if not qualified:
            return _stop(manifest, run_dir, "NO_QUALIFIED_J_CANDIDATES", "j_eligibility",
                         ["没有经上架时间、FBM 和预估月销量三项证实的候选"])
        manifest["artifacts"]["candidate_pool"] = _write_json(
            run_dir / "08-candidate-pool.json",
            {"candidates": qualified, "count": len(qualified), "strategy": "J"},
        )
        screening = score_recent_fbm(
            qualified, records, as_of_date=payload.get("as_of_date"),
            shortlist_limit=int(payload.get("shortlist_limit") or task.get("shortlist_limit") or 20),
        )
        _enrich_j_shortlist_details(screening, payload, run_dir, manifest)
        requests = ai_analysis_requests(screening)
        manifest["artifacts"]["j_ai_analysis_requests"] = _write_json(
            run_dir / "09-j-ai-analysis-requests.json", {"requests": requests}
        )
        analyses = payload.get("j_ai_analyses")
        if analyses is None:
            pending = [item["candidate_id"] for item in requests]
        else:
            pending = apply_ai_analyses(screening, analyses)
        manifest["artifacts"]["screening"] = _write_json(run_dir / "09-screening.json", screening)
        if pending:
            result = _stop(
                manifest, run_dir, "AWAITING_AI_ANALYSIS", "j_ai_analysis",
                [f"需要 AI 分析的 J 候选：{', '.join(pending)}"],
            )
            result["analysis_requests"] = [
                item for item in requests if item["candidate_id"] in pending
            ]
            result["analysis_input_format"] = (
                "用同一 run_dir 续跑，并提交 j_ai_analyses 数组；每项包含 "
                "marketplace、asin、analysis；来源品类为空时还须包含 category_name。"
                "analysis 用简短中文合并有证据的商品特点、不足和机会判断。"
            )
            return result
        manifest["artifacts"]["j_ai_analyses"] = _write_json(
            run_dir / "10-j-ai-analyses.json", {"analyses": analyses}
        )
        rows = table_rows_recent_fbm(screening)
        manifest["artifacts"]["table_rows"] = _write_json(run_dir / "10-table-rows.json", {"rows": rows})
        workbook = export_discovery_workbook(
            payload.get("output_path") or (run_dir / "开品结果.xlsx"), rows
        )
        manifest["artifacts"]["workbook"] = workbook["path"]
        status = "PARTIAL" if manifest.get("enrichment_incomplete") else "COMPLETE"
        manifest.update({"status": status, "current_stage": "delivery", "blocking_items": []})
        _record_timing(manifest, "total", flow_started)
        _save_manifest(manifest, run_dir)
        return {"ok": True, "run_id": manifest["run_id"], "status": status,
                "strategy_resolution": task["strategy_resolution"],
                "category_resolution": task["category_resolution"],
                "counts": {**eligibility["counts"], **screening["counts"]},
                "score_method": screening["method"], "workbook": workbook,
                "artifacts": dict(manifest["artifacts"]),
                "warnings": list(manifest["warnings"]),
                "timings_ms": dict(manifest["timings_ms"]), "run_dir": str(run_dir)}
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
    skipped_keys = {
        (item["marketplace"], item["asin"])
        for item in manifest.get("skipped_asins", [])
    }
    if skipped_keys:
        records = [row for row in records if (str(row.get("marketplace") or "").upper(), str(row.get("asin") or "").upper()) not in skipped_keys]
        candidates = [row for row in candidates if (str(row.get("marketplace") or "").upper(), str(row.get("asin") or "").upper()) not in skipped_keys]
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
