"""Build traceable market evidence from structured Amazon/SellerSprite snapshots."""
from __future__ import annotations

import statistics


class MarketEvidenceError(ValueError):
    pass


def _unique_groups(hits):
    groups = {}
    for hit in hits:
        if not isinstance(hit, dict):
            raise MarketEvidenceError("search_hits must contain objects")
        if hit.get("relevant") is False:
            continue
        key = hit.get("parent_asin") or hit.get("asin")
        if not key:
            continue
        groups.setdefault(str(key).upper(), hit)
    return list(groups.values())


def _price_values(groups):
    values = []
    for hit in groups:
        value = hit.get("landed_price")
        if value is None:
            value = hit.get("price")
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _fulfillment_summary(groups, coverage_complete):
    fba = 0
    known = 0
    unknown = 0
    for hit in groups:
        fulfillment = str(hit.get("fulfillment") or "").upper()
        if fulfillment == "FBA":
            fba += 1
            known += 1
        elif fulfillment in {"FBM", "AMAZON_RETAIL", "AMAZON_DISPATCH_UNKNOWN_ROLE"}:
            known += 1
        else:
            unknown += 1
    if fba:
        status = "observed"
    elif groups and coverage_complete and unknown == 0:
        status = "not_observed_in_sample"
    else:
        status = "unknown"
    return {
        "fba_presence": status,
        "known_fba_group_count": fba,
        "relevant_group_count": len(groups),
        "unknown_group_count": unknown,
        "coverage_complete": bool(coverage_complete),
    }


def build_market_evidence(
    candidate_id,
    marketplace,
    observed_at,
    search_hits=None,
    product_details=None,
    review_annotations=None,
    source_ref=None,
    query=None,
    coverage_complete=False,
):
    market = str(marketplace or "").upper()
    if market not in {"DE", "FR", "IT", "ES"}:
        raise MarketEvidenceError("marketplace must be DE/FR/IT/ES")
    if not observed_at:
        raise MarketEvidenceError("observed_at is required")

    search_hits = list(search_hits or [])
    product_details = list(product_details or [])
    review_annotations = list(review_annotations or [])
    groups = _unique_groups(search_hits)
    prices = _price_values(groups)

    evidence = []

    # Demand stays an estimate unless the caller supplies real first-party orders.
    demand_signals = {
        "query": query,
        "relevant_product_groups_observed": len(groups),
        "search_hit_count_observed": len(search_hits),
        "coverage_complete": bool(coverage_complete),
        "purchase_cues": [
            hit.get("purchase_cue")
            for hit in groups
            if hit.get("purchase_cue") not in (None, "")
        ],
    }
    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "target_market_demand",
            "value": demand_signals,
            "evidence_status": "estimate",
            "source_type": "market_snapshot",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
            "notes": "search/sample demand signal; not actual competitor orders",
        }
    )

    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "comparable_competition",
            "value": {
                "independent_product_groups": len(groups),
                "sponsored_groups_observed": sum(1 for hit in groups if hit.get("sponsored") is True),
                "coverage_complete": bool(coverage_complete),
            },
            "evidence_status": "fact",
            "source_type": "market_snapshot",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
        }
    )

    if prices:
        evidence.append(
            {
                "candidate_id": candidate_id,
                "field": "comparable_price",
                "value": {
                    "min": min(prices),
                    "median": statistics.median(prices),
                    "max": max(prices),
                    "sample_size": len(prices),
                },
                "unit": "EUR",
                "evidence_status": "fact",
                "source_type": "market_snapshot",
                "source_ref": source_ref,
                "source_market": market,
                "observed_at": observed_at,
            }
        )
    else:
        evidence.append(
            {
                "candidate_id": candidate_id,
                "field": "comparable_price",
                "value": None,
                "unit": "EUR",
                "evidence_status": "pending_verification",
                "source_type": "market_snapshot",
                "source_ref": source_ref,
                "source_market": market,
                "observed_at": observed_at,
                "notes": "no numeric comparable landed/effective prices supplied",
            }
        )

    # Product detail rows are evidence about comparable specifications, not self-product facts.
    specs = []
    for row in product_details:
        if not isinstance(row, dict):
            raise MarketEvidenceError("product_details must contain objects")
        specs.append(
            {
                "asin": row.get("asin"),
                "material": row.get("material"),
                "size": row.get("size"),
                "pack_count": row.get("pack_count"),
                "selected_variant": row.get("selected_variant"),
            }
        )
    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "product_specs",
            "value": specs if specs else None,
            "evidence_status": "fact" if specs else "pending_verification",
            "source_type": "market_snapshot",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
            "notes": "comparable product specifications; do not copy into own-product facts",
        }
    )

    pain_points = []
    for row in review_annotations:
        if not isinstance(row, dict):
            raise MarketEvidenceError("review_annotations must contain objects")
        text = row.get("pain_point")
        if text:
            pain_points.append(
                {
                    "pain_point": text,
                    "count": row.get("count"),
                    "review_refs": row.get("review_refs") or [],
                    "analysis_status": row.get("analysis_status") or "human_or_model_annotation",
                }
            )
    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "review_pain_points",
            "value": pain_points if pain_points else None,
            "evidence_status": "fact" if pain_points else "pending_verification",
            "source_type": "review_annotation",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
            "notes": "pain points must be annotated from review evidence; no automatic sentiment guess",
        }
    )

    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "fulfillment_and_delivery",
            "value": _fulfillment_summary(groups, coverage_complete),
            "evidence_status": "fact",
            "source_type": "market_snapshot",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
        }
    )

    cn_count = sum(1 for hit in groups if str(hit.get("seller_location") or "").upper() == "CN")
    cn_unknown = sum(1 for hit in groups if not hit.get("seller_location"))
    cn_status = "fact" if coverage_complete and cn_unknown == 0 else "estimate"
    evidence.append(
        {
            "candidate_id": candidate_id,
            "field": "cn_seller_evidence",
            "value": cn_count,
            "evidence_status": cn_status,
            "source_type": "market_snapshot",
            "source_ref": source_ref,
            "source_market": market,
            "observed_at": observed_at,
            "notes": "count within supplied comparable sample; admission signal only",
        }
    )

    return {
        "candidate_id": candidate_id,
        "marketplace": market,
        "evidence": evidence,
        "sample": {
            "search_hit_count": len(search_hits),
            "independent_product_groups": len(groups),
            "coverage_complete": bool(coverage_complete),
        },
    }
