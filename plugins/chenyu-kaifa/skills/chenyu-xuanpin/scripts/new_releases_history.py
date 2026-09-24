"""Read-only time-series analysis for a collector-owned new_releases.db."""
from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


class HistoryDatabaseError(ValueError):
    pass


REQUIRED_COLUMNS = {
    "observations": {
        "source_url",
        "marketplace",
        "category",
        "snapshot_date",
        "rank",
        "asin",
        "title",
        "image_url",
    }
}

OPTIONAL_COLUMNS = {
    "observations": {
        "review_count",
        "price",
        "price_text",
        "rating",
        "product_url",
    },
    "product_seen": {
        "title",
        "product_url",
        "image_url",
    },
}

PRODUCT_SEEN_REQUIRED_COLUMNS = {"marketplace", "asin", "first_seen", "last_seen"}


def _positive_int(value: Any, default: int, name: str, maximum: int = 1000) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise HistoryDatabaseError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HistoryDatabaseError(f"{name} must be an integer") from exc
    if parsed < 1 or parsed > maximum:
        raise HistoryDatabaseError(f"{name} must be between 1 and {maximum}")
    return parsed


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _ratio(value: Any, default: float, name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoryDatabaseError(f"{name} must be a number") from exc
    if not 0 <= parsed <= 1:
        raise HistoryDatabaseError(f"{name} must be between 0 and 1")
    return parsed


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "der",
    "die",
    "das",
    "for",
    "für",
    "in",
    "mit",
    "of",
    "set",
    "the",
    "und",
    "with",
}


def _title_tokens(value: Any) -> set[str]:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return {
        token
        for token in re.findall(r"[\w]+", text, flags=re.UNICODE)
        if len(token) > 1 and token not in TITLE_STOPWORDS and not token.isdigit()
    }


def _title_similarity(left: Any, right: Any) -> float:
    left_text = unicodedata.normalize("NFKC", str(left or "")).casefold().strip()
    right_text = unicodedata.normalize("NFKC", str(right or "")).casefold().strip()
    if not left_text or not right_text:
        return 0.0
    left_tokens = _title_tokens(left_text)
    right_tokens = _title_tokens(right_text)
    union = left_tokens | right_tokens
    shared = left_tokens & right_tokens
    jaccard = len(shared) / len(union) if union else 0.0
    overlap = len(shared) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    sequence = SequenceMatcher(None, left_text, right_text).ratio()
    return round(max(jaccard, overlap * 0.75, sequence * 0.85), 4)


def _placeholder_image_url(value: Any) -> bool:
    text = str(value or "").casefold()
    return not text or any(token in text for token in ("no_image", "no-image", "placeholder"))


def _image_fingerprint(url: str, cache: dict[str, int | None]) -> int | None:
    if url in cache:
        return cache[url]
    if _placeholder_image_url(url):
        cache[url] = None
        return None
    try:
        from PIL import Image, ImageOps

        request: Any = url
        if url.startswith(("http://", "https://")):
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=5) as response:
            payload = response.read(5 * 1024 * 1024 + 1)
        if len(payload) > 5 * 1024 * 1024:
            raise ValueError("image exceeds 5 MiB")
        with Image.open(BytesIO(payload)) as opened:
            image = ImageOps.exif_transpose(opened).convert("L").resize((9, 8))
            pixels = list(image.getdata())
        fingerprint = 0
        for row in range(8):
            for column in range(8):
                fingerprint = (fingerprint << 1) | int(
                    pixels[row * 9 + column] > pixels[row * 9 + column + 1]
                )
        cache[url] = fingerprint
    except Exception:
        cache[url] = None
    return cache[url]


def _image_similarity(
    left_url: Any,
    right_url: Any,
    cache: dict[str, int | None],
) -> float | None:
    left = str(left_url or "").strip()
    right = str(right_url or "").strip()
    if _placeholder_image_url(left) or _placeholder_image_url(right):
        return None
    if left == right:
        return 1.0
    left_hash = _image_fingerprint(left, cache)
    right_hash = _image_fingerprint(right, cache)
    if left_hash is None or right_hash is None:
        return None
    return round(1 - ((left_hash ^ right_hash).bit_count() / 64), 4)


def resolve_database_path(payload: dict | None = None) -> Path:
    payload = dict(payload or {})
    history = dict(payload.get("history") or payload.get("new_releases_db") or {})
    discovery = dict(payload.get("discovery") or {})
    explicit = (
        payload.get("db_path")
        or history.get("db_path")
        or history.get("path")
        or discovery.get("history_db_path")
        or discovery.get("new_releases_db_path")
        or os.environ.get("CHENYU_NEW_RELEASES_DB")
    )
    if explicit:
        path = Path(str(explicit)).expanduser().resolve()
        if not path.is_file():
            raise HistoryDatabaseError(f"new_releases.db not found: {path}")
        return path

    roots: list[Path] = []
    for base in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for root in (base, *base.parents):
            if root not in roots:
                roots.append(root)
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            (
                root / "data" / "new_releases.db",
                root / "amazon-new-release-collector" / "data" / "new_releases.db",
                root.parent / "amazon-new-release-collector" / "data" / "new_releases.db",
            )
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise HistoryDatabaseError(
        "new_releases.db not found; pass db_path or set CHENYU_NEW_RELEASES_DB"
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _validate_schema(connection: sqlite3.Connection) -> set[str]:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing_tables = sorted(set(REQUIRED_COLUMNS) - tables)
    if missing_tables:
        raise HistoryDatabaseError("database missing tables: " + ", ".join(missing_tables))
    for table, expected in REQUIRED_COLUMNS.items():
        actual = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        missing = sorted(expected - actual)
        if missing:
            raise HistoryDatabaseError(f"database table {table} missing columns: {', '.join(missing)}")
    for table, expected in OPTIONAL_COLUMNS.items():
        if table not in tables:
            continue
        actual = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if table == "product_seen":
            missing = sorted(PRODUCT_SEEN_REQUIRED_COLUMNS - actual)
            if missing:
                raise HistoryDatabaseError(f"database table {table} missing columns: {', '.join(missing)}")
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(observations)")}


def _markets(connection: sqlite3.Connection, requested: Any) -> list[str]:
    if requested:
        raw = requested if isinstance(requested, list) else [requested]
        markets = list(dict.fromkeys(str(value).strip().upper() for value in raw if str(value).strip()))
    else:
        markets = [
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT marketplace FROM observations ORDER BY marketplace"
            )
        ]
    if not markets:
        raise HistoryDatabaseError("database has no marketplaces")
    return markets


def _latest_snapshot(
    connection: sqlite3.Connection,
    marketplace: str,
    category: str | None,
    on_or_before: str | None = None,
) -> str | None:
    sql = "SELECT MAX(snapshot_date) FROM observations WHERE marketplace = ?"
    params: list[Any] = [marketplace]
    if category:
        sql += " AND category = ?"
        params.append(category)
    if on_or_before:
        sql += " AND snapshot_date <= ?"
        params.append(on_or_before)
    value = connection.execute(sql, params).fetchone()[0]
    return str(value) if value else None


def _window_rows(
    connection: sqlite3.Connection,
    observation_columns: set[str],
    marketplace: str,
    start_date: str,
    end_date: str,
    category: str | None,
) -> list[dict[str, Any]]:
    optional = {
        name: name if name in observation_columns else f"'' AS {name}"
        for name in ("price_text", "product_url")
    }
    optional.update(
        {
            name: name if name in observation_columns else f"0 AS {name}"
            for name in ("review_count", "price", "rating")
        }
    )
    sql = """
        SELECT source_url, marketplace, category, snapshot_date, rank, asin, title,
               {review_count}, {price}, {price_text}, {rating},
               {product_url}, image_url
        FROM observations
        WHERE marketplace = ? AND snapshot_date >= ? AND snapshot_date <= ?
    """.format(**optional)
    params: list[Any] = [marketplace, start_date, end_date]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY snapshot_date, rank, asin"
    rows = connection.execute(sql, params).fetchall()

    best_by_day: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        key = (str(row["snapshot_date"]), str(row["asin"]).upper())
        current = best_by_day.get(key)
        if current is None or int(row["rank"]) < int(current["rank"]):
            row["asin"] = key[1]
            best_by_day[key] = row
    return sorted(best_by_day.values(), key=lambda row: (row["snapshot_date"], row["rank"], row["asin"]))


def _identity_map(
    connection: sqlite3.Connection, marketplace: str, observation_columns: set[str]
) -> tuple[dict[str, dict[str, Any]], str]:
    has_identity_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='product_seen'"
    ).fetchone()
    if has_identity_table:
        product_seen_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(product_seen)")
        }
        optional = {
            name: name if name in product_seen_columns else f"'' AS {name}"
            for name in ("title", "product_url", "image_url")
        }
        rows = connection.execute(
            """
            SELECT asin, first_seen, last_seen, {title}, {product_url}, {image_url}
            FROM product_seen WHERE marketplace = ?
            """.format(**optional),
            (marketplace,),
        ).fetchall()
        return ({str(row["asin"]).upper(): dict(row) for row in rows}, "product_seen")
    product_url = "MAX(product_url)" if "product_url" in observation_columns else "''"
    image_url = "MAX(image_url)" if "image_url" in observation_columns else "''"
    rows = connection.execute(
        f"""
        SELECT asin, MIN(snapshot_date) AS first_seen, MAX(snapshot_date) AS last_seen,
               MAX(title) AS title, {product_url} AS product_url, {image_url} AS image_url
        FROM observations WHERE marketplace = ? GROUP BY asin
        """,
        (marketplace,),
    ).fetchall()
    return (
        {str(row["asin"]).upper(): dict(row) for row in rows},
        "earliest_retained_observation",
    )


def _product(row: dict[str, Any], **metrics: Any) -> dict[str, Any]:
    price = _number(row.get("price"))
    rating = _number(row.get("rating"))
    result = {
        "asin": str(row.get("asin") or "").upper(),
        "rank": int(row["rank"]),
        "title": str(row.get("title") or ""),
        "category": str(row.get("category") or ""),
        "product_url": str(row.get("product_url") or ""),
        "image_url": str(row.get("image_url") or ""),
        "price": price,
        "price_text": str(row.get("price_text") or ""),
        "review_count": int(row.get("review_count") or 0),
        "rating": rating,
        "snapshot_date": str(row.get("snapshot_date") or ""),
        "source_url": str(row.get("source_url") or ""),
    }
    result.update(metrics)
    return result


def _similar_product_groups(
    rows: list[dict[str, Any]],
    *,
    identity: dict[str, dict[str, Any]],
    product_metrics: dict[str, dict[str, Any]],
    analysis_day: date,
    days: int,
    recent_days: int,
    min_group_asins: int,
    title_similarity_min: float,
    image_similarity_min: float,
    combined_similarity_min: float,
    max_similarity_products: int,
    limit: int,
) -> dict[str, Any]:
    recent_start = analysis_day - timedelta(days=min(recent_days, days) - 1)
    history_by_asin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        history_by_asin[str(row["asin"])].append(row)

    candidates = [
        max(history, key=lambda item: (str(item["snapshot_date"]), -int(item["rank"])))
        for history in history_by_asin.values()
    ]
    candidates.sort(
        key=lambda row: (
            str(row["snapshot_date"]) < recent_start.isoformat(),
            int(row["rank"]),
            str(row["asin"]),
        )
    )
    candidates = candidates[:max_similarity_products]

    image_cache: dict[str, int | None] = {}
    pair_cache: dict[tuple[str, str], dict[str, Any]] = {}
    counters = {
        "compared_pairs": 0,
        "title_screened_pairs": 0,
        "image_comparable_pairs": 0,
        "image_unavailable_pairs": 0,
    }

    def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        left_asin = str(left["asin"])
        right_asin = str(right["asin"])
        key = tuple(sorted((left_asin, right_asin)))
        if key in pair_cache:
            return pair_cache[key]
        counters["compared_pairs"] += 1
        title_score = _title_similarity(left.get("title"), right.get("title"))
        evidence = {
            "asin_a": key[0],
            "asin_b": key[1],
            "title_similarity": title_score,
            "image_similarity": None,
            "combined_similarity": None,
            "is_similar": False,
        }
        if str(left.get("category") or "").casefold() != str(right.get("category") or "").casefold():
            pair_cache[key] = evidence
            return evidence
        if title_score < title_similarity_min:
            pair_cache[key] = evidence
            return evidence
        counters["title_screened_pairs"] += 1
        image_score = _image_similarity(left.get("image_url"), right.get("image_url"), image_cache)
        evidence["image_similarity"] = image_score
        if image_score is None:
            counters["image_unavailable_pairs"] += 1
            pair_cache[key] = evidence
            return evidence
        counters["image_comparable_pairs"] += 1
        combined = round(title_score * 0.6 + image_score * 0.4, 4)
        evidence["combined_similarity"] = combined
        evidence["is_similar"] = (
            image_score >= image_similarity_min and combined >= combined_similarity_min
        )
        pair_cache[key] = evidence
        return evidence

    groups: list[list[dict[str, Any]]] = []
    for candidate in candidates:
        for group in groups:
            if all(compare(candidate, member)["is_similar"] for member in group):
                group.append(candidate)
                break
        else:
            groups.append([candidate])

    results = []
    for group in groups:
        member_asins = {str(row["asin"]) for row in group}
        recent_asins = {
            asin
            for asin in member_asins
            if any(
                date.fromisoformat(str(row["snapshot_date"])) >= recent_start
                for row in history_by_asin[asin]
            )
        }
        if len(recent_asins) < min_group_asins:
            continue
        prior_asins = {
            asin
            for asin in member_asins
            if any(
                date.fromisoformat(str(row["snapshot_date"])) < recent_start
                for row in history_by_asin[asin]
            )
        }
        new_recent_asins = {
            asin
            for asin in recent_asins
            if str((identity.get(asin) or {}).get("first_seen") or "") >= recent_start.isoformat()
        }
        pair_evidence = []
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                evidence = compare(left, right)
                if evidence["is_similar"]:
                    pair_evidence.append(evidence)
        if len(member_asins) < min_group_asins or not pair_evidence:
            continue
        ranked_members = sorted(
            (product_metrics[asin] for asin in member_asins),
            key=lambda item: (item.get("current_rank") is None, item.get("current_rank") or item["rank"]),
        )
        similarities = [float(item["combined_similarity"]) for item in pair_evidence]
        results.append(
            {
                "member_count": len(member_asins),
                "recent_member_count": len(recent_asins),
                "prior_member_count": len(prior_asins),
                "recent_new_member_count": len(new_recent_asins),
                "member_asins": [item["asin"] for item in ranked_members],
                "members": [
                    {
                        "asin": item["asin"],
                        "title": item["title"],
                        "image_url": item["image_url"],
                        "current_rank": item.get("current_rank"),
                        "best_rank": item["best_rank"],
                        "first_seen": item["first_seen"],
                    }
                    for item in ranked_members
                ],
                "minimum_pair_similarity": round(min(similarities), 4),
                "average_pair_similarity": round(sum(similarities) / len(similarities), 4),
                "pair_evidence": pair_evidence,
            }
        )
    results.sort(
        key=lambda item: (
            item["recent_new_member_count"],
            item["recent_member_count"],
            item["member_count"],
            item["average_pair_similarity"],
        ),
        reverse=True,
    )
    if results:
        status = "AVAILABLE"
    elif counters["image_comparable_pairs"] == 0:
        status = "INSUFFICIENT_IMAGE_EVIDENCE"
    else:
        status = "NO_SIMILAR_PRODUCT_GROUPS"
    return {
        "status": status,
        "definition": (
            f"不命名产品类型；仅在同站点同类目内同时比较标题与主图，"
            f"最近{min(recent_days, days)}个自然日至少{min_group_asins}个相似ASIN才形成一组"
        ),
        "criteria": {
            "title_similarity_min": title_similarity_min,
            "image_similarity_min": image_similarity_min,
            "combined_similarity_min": combined_similarity_min,
            "combined_weights": {"title": 0.6, "image": 0.4},
            "group_linkage": "all_pairs_must_match",
        },
        "candidate_products": len(candidates),
        **counters,
        "count": len(results),
        "groups": results[:limit],
    }


def _market_report(
    connection: sqlite3.Connection,
    *,
    observation_columns: set[str],
    marketplace: str,
    category: str | None,
    requested_as_of: str | None,
    days: int,
    recent_days: int,
    min_repeat_days: int,
    min_group_asins: int,
    title_similarity_min: float,
    image_similarity_min: float,
    combined_similarity_min: float,
    max_similarity_products: int,
    min_rank_improvement: int,
    min_rising_consistency: float,
    limit: int,
) -> dict[str, Any]:
    latest_any = _latest_snapshot(connection, marketplace, category)
    if not latest_any:
        return {
            "marketplace": marketplace,
            "category": category,
            "status": "NO_DATA",
            "warnings": ["指定站点和类目没有快照数据"],
        }

    analysis_date = requested_as_of or latest_any
    latest_on_or_before = _latest_snapshot(connection, marketplace, category, analysis_date)
    analysis_day = date.fromisoformat(analysis_date)
    start_day = analysis_day - timedelta(days=days - 1)
    yesterday = (analysis_day - timedelta(days=1)).isoformat()
    rows = _window_rows(
        connection,
        observation_columns,
        marketplace,
        start_day.isoformat(),
        analysis_date,
        category,
    )
    identity, identity_source = _identity_map(connection, marketplace, observation_columns)
    available_dates = sorted({str(row["snapshot_date"]) for row in rows})
    previous_available = next(
        (value for value in reversed(available_dates) if value < analysis_date),
        None,
    )

    by_asin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_asin[str(row["asin"])].append(row)
        by_date[str(row["snapshot_date"])].append(row)

    products: list[dict[str, Any]] = []
    first_today: list[dict[str, Any]] = []
    first_window: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    rising: list[dict[str, Any]] = []
    product_metrics: dict[str, dict[str, Any]] = {}
    reverse_dates = list(reversed(available_dates))

    for asin, history in by_asin.items():
        history.sort(key=lambda row: str(row["snapshot_date"]))
        ranks = [int(row["rank"]) for row in history]
        latest_row = history[-1]
        first_seen = str((identity.get(asin) or {}).get("first_seen") or history[0]["snapshot_date"])
        last_seen = str(history[-1]["snapshot_date"])
        dates_present = {str(row["snapshot_date"]) for row in history}
        consecutive = 0
        if analysis_date in dates_present:
            for snapshot_date in reverse_dates:
                if snapshot_date not in dates_present:
                    break
                consecutive += 1
        steps = max(0, len(ranks) - 1)
        improving_steps = sum(ranks[index] < ranks[index - 1] for index in range(1, len(ranks)))
        worsening_steps = sum(ranks[index] > ranks[index - 1] for index in range(1, len(ranks)))
        period_change = ranks[0] - ranks[-1] if steps else 0
        consistency = round(improving_steps / steps, 4) if steps else 0.0
        velocity = round(period_change / steps, 2) if steps else 0.0
        metrics = {
            "first_seen": first_seen,
            "last_seen": last_seen,
            "days_present": len(history),
            "snapshots_available": len(available_dates),
            "repeat_rate": round(len(history) / max(1, len(available_dates)), 4),
            "consecutive_snapshots": consecutive,
            "best_rank": min(ranks),
            "average_rank": round(sum(ranks) / len(ranks), 2),
            "current_rank": ranks[-1] if last_seen == analysis_date else None,
            "period_rank_change": period_change,
            "rank_velocity": velocity,
            "rank_consistency": consistency,
            "improving_steps": improving_steps,
            "worsening_steps": worsening_steps,
            "rank_history": [
                {"date": str(row["snapshot_date"]), "rank": int(row["rank"])}
                for row in history
            ],
        }
        item = _product(latest_row, **metrics)
        product_metrics[asin] = item
        products.append(item)
        if start_day.isoformat() <= first_seen <= analysis_date:
            first_window.append(item)
        if first_seen == analysis_date:
            first_today.append(item)
        if consecutive >= min_repeat_days:
            repeats.append(item)
        if (
            last_seen == analysis_date
            and steps >= 1
            and period_change >= min_rank_improvement
            and consistency >= min_rising_consistency
        ):
            rising.append(item)

    products.sort(
        key=lambda item: (
            item["last_seen"] != analysis_date,
            -(item["days_present"]),
            item["rank"],
            item["asin"],
        )
    )
    first_today.sort(key=lambda item: (item["rank"], item["asin"]))
    first_window.sort(key=lambda item: (item["first_seen"], -item["rank"]), reverse=True)
    repeats.sort(
        key=lambda item: (
            item["current_rank"] is not None,
            item["consecutive_snapshots"],
            item["days_present"],
            -(item["current_rank"] or 9999),
        ),
        reverse=True,
    )
    rising.sort(
        key=lambda item: (
            item["period_rank_change"],
            item["rank_consistency"],
            item["rank_velocity"],
            -(item["current_rank"] or 9999),
        ),
        reverse=True,
    )

    similar_groups = _similar_product_groups(
        rows,
        identity=identity,
        product_metrics=product_metrics,
        analysis_day=analysis_day,
        days=days,
        recent_days=recent_days,
        min_group_asins=min_group_asins,
        title_similarity_min=title_similarity_min,
        image_similarity_min=image_similarity_min,
        combined_similarity_min=combined_similarity_min,
        max_similarity_products=max_similarity_products,
        limit=limit,
    )

    def snapshot_bucket(snapshot_date: str | None) -> dict[str, Any]:
        if not snapshot_date:
            return {"snapshot_date": None, "count": 0, "products": []}
        selected = sorted(by_date.get(snapshot_date, []), key=lambda row: (row["rank"], row["asin"]))
        return {
            "snapshot_date": snapshot_date,
            "count": len(selected),
            "products": [_product(row) for row in selected[:limit]],
        }

    system_today = date.today()
    warnings = []
    if analysis_date != system_today.isoformat():
        lag = (system_today - date.fromisoformat(latest_any)).days
        warnings.append(f"数据库最新快照为{latest_any}，距离系统日期{system_today.isoformat()}为{lag}天")
    if analysis_date not in available_dates:
        warnings.append(f"分析日{analysis_date}没有快照，today列表为空")
    if yesterday not in available_dates:
        warnings.append(f"自然日前一日{yesterday}没有快照，yesterday列表为空")
    if len(available_dates) < days:
        warnings.append(f"过去{days}个自然日只有{len(available_dates)}个有效快照日")
    if identity_source != "product_seen":
        warnings.append("数据库没有product_seen表，首次出现按当前保留快照中的最早日期计算")
    if similar_groups["status"] == "INSUFFICIENT_IMAGE_EVIDENCE":
        warnings.append("没有可同时比较标题和主图的商品对，相似商品组无结果")
    elif similar_groups["status"] == "NO_SIMILAR_PRODUCT_GROUPS":
        warnings.append("没有商品对同时达到标题、主图和综合相似度阈值")

    return {
        "marketplace": marketplace,
        "category": category,
        "status": "COMPLETE",
        "date_basis": {
            "analysis_date": analysis_date,
            "analysis_date_source": "explicit" if requested_as_of else "latest_available",
            "system_date": system_today.isoformat(),
            "latest_snapshot_date": latest_any,
            "latest_snapshot_on_or_before_analysis_date": latest_on_or_before,
            "calendar_yesterday": yesterday,
            "previous_available_snapshot": previous_available,
            "window_start": start_day.isoformat(),
            "window_days": days,
            "available_snapshot_dates": available_dates,
            "first_seen_basis": identity_source,
        },
        "today": snapshot_bucket(analysis_date),
        "yesterday": snapshot_bucket(yesterday),
        "previous_available": snapshot_bucket(previous_available),
        "past_days": {
            "from": start_day.isoformat(),
            "to": analysis_date,
            "snapshot_days": len(available_dates),
            "unique_products": len(products),
            "products": products[:limit],
        },
        "first_appearances": {
            "today_count": len(first_today),
            "today": first_today[:limit],
            "window_count": len(first_window),
            "window": first_window[:limit],
        },
        "continuous_products": {
            "definition": "按数据库实际存在的快照日计算，不把漏采日自动当作中断",
            "minimum_consecutive_snapshots": min_repeat_days,
            "count": len(repeats),
            "products": repeats[:limit],
        },
        "similar_product_groups": similar_groups,
        "rising_products": {
            "definition": f"分析日仍在榜、窗口净提升至少{min_rank_improvement}名且上升步占比至少{min_rising_consistency:.0%}",
            "count": len(rising),
            "products": rising[:limit],
        },
        "warnings": warnings,
    }


def analyze_new_releases_database(payload: dict | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    history = dict(payload.get("history") or payload.get("new_releases_db") or {})
    path = resolve_database_path(payload)
    days = _positive_int(payload.get("days", history.get("days")), 10, "days", 90)
    recent_days = _positive_int(history.get("recent_days"), 3, "recent_days", days)
    min_repeat_days = _positive_int(history.get("min_repeat_days"), 3, "min_repeat_days", days)
    min_group_asins = _positive_int(history.get("min_group_asins"), 2, "min_group_asins", 100)
    max_similarity_products = _positive_int(
        history.get("max_similarity_products"), 100, "max_similarity_products", 500
    )
    title_similarity_min = _ratio(
        history.get("title_similarity_min"), 0.35, "title_similarity_min"
    )
    image_similarity_min = _ratio(
        history.get("image_similarity_min"), 0.72, "image_similarity_min"
    )
    combined_similarity_min = _ratio(
        history.get("combined_similarity_min"), 0.68, "combined_similarity_min"
    )
    min_rank_improvement = _positive_int(
        history.get("min_rank_improvement"), 5, "min_rank_improvement", 1000
    )
    limit = _positive_int(payload.get("limit", history.get("limit")), 100, "limit", 1000)
    min_rising_consistency = float(history.get("min_rising_consistency", 0.6))
    if not 0 <= min_rising_consistency <= 1:
        raise HistoryDatabaseError("min_rising_consistency must be between 0 and 1")
    category = payload.get("category") or history.get("category")
    requested_as_of = payload.get("as_of_date") or history.get("as_of_date")
    if requested_as_of:
        try:
            requested_as_of = date.fromisoformat(str(requested_as_of)[:10]).isoformat()
        except ValueError as exc:
            raise HistoryDatabaseError("as_of_date must use YYYY-MM-DD") from exc

    with closing(_connect_readonly(path)) as connection:
        observation_columns = _validate_schema(connection)
        marketplaces = _markets(
            connection,
            payload.get("marketplaces") or payload.get("marketplace") or history.get("marketplaces"),
        )
        reports = {
            market: _market_report(
                connection,
                observation_columns=observation_columns,
                marketplace=market,
                category=str(category) if category else None,
                requested_as_of=requested_as_of,
                days=days,
                recent_days=recent_days,
                min_repeat_days=min_repeat_days,
                min_group_asins=min_group_asins,
                title_similarity_min=title_similarity_min,
                image_similarity_min=image_similarity_min,
                combined_similarity_min=combined_similarity_min,
                max_similarity_products=max_similarity_products,
                min_rank_improvement=min_rank_improvement,
                min_rising_consistency=min_rising_consistency,
                limit=limit,
            )
            for market in marketplaces
        }
        observation_count = int(connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0])

    warnings = [warning for report in reports.values() for warning in report.get("warnings", [])]
    return {
        "ok": True,
        "action": "analyze_new_releases_db",
        "database": {
            "path": str(path),
            "mode": "read_only",
            "required_tables": sorted(REQUIRED_COLUMNS),
            "optional_tables": ["product_seen"],
            "optional_observation_columns": sorted(OPTIONAL_COLUMNS["observations"]),
            "observation_count": observation_count,
            "observation_columns": sorted(observation_columns),
        },
        "parameters": {
            "days": days,
            "category": category,
            "as_of_date": requested_as_of,
            "recent_days": recent_days,
            "min_repeat_days": min_repeat_days,
            "min_group_asins": min_group_asins,
            "max_similarity_products": max_similarity_products,
            "title_similarity_min": title_similarity_min,
            "image_similarity_min": image_similarity_min,
            "combined_similarity_min": combined_similarity_min,
            "min_rank_improvement": min_rank_improvement,
            "min_rising_consistency": min_rising_consistency,
            "limit": limit,
        },
        "marketplaces": reports,
        "warnings": list(dict.fromkeys(warnings)),
    }


def discovery_records_from_history(report: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
    """Turn NEW / REPEAT / RISING history signals into current discovery seed records."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for marketplace, market_report in (report.get("marketplaces") or {}).items():
        if market_report.get("status") != "COMPLETE":
            continue
        signal_groups = (
            ("NEW", (market_report.get("first_appearances") or {}).get("window") or []),
            ("REPEAT", (market_report.get("continuous_products") or {}).get("products") or []),
            ("RISING", (market_report.get("rising_products") or {}).get("products") or []),
        )
        for signal, products in signal_groups:
            for product in products:
                asin = str(product.get("asin") or "").upper()
                if not asin:
                    continue
                key = (str(marketplace).upper(), asin)
                row = merged.setdefault(
                    key,
                    {
                        "marketplace": key[0],
                        "asin": asin,
                        "history_signals": [],
                        "source_strategy": "E",
                        "ranking_type": "new_releases_history",
                    },
                )
                if signal not in row["history_signals"]:
                    row["history_signals"].append(signal)
                mappings = {
                    "product_name": product.get("title"),
                    "new_release_rank": product.get("current_rank") or product.get("rank"),
                    "category_name": product.get("category"),
                    "image_url": product.get("image_url"),
                    "detail_url": product.get("product_url"),
                    "price": product.get("price"),
                    "review_count": product.get("review_count"),
                    "rating": product.get("rating"),
                    "observed_at": product.get("last_seen") or product.get("snapshot_date"),
                    "history_first_seen": product.get("first_seen"),
                    "history_last_seen": product.get("last_seen"),
                    "history_days_present": product.get("days_present"),
                    "history_snapshots_available": product.get("snapshots_available"),
                    "history_consecutive_snapshots": product.get("consecutive_snapshots"),
                    "history_repeat_rate": product.get("repeat_rate"),
                    "history_period_rank_change": product.get("period_rank_change"),
                    "history_rank_velocity": product.get("rank_velocity"),
                    "history_rank_consistency": product.get("rank_consistency"),
                    "history_rank_history": product.get("rank_history"),
                }
                for field, value in mappings.items():
                    if value not in (None, ""):
                        row[field] = value
                row["source_ref"] = (
                    f"sqlite://new_releases/{key[0]}/{asin}"
                    f"?as_of={product.get('last_seen') or product.get('snapshot_date') or ''}"
                )

    records = list(merged.values())
    records.sort(
        key=lambda row: (
            len(row.get("history_signals") or []),
            int(row.get("history_consecutive_snapshots") or 0),
            int(row.get("history_period_rank_change") or 0),
            -(int(row.get("new_release_rank") or 9999)),
        ),
        reverse=True,
    )
    return records[:limit]
