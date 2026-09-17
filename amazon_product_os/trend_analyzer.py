from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Any

from .io_utils import clamp
from .models import Candidate
from .trend_db import TrendDatabase


def analyze_trends(
    database: TrendDatabase,
    source_url: str,
    *,
    low_review_threshold: int = 100,
    limit: int = 10,
    window_days: int = 30,
) -> list[Candidate]:
    rows = database.observations(source_url)
    if rows and window_days > 0:
        latest = max(date.fromisoformat(str(row["snapshot_date"])) for row in rows)
        cutoff = latest - timedelta(days=window_days - 1)
        rows = [row for row in rows if date.fromisoformat(str(row["snapshot_date"])) >= cutoff]
    dates = sorted({row["snapshot_date"] for row in rows})
    if not dates:
        return []
    latest_date = dates[-1]
    previous_date = dates[-2] if len(dates) > 1 else None
    latest = [row for row in rows if row["snapshot_date"] == latest_date]
    previous = [row for row in rows if row["snapshot_date"] == previous_date] if previous_date else []

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    history_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    previous_asins = {row["asin"] for row in previous}
    previous_rank = {row["asin"]: row["rank"] for row in previous}
    for row in latest:
        by_type[row["product_type"]].append(row)
    for row in rows:
        history_by_type[row["product_type"]].append(row)

    candidates: list[Candidate] = []
    for product_type, current in by_type.items():
        history = history_by_type[product_type]
        current_asins = {row["asin"] for row in current}
        new_asins = current_asins - previous_asins if previous_date else set()
        top30_count = sum(1 for row in current if row["rank"] <= 30)
        low_review_count = sum(1 for row in current if row["review_count"] <= low_review_threshold)
        active_dates = sorted({row["snapshot_date"] for row in history})

        improvements = [
            previous_rank[row["asin"]] - row["rank"]
            for row in current
            if row["asin"] in previous_rank
        ]
        average_rank_improvement = mean(improvements) if improvements else 0.0
        count_series = [
            sum(1 for row in history if row["snapshot_date"] == snapshot_date)
            for snapshot_date in dates
        ]

        count_score = min(20.0, len(current) * 3.0)
        new_score = 25.0 * len(new_asins) / max(1, len(current))
        top_score = 15.0 * top30_count / max(1, len(current))
        low_review_score = 15.0 * low_review_count / max(1, len(current))
        persistence_score = min(10.0, len(active_dates) * 2.0)
        rank_score = clamp(average_rank_improvement, 0.0, 15.0)
        score = round(clamp(count_score + new_score + top_score + low_review_score + persistence_score + rank_score), 1)

        prices = sorted(float(row["price"]) for row in current if float(row["price"]) > 0)
        price_band = {}
        if prices:
            price_band = {"min": prices[0], "median": prices[len(prices) // 2], "max": prices[-1]}
        candidates.append(
            Candidate(
                product_type=product_type,
                source="New Releases",
                marketplace=str(current[0]["marketplace"]),
                source_ref=source_url,
                observed_at=latest_date,
                score=score,
                evidence={
                    "current_count": len(current),
                    "new_count": len(new_asins),
                    "top30_count": top30_count,
                    "low_review_count": low_review_count,
                    "persistence_days": len(active_dates),
                    "average_rank_improvement": round(average_rank_improvement, 1),
                    "count_series": count_series,
                    "snapshot_dates": dates,
                    "history_sufficient": len(dates) >= 2,
                },
                representative_asins=[row["asin"] for row in sorted(current, key=lambda item: item["rank"])[:5]],
                representative_titles=[row["title"] for row in sorted(current, key=lambda item: item["rank"])[:3]],
                price_band=price_band,
            )
        )
    return sorted(candidates, key=lambda candidate: (candidate.score or 0, candidate.evidence["current_count"]), reverse=True)[:limit]
