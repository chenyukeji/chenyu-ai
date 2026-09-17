from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision import evaluate_product
from .io_utils import read_json, write_json
from .listing import export_launch_package
from .models import Candidate
from .sellersprite import analyze_sellersprite
from .trend_analyzer import analyze_trends
from .trend_db import DEFAULT_TREND_DATABASE, TrendDatabase


class AmazonProductOS:
    """Independent command facade; no method automatically triggers another role."""

    def __init__(
        self,
        database_path: str | Path = DEFAULT_TREND_DATABASE,
    ) -> None:
        self.trends = TrendDatabase(database_path)

    def discover_new_release_candidates(self, source_url: str, *, limit: int = 10) -> list[Candidate]:
        return analyze_trends(self.trends, source_url, limit=limit)

    def discover_all_new_release_candidates(
        self,
        *,
        marketplace: str = "",
        limit: int = 10,
    ) -> list[Candidate]:
        candidates: list[Candidate] = []
        for series in self.trends.series(marketplace):
            candidates.extend(analyze_trends(self.trends, str(series["source_url"]), limit=limit))
        return sorted(
            candidates,
            key=lambda candidate: (candidate.score or 0, candidate.evidence.get("current_count", 0)),
            reverse=True,
        )[:limit]

    def discover_historical_candidates(
        self,
        path: str | Path,
        *,
        marketplace: str = "",
        minimum_asins: int = 2,
        max_price: float | None = 30.0,
        max_package_weight_g: float | None = 1000.0,
        max_package_dimensions_cm: tuple[float, float, float] | None = (45.0, 35.0, 25.0),
        require_complete_size: bool = True,
    ) -> list[Candidate]:
        return analyze_sellersprite(
            path,
            marketplace=marketplace,
            minimum_asins=minimum_asins,
            max_price=max_price,
            max_package_weight_g=max_package_weight_g,
            max_package_dimensions_cm=max_package_dimensions_cm,
            require_complete_size=require_complete_size,
        )

    def decide(self, development_case: dict[str, Any]) -> dict[str, Any]:
        return evaluate_product(development_case)

    def launch(
        self,
        product_master: dict[str, Any],
        listings: dict[str, Any],
        output_dir: str | Path,
        development_record: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return export_launch_package(
            product_master,
            listings,
            output_dir,
            development_record=development_record,
            **kwargs,
        )

    @staticmethod
    def save_candidates(candidates: list[Candidate], output: str | Path) -> Path:
        return write_json(output, {"schema_version": "1.0", "candidates": [candidate.to_dict() for candidate in candidates]})

    @staticmethod
    def load_candidate(path: str | Path, index: int = 0) -> Candidate:
        payload = read_json(path)
        if "candidates" in payload:
            return Candidate.from_dict(payload["candidates"][index])
        return Candidate.from_dict(payload)
