"""Read-only supplier quote import and validation (stdlib only)."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50000

FIELDS = {
    "supplier",
    "supplier_sku",
    "variant_ref",
    "material",
    "size",
    "color",
    "pack_count",
    "currency",
    "unit_quote_cny",
    "packaging_cny",
    "packaging_included",
    "moq",
    "min_qty",
    "max_qty",
    "stock_qty",
    "lead_time_days",
    "quote_observed_at",
    "quote_valid_until",
    "domestic_shipping_cny",
    "inspection_cny",
    "source_ref",
}


class QuoteImportError(ValueError):
    pass


def _bool(value):
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "包含"}:
        return True
    if text in {"0", "false", "no", "n", "否", "不包含"}:
        return False
    raise QuoteImportError(f"invalid boolean value: {value!r}")


def _num(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise QuoteImportError(f"{field} cannot be boolean")
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise QuoteImportError(f"{field} must be numeric: {value!r}") from exc


def _date(value, field):
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise QuoteImportError(f"{field} must begin with YYYY-MM-DD") from exc


def _read(path: Path):
    if not path.exists() or not path.is_file():
        raise QuoteImportError(f"quote file not found: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise QuoteImportError("quote file exceeds size limit")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("rows") or data.get("quotes") or data.get("records")
            if rows is None:
                rows = [data]
        else:
            raise QuoteImportError("JSON root must be object or array")
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise QuoteImportError("CSV must have headers")
            rows = list(reader)
    else:
        raise QuoteImportError("only .json and .csv quote imports are supported")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise QuoteImportError("quote rows must be objects")
    if len(rows) > MAX_ROWS:
        raise QuoteImportError("too many quote rows")
    return rows


def _map(row, field_map):
    field_map = field_map or {}
    if not isinstance(field_map, dict):
        raise QuoteImportError("field_map must be an object")
    out = {}
    for field in FIELDS:
        source = field_map.get(field, field)
        if source in row and row[source] not in ("", None):
            out[field] = row[source]
    return out


def normalize_quote(row, field_map=None):
    q = _map(row, field_map)
    for field in ("supplier", "supplier_sku", "variant_ref", "material", "size", "color", "currency", "source_ref"):
        if field in q:
            q[field] = str(q[field]).strip()
    if q.get("currency"):
        q["currency"] = q["currency"].upper()
    for field in (
        "pack_count",
        "unit_quote_cny",
        "packaging_cny",
        "moq",
        "min_qty",
        "max_qty",
        "stock_qty",
        "lead_time_days",
        "domestic_shipping_cny",
        "inspection_cny",
    ):
        if field in q:
            q[field] = _num(q[field], field)
    if "packaging_included" in q:
        q["packaging_included"] = _bool(q["packaging_included"])
    return q


def assess_quote(quote, planned_quantity=None, as_of_date=None):
    pending = []
    failures = []

    if not quote.get("supplier_sku"):
        failures.append("MISSING_SUPPLIER_SKU")
    if not quote.get("supplier"):
        pending.append("supplier")
    if quote.get("currency") not in {None, "CNY"}:
        pending.append("currency_conversion_required")
    if quote.get("unit_quote_cny") is None:
        pending.append("unit_quote_cny")

    quantity = _num(planned_quantity, "planned_quantity") if planned_quantity is not None else None
    if quantity is None:
        pending.append("planned_quantity")
    else:
        min_qty = quote.get("min_qty")
        max_qty = quote.get("max_qty")
        moq = quote.get("moq")
        lower = min_qty if min_qty is not None else moq
        if lower is not None and quantity < lower:
            failures.append("PLANNED_QTY_BELOW_QUOTE_RANGE")
        if max_qty is not None and quantity > max_qty:
            failures.append("PLANNED_QTY_ABOVE_QUOTE_RANGE")

    valid_until = _date(quote.get("quote_valid_until"), "quote_valid_until")
    as_of = _date(as_of_date, "as_of_date") if as_of_date else None
    if valid_until and as_of and as_of > valid_until:
        failures.append("QUOTE_EXPIRED")
    elif not quote.get("quote_valid_until"):
        pending.append("quote_valid_until")
    elif as_of is None:
        pending.append("as_of_date")

    packaging_included = quote.get("packaging_included")
    packaging = quote.get("packaging_cny")
    if packaging_included is True:
        effective_packaging = 0.0
    elif packaging is not None:
        effective_packaging = packaging
    else:
        effective_packaging = None
        pending.append("packaging_cny_or_included_flag")

    if failures:
        status = "invalid"
    elif pending:
        status = "pending"
    else:
        status = "valid"

    return {
        "status": status,
        "reason_codes": failures,
        "pending_fields": sorted(set(pending)),
        "planned_quantity": quantity,
        "effective_packaging_cny": effective_packaging,
    }


def import_supplier_quotes(path_value, field_map=None, planned_quantity=None, as_of_date=None):
    path = Path(path_value)
    rows = _read(path)
    valid = []
    pending = []
    invalid = []
    for index, row in enumerate(rows, start=1):
        quote = normalize_quote(row, field_map)
        quote["source_ref"] = quote.get("source_ref") or f"{path.name}#row={index}"
        quote["source_row"] = index
        assessment = assess_quote(quote, planned_quantity, as_of_date)
        quote["assessment"] = assessment
        quote["match_supplier_item"] = {
            "supplier": quote.get("supplier"),
            "supplier_sku": quote.get("supplier_sku"),
            "material": quote.get("material"),
            "size": quote.get("size"),
            "color": quote.get("color"),
            "pack_count": quote.get("pack_count"),
            "unit_quote_cny": quote.get("unit_quote_cny"),
            "packaging_cny": assessment.get("effective_packaging_cny"),
            "moq": quote.get("moq") if quote.get("moq") is not None else quote.get("min_qty"),
            "lead_time_days": quote.get("lead_time_days"),
            "quote_observed_at": quote.get("quote_observed_at"),
            "quote_valid_until": quote.get("quote_valid_until"),
            "source_ref": quote.get("source_ref"),
        }
        if assessment["status"] == "valid":
            valid.append(quote)
        elif assessment["status"] == "pending":
            pending.append(quote)
        else:
            invalid.append(quote)
    return {
        "source": str(path.resolve()),
        "valid": valid,
        "pending": pending,
        "invalid": invalid,
        "counts": {"rows": len(rows), "valid": len(valid), "pending": len(pending), "invalid": len(invalid)},
    }
