import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from amazon_product_os.orchestrator import AmazonProductOS
from amazon_product_os.trend_db import TrendDatabase


URL = "https://www.amazon.de/gp/new-releases/example"


def create_database(path: Path, rows: list[tuple[object, ...]]) -> None:
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.executescript(
                """
                CREATE TABLE observations (
                    source_url TEXT NOT NULL,
                    marketplace TEXT NOT NULL,
                    snapshot_date TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    asin TEXT NOT NULL,
                    title TEXT NOT NULL,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    price REAL NOT NULL DEFAULT 0,
                    product_type TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_url, snapshot_date, asin)
                );
                """
            )
            connection.executemany(
                """
                INSERT INTO observations (
                    source_url, marketplace, snapshot_date, rank, asin, title,
                    review_count, price, product_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )


class TrendTests(unittest.TestCase):
    def test_two_snapshots_produce_ranked_type_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trends.db"
            create_database(
                path,
                [
                    (URL, "DE", "2026-08-31", 40, "B000000001", "Glow Gloves", 20, 9.99, "Skeleton Glow Gloves"),
                    (URL, "DE", "2026-08-31", 50, "B000000002", "Bone Gloves", 30, 10.99, "Skeleton Glow Gloves"),
                    (URL, "DE", "2026-09-01", 20, "B000000001", "Glow Gloves", 22, 9.99, "Skeleton Glow Gloves"),
                    (URL, "DE", "2026-09-01", 25, "B000000002", "Bone Gloves", 31, 10.99, "Skeleton Glow Gloves"),
                    (URL, "DE", "2026-09-01", 28, "B000000003", "New Gloves", 5, 11.99, "Skeleton Glow Gloves"),
                ],
            )

            candidates = AmazonProductOS(path).discover_new_release_candidates(URL)

            self.assertEqual(candidates[0].product_type, "Skeleton Glow Gloves")
            self.assertEqual(candidates[0].evidence["new_count"], 1)
            self.assertEqual(candidates[0].evidence["top30_count"], 3)
            self.assertEqual(candidates[0].evidence["count_series"], [2, 3])

    def test_database_is_always_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trends.db"
            create_database(path, [])
            before = path.read_bytes()

            database = TrendDatabase(path)

            self.assertEqual(database.series(), [])
            self.assertFalse(hasattr(database, "ingest"))
            self.assertFalse(hasattr(database, "prune"))
            self.assertEqual(path.read_bytes(), before)

    def test_database_requires_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                TrendDatabase(path)
            self.assertFalse(path.exists())

    def test_analysis_uses_only_latest_30_calendar_days(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trends.db"
            create_database(
                path,
                [
                    (URL, "DE", "2026-07-01", 50, "B000000001", "Old Product", 10, 9.99, "Compact Product"),
                    (URL, "DE", "2026-09-01", 20, "B000000001", "Current Product", 12, 9.99, "Compact Product"),
                ],
            )

            candidate = AmazonProductOS(path).discover_new_release_candidates(URL)[0]

            self.assertEqual(candidate.evidence["snapshot_dates"], ["2026-09-01"])
            self.assertEqual(candidate.evidence["persistence_days"], 1)


if __name__ == "__main__":
    unittest.main()
