from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .io_utils import write_csv, write_json
from .models import ProductMaster


REQUIRED_LISTING_FIELDS = {"title", "bullets", "description", "search_terms", "attributes"}
LOCALES = {"DE", "FR", "IT", "ES", "UK"}


def export_launch_package(
    product_master_data: dict[str, Any],
    listings: dict[str, Any],
    output_dir: str | Path,
    *,
    development_record: dict[str, Any] | None = None,
    node_executable: str | None = None,
    workbook_builder: str | Path | None = None,
) -> dict[str, Any]:
    development_record = development_record or {}
    master = ProductMaster.from_dict(product_master_data)
    target = Path(output_dir)
    listing_dir = target / "listing"
    image_dir = target / "images"
    compliance_dir = target / "compliance"
    for directory in (listing_dir, image_dir, compliance_dir):
        directory.mkdir(parents=True, exist_ok=True)

    listing_errors = _validate_listings(listings)
    for locale, content in listings.items():
        if locale.upper() not in LOCALES:
            continue
        bullets = content.get("bullets", [])
        text = [
            f"TITLE\n{content.get('title', '')}",
            "BULLETS\n" + "\n".join(f"{index}. {bullet}" for index, bullet in enumerate(bullets, start=1)),
            f"DESCRIPTION\n{content.get('description', '')}",
            f"SEARCH TERMS\n{content.get('search_terms', '')}",
            "ATTRIBUTES\n" + json.dumps(content.get("attributes", {}), ensure_ascii=False, indent=2),
        ]
        (listing_dir / f"{locale.upper()}.txt").write_text("\n\n".join(text) + "\n", encoding="utf-8")

    image_plan = build_image_plan(master)
    write_json(image_dir / "manifest.json", image_plan)
    write_json(target / "product_master.json", master.to_dict())
    if development_record:
        write_json(target / "product_decision_card.json", development_record)
    compliance_record = development_record.get("compliance") or master.compliance
    write_json(compliance_dir / "requirements.json", compliance_record)

    upload_rows = _upload_rows(master, listings)
    csv_path = write_csv(target / "amazon_upload.csv", upload_rows)
    xlsx_path = target / "amazon_upload.xlsx"
    workbook_error = _build_xlsx(
        upload_rows,
        xlsx_path,
        node_executable=node_executable,
        workbook_builder=workbook_builder,
    )

    checks = _prelaunch_checks(
        master,
        development_record,
        listings,
        listing_errors,
        workbook_error,
        xlsx_path,
    )
    write_json(target / "pre_launch_check.json", checks)
    return {
        "status": checks["status"],
        "output_dir": str(target.resolve()),
        "amazon_upload_csv": str(csv_path.resolve()),
        "amazon_upload_xlsx": str(xlsx_path.resolve()) if xlsx_path.exists() else "",
        "checks": checks,
    }


def build_image_plan(master: ProductMaster) -> list[dict[str, Any]]:
    functions = ", ".join(master.core_functions)
    common = f"Product facts: {master.product_name}, {master.quantity}, {master.color}, {master.material}; functions: {functions}."
    scenes = [
        ("01", "Main image", "Pure white background; product fills 85% of frame; no text or props", "Show the exact sellable quantity and packaging contents only"),
        ("02", "Core benefit", "Clean infographic with one primary benefit", "Make the main functional difference immediately understandable"),
        ("03", "In use", "Realistic target-customer usage scene", "Demonstrate fit, scale, and intended use"),
        ("04", "Dimensions", "Front and side views with dimension callouts", "Reduce size-related returns"),
        ("05", "Function detail", "Macro close-up of construction and functional area", "Prove material and feature quality"),
        ("06", "Scenario", "Contextual lifestyle scene relevant to the marketplace", "Connect the product to the purchase occasion"),
        ("07", "Multi-scenario", "Three-panel usage collage with restrained labels", "Show breadth without adding unsupported claims"),
    ]
    return [
        {
            "number": number,
            "name": name,
            "composition": composition,
            "purpose": purpose,
            "copy": "",
            "ai_prompt": f"Create an Amazon product image. {common} {composition}. Keep all product facts exact; do not invent accessories, certifications, or performance claims.",
        }
        for number, name, composition, purpose in scenes
    ]


def _validate_listings(listings: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not listings:
        return ["No marketplace listings supplied"]
    for locale, content in listings.items():
        code = locale.upper()
        if code not in LOCALES:
            errors.append(f"Unsupported listing locale: {locale}")
            continue
        missing = sorted(field for field in REQUIRED_LISTING_FIELDS if not content.get(field))
        if missing:
            errors.append(f"{code} missing fields: {', '.join(missing)}")
        if len(content.get("bullets", [])) != 5:
            errors.append(f"{code} must contain exactly 5 bullets")
    return errors


def _upload_rows(master: ProductMaster, listings: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for locale, content in listings.items():
        code = locale.upper()
        if code not in LOCALES:
            continue
        bullets = list(content.get("bullets", [])) + [""] * 5
        row = {
            "marketplace": code,
            "sku": master.sku,
            "ean": master.ean,
            "brand": master.brand,
            "title": content.get("title", ""),
            "bullet_1": bullets[0],
            "bullet_2": bullets[1],
            "bullet_3": bullets[2],
            "bullet_4": bullets[3],
            "bullet_5": bullets[4],
            "description": content.get("description", ""),
            "search_terms": content.get("search_terms", ""),
            "color": master.color,
            "material": master.material,
            "quantity": master.quantity,
            "weight_g": master.weight_g,
            "country_of_origin": master.country_of_origin,
            "manufacturer": master.manufacturer,
            "responsible_person": master.responsible_person,
            "price": master.target_price or "",
            "currency": master.currency,
            "quantity_available": master.initial_inventory,
        }
        row.update({f"attribute_{key}": value for key, value in content.get("attributes", {}).items()})
        rows.append(row)
    return rows


def _build_xlsx(
    rows: list[dict[str, Any]],
    output: Path,
    *,
    node_executable: str | None,
    workbook_builder: str | Path | None,
) -> str:
    node = node_executable or shutil.which("node")
    builder = (
        Path(workbook_builder)
        if workbook_builder
        else Path(__file__).resolve().parent
        / "scripts"
        / "build_amazon_upload.mjs"
    )
    if not node:
        return "Node.js was not found; CSV was produced but XLSX could not be generated"
    if not builder.exists():
        return f"Workbook builder not found: {builder}"
    input_json = output.with_suffix(".rows.json")
    write_json(input_json, rows)
    try:
        process = subprocess.run(
            [str(node), str(builder), str(input_json), str(output)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or "Workbook builder failed").strip()
            return f"Workbook builder exited with code {process.returncode}: {detail}"
    finally:
        input_json.unlink(missing_ok=True)
    return ""


def _prelaunch_checks(
    master: ProductMaster,
    development_record: dict[str, Any],
    listings: dict[str, Any],
    listing_errors: list[str],
    workbook_error: str,
    workbook_path: Path,
) -> dict[str, Any]:
    failures = list(listing_errors)
    warnings: list[str] = []
    for name in ("brand", "ean", "manufacturer", "responsible_person"):
        if not str(getattr(master, name)).strip():
            failures.append(f"Product Master field is empty: {name}")
    if master.target_price is None or master.target_price <= 0:
        failures.append("Product Master target_price must be positive")
    if master.initial_inventory <= 0:
        failures.append("Product Master initial_inventory must be positive")
    if not _valid_ean13(master.ean):
        failures.append("Product Master ean must be a valid EAN-13")
    compliance = development_record.get("compliance") or master.compliance
    compliance_risk = compliance.get("risk")
    if compliance_risk and compliance_risk != "low":
        failures.append("Compliance risk must be resolved before operations review")
    if compliance.get("missing_evidence"):
        failures.append("Compliance evidence is incomplete")
    if any(value is False for value in master.compliance.values()):
        failures.append("Product Master contains unresolved compliance items")
    if workbook_error:
        failures.append(workbook_error)
    if not workbook_path.exists():
        failures.append("amazon_upload.xlsx was not generated")
    if not compliance:
        failures.append("Product Master compliance object is empty")
    checks = {
        "development_record_supplied": bool(development_record),
        "development_recommendation": development_record.get("decision", ""),
        "product_master_valid": True,
        "listing_locales": sorted(locale.upper() for locale in listings),
        "workbook_generated": workbook_path.exists(),
        "operations_review_required": True,
        "failures": failures,
        "warnings": warnings,
    }
    checks["status"] = "READY_FOR_OPERATIONS_REVIEW" if not failures else "NOT_READY"
    return checks


def _valid_ean13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(value[:12]))
    return (10 - total % 10) % 10 == int(value[-1])
