from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .compliance import assess_compliance
from .decision import evaluate_product
from .io_utils import read_json, write_json
from .listing import export_launch_package
from .orchestrator import AmazonProductOS
from .profit import calculate_profit
from .sellersprite import (
    DEFAULT_MAX_PACKAGE_DIMENSIONS_CM,
    DEFAULT_MAX_PACKAGE_WEIGHT_G,
    DEFAULT_MAX_PRICE,
    analyze_sellersprite,
)
from .trend_db import DEFAULT_TREND_DATABASE


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _candidate_payload(candidates: list[Any]) -> dict[str, Any]:
    return {"schema_version": "1.0", "candidates": [candidate.to_dict() for candidate in candidates]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amazon-os", description="Amazon Product OS")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_TREND_DATABASE),
        help="Read-only New Releases SQLite database maintained by the standalone collector",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    trend = sub.add_parser("trend", help="Read candidates from the external New Releases database")
    trend_sub = trend.add_subparsers(dest="trend_command", required=True)
    report = trend_sub.add_parser("report", help="Rank candidate product types")
    report.add_argument("--url", help="Analyze one source URL; omit to analyze every stored series")
    report.add_argument("--marketplace", default="", help="Optional marketplace filter when --url is omitted")
    report.add_argument("--limit", type=int, default=10)
    report.add_argument("--output")

    historical = sub.add_parser("historical", help="Analyze a SellerSprite Excel/CSV export")
    historical.add_argument("input")
    historical.add_argument("--marketplace", default="")
    historical.add_argument("--minimum-asins", type=int, default=2)
    historical.add_argument("--max-price", type=float, default=DEFAULT_MAX_PRICE)
    historical.add_argument("--max-package-weight-g", type=float, default=DEFAULT_MAX_PACKAGE_WEIGHT_G)
    historical.add_argument("--max-longest-side-cm", type=float, default=DEFAULT_MAX_PACKAGE_DIMENSIONS_CM[0])
    historical.add_argument("--max-middle-side-cm", type=float, default=DEFAULT_MAX_PACKAGE_DIMENSIONS_CM[1])
    historical.add_argument("--max-shortest-side-cm", type=float, default=DEFAULT_MAX_PACKAGE_DIMENSIONS_CM[2])
    historical.add_argument(
        "--allow-missing-size",
        action="store_true",
        help="Keep rows with missing dimensions or weight; strict compact screening is the default",
    )
    historical.add_argument("--output", required=True)

    profit = sub.add_parser("profit", help="Calculate normal and conservative unit economics")
    profit.add_argument("input")
    profit.add_argument("--output")

    compliance = sub.add_parser("compliance", help="Screen product compliance flags")
    compliance.add_argument("input")
    compliance.add_argument("--marketplace", default="EU")
    compliance.add_argument("--output")

    decision = sub.add_parser("decision", help="Create a Product Decision Card")
    decision.add_argument("input")
    decision.add_argument("--output", required=True)

    launch = sub.add_parser("launch", help="Generate a draft Amazon Upload Package for operations review")
    launch.add_argument("--product-master", required=True)
    launch.add_argument("--decision", help="Optional development record retained for traceability")
    launch.add_argument("--listings", required=True)
    launch.add_argument("--output-dir", required=True)
    launch.add_argument("--node")
    launch.add_argument("--workbook-builder")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "trend":
            os = AmazonProductOS(args.db)
            return _trend(args, os)
        if args.command == "historical":
            candidates = analyze_sellersprite(
                args.input,
                marketplace=args.marketplace,
                minimum_asins=args.minimum_asins,
                max_price=args.max_price,
                max_package_weight_g=args.max_package_weight_g,
                max_package_dimensions_cm=(
                    args.max_longest_side_cm,
                    args.max_middle_side_cm,
                    args.max_shortest_side_cm,
                ),
                require_complete_size=not args.allow_missing_size,
            )
            payload = _candidate_payload(candidates)
            write_json(args.output, payload)
            _print(payload)
            return 0
        if args.command == "profit":
            result = calculate_profit(read_json(args.input))
            if args.output:
                write_json(args.output, result)
            _print(result)
            return 0
        if args.command == "compliance":
            result = assess_compliance(read_json(args.input), args.marketplace)
            if args.output:
                write_json(args.output, result)
            _print(result)
            return 0
        if args.command == "decision":
            result = evaluate_product(read_json(args.input))
            write_json(args.output, result)
            _print(result)
            return 0
        if args.command == "launch":
            result = export_launch_package(
                read_json(args.product_master),
                read_json(args.listings),
                args.output_dir,
                development_record=read_json(args.decision) if args.decision else None,
                node_executable=args.node,
                workbook_builder=args.workbook_builder,
            )
            _print(result)
            return 0 if result["status"] == "READY_FOR_OPERATIONS_REVIEW" else 2
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


def _trend(args: argparse.Namespace, os: AmazonProductOS) -> int:
    if args.trend_command == "report":
        candidates = (
            os.discover_new_release_candidates(args.url, limit=args.limit)
            if args.url
            else os.discover_all_new_release_candidates(marketplace=args.marketplace, limit=args.limit)
        )
        payload = _candidate_payload(candidates)
        if args.output:
            write_json(args.output, payload)
        _print(payload)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
