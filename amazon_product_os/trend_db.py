from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


DEFAULT_TREND_DATABASE = (
    Path(__file__).resolve().parents[2] / "amazon-new-release-collector" / "data" / "trends.db"
)


class TrendDatabase:
    """Read-only access to the database maintained by the standalone collector."""

    def __init__(self, path: str | Path = DEFAULT_TREND_DATABASE) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"Trend database does not exist: {self.path}")

    def connect(self) -> sqlite3.Connection:
        database_uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def snapshot_dates(self, source_url: str) -> list[str]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT snapshot_date FROM observations WHERE source_url = ? ORDER BY snapshot_date",
                (source_url,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def observations(self, source_url: str) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM observations WHERE source_url = ? ORDER BY snapshot_date, rank",
                (source_url,),
            ).fetchall()
        return [dict(row) for row in rows]

    def series(self, marketplace: str = "") -> list[dict[str, Any]]:
        where = "WHERE marketplace = ?" if marketplace else ""
        parameters: tuple[str, ...] = (marketplace.upper(),) if marketplace else ()
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT source_url, marketplace,
                       MIN(snapshot_date) AS first_date,
                       MAX(snapshot_date) AS latest_date,
                       COUNT(DISTINCT snapshot_date) AS snapshot_days,
                       COUNT(*) AS observations
                FROM observations
                {where}
                GROUP BY source_url, marketplace
                ORDER BY marketplace, source_url
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]
