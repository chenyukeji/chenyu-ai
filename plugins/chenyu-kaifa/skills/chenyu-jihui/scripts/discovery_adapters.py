"""Read-only discovery import adapters for A/E/J strategy records."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50000

CANONICAL_FIELDS = {
    "marketplace",
    "asin",
    "parent_asin",
    "product_name",
    "product_name_normalized",
    "product_signature",
    "need_cluster",
    "seller_location",
    "fulfillment",
    "price",
    "currency",
    "estimated_sales",
    "sales_period",
    "sales_level",
    "review_count",
    "source_available_date",
    "observed_at",
    "source_entity_id",
    "source_ref",
}


class AdapterError(ValueError):
    pass


def _read_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data, {}
    if not isinstance(data, dict):
        raise AdapterError("JSON root must be an object or array")
    rows = data.get("rows")
    if rows is None:
        rows = data.get("records")
    if rows is None:
        rows = data.get("items")
    if rows is None:
        # Single canonical record is allowed.
        rows = [data]
        meta = {}
    else:
        meta = {k: v for k, v in data.items() if k not in {"rows", "records", "items"}}
    if not isinstance(rows, list):
        raise AdapterError("JSON rows/records/items must be a list")
    return rows, meta


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise AdapterError("CSV must have a header row")
        rows = list(reader)
    return rows, {}


def read_records(path_value: str):
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        raise AdapterError(f"input file not found: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise AdapterError(f"input file exceeds {MAX_FILE_BYTES} bytes")
    suffix = path.suffix.lower()
    if suffix == ".json":
        rows, meta = _read_json(path)
    elif suffix == ".csv":
        rows, meta = _read_csv(path)
    else:
        raise AdapterError("only .json and .csv discovery imports are supported")
    if len(rows) > MAX_ROWS:
        raise AdapterError(f"input contains more than {MAX_ROWS} rows")
    if any(not isinstance(row, dict) for row in rows):
        raise AdapterError("each imported row must be an object")
    return rows, meta


def apply_field_map(row: dict, field_map: dict | None):
    field_map = field_map or {}
    if not isinstance(field_map, dict):
        raise AdapterError("field_map must be an object")
    output = {}
    for canonical in CANONICAL_FIELDS:
        source = field_map.get(canonical, canonical)
        if source in row and row[source] not in ("", None):
            output[canonical] = row[source]
    return output


def _parse_number(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise AdapterError(f"{field} cannot be boolean")
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise AdapterError(f"{field} must be numeric: {value!r}") from exc


def _parse_iso_date(value, field):
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise AdapterError(f"{field} must begin with YYYY-MM-DD: {text!r}") from exc


def _normalize_text(value):
    return None if value in (None, "") else str(value).strip()


def normalize_row(row: dict, field_map: dict | None = None):
    item = apply_field_map(row, field_map)
    for key in ("marketplace", "seller_location", "fulfillment", "currency", "sales_level"):
        if key in item:
            item[key] = str(item[key]).strip().upper()
    for key in ("asin", "parent_asin"):
        if key in item:
            item[key] = str(item[key]).strip().upper()
    for key in ("product_name", "product_name_normalized", "product_signature", "need_cluster", "sales_period", "source_ref", "source_entity_id"):
        if key in item:
            item[key] = _normalize_text(item[key])
    for key in ("price", "estimated_sales", "review_count"):
        if key in item:
            item[key] = _parse_number(item[key], key)
    return item


def _age_days(source_available_date, as_of_date):
    source_date = _parse_iso_date(source_available_date, "source_available_date")
    as_of = _parse_iso_date(as_of_date, "as_of_date")
    if source_date is None or as_of is None:
        return None
    return (as_of - source_date).days


def strategy_assessment(item: dict, strategy_id: str, as_of_date: str | None = None):
    strategy_id = str(strategy_id).upper()
    reasons = []
    pending = []

    if strategy_id == "A":
        location = item.get("seller_location")
        if location is None:
            pending.append("seller_location")
        elif location == "CN":
            reasons.append("comparable_cn_seller")
        else:
            return {"status": "fail", "reason_codes": ["SELLER_LOCATION_NOT_CN"], "pending_fields": []}

    elif strategy_id == "E":
        market = item.get("marketplace")
        if market is None:
            pending.append("marketplace")
        elif market not in {"US", "DE"}:
            return {"status": "fail", "reason_codes": ["NEW_RELEASE_SOURCE_MARKET_NOT_US_DE"], "pending_fields": []}
        else:
            reasons.append("new_release_source_market")

    elif strategy_id == "J":
        fulfillment = item.get("fulfillment")
        if fulfillment is None:
            pending.append("fulfillment")
        elif fulfillment != "FBM":
            return {"status": "fail", "reason_codes": ["FULFILLMENT_NOT_FBM"], "pending_fields": []}
        else:
            reasons.append("fbm_observed")

        if item.get("source_available_date") is None:
            pending.append("source_available_date")
        elif not as_of_date:
            pending.append("as_of_date")
        else:
            age = _age_days(item.get("source_available_date"), as_of_date)
            if age is not None:
                if age < 0:
                    return {"status": "fail", "reason_codes": ["SOURCE_DATE_IN_FUTURE"], "pending_fields": []}
                if age > 60:
                    return {"status": "fail", "reason_codes": ["AGE_OVER_60_DAYS"], "pending_fields": []}
                reasons.append("age_0_to_60_days")
    else:
        raise AdapterError(f"file adapter currently supports A/E/J, got {strategy_id}")

    status = "unknown" if pending else "pass"
    return {"status": status, "reason_codes": reasons, "pending_fields": sorted(set(pending))}


def import_discovery_file(
    path_value: str,
    strategy_id: str,
    field_map: dict | None = None,
    as_of_date: str | None = None,
    source_type: str = "file_import",
    requested_filters: dict | None = None,
    applied_filters: dict | None = None,
    filter_verification: str | None = None,
):
    rows, file_meta = read_records(path_value)
    accepted = []
    pending = []
    rejected = []

    requested_filters = requested_filters if requested_filters is not None else file_meta.get("requested_filters")
    applied_filters = applied_filters if applied_filters is not None else file_meta.get("applied_filters")
    filter_verification = filter_verification or file_meta.get("filter_verification")
    if filter_verification is None:
        if isinstance(requested_filters, dict) and isinstance(applied_filters, dict):
            filter_verification = "verified" if requested_filters == applied_filters else "mismatch"
        else:
            filter_verification = "unverified"
    if filter_verification not in {"verified", "unverified", "mismatch", "partial"}:
        raise AdapterError("filter_verification must be verified/unverified/mismatch/partial")

    for index, raw in enumerate(rows, start=1):
        item = normalize_row(raw, field_map)
        if not (item.get("asin") or item.get("parent_asin") or item.get("product_signature") or item.get("source_entity_id")):
            rejected.append({"row": index, "reason_codes": ["MISSING_PRODUCT_IDENTITY"], "raw": raw})
            continue

        assessment = strategy_assessment(item, strategy_id, as_of_date)
        item["source_strategy"] = str(strategy_id).upper()
        item["source_type"] = source_type
        item["source_row"] = index
        item["strategy_match_status"] = assessment["status"]
        item["strategy_reason_codes"] = assessment["reason_codes"]
        item["strategy_pending_fields"] = assessment["pending_fields"]
        item["filter_verification"] = filter_verification
        item["requested_filters"] = requested_filters
        item["applied_filters"] = applied_filters
        item["source_ref"] = item.get("source_ref") or f"{Path(path_value).name}#row={index}"

        if filter_verification == "mismatch":
            item["strategy_match_status"] = "unknown"
            if "filter_mismatch" not in item["strategy_pending_fields"]:
                item["strategy_pending_fields"].append("filter_mismatch")

        if assessment["status"] == "fail":
            rejected.append({"row": index, "reason_codes": assessment["reason_codes"], "normalized": item})
        elif item["strategy_match_status"] == "pass" and filter_verification == "verified":
            accepted.append(item)
        else:
            pending.append(item)

    return {
        "source": str(Path(path_value).resolve()),
        "source_type": source_type,
        "strategy_id": str(strategy_id).upper(),
        "filter_verification": filter_verification,
        "requested_filters": requested_filters,
        "applied_filters": applied_filters,
        "file_metadata": file_meta,
        "accepted": accepted,
        "pending": pending,
        "rejected": rejected,
        "counts": {
            "rows": len(rows),
            "accepted": len(accepted),
            "pending": len(pending),
            "rejected": len(rejected),
        },
    }
