from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


STOPWORDS = {
    "a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "with",
    "new", "pack", "set", "piece", "pieces", "pcs", "size", "small", "medium", "large",
    "black", "white", "red", "blue", "green", "pink", "best", "premium", "upgraded",
}
HEAD_NOUNS = {
    "gloves", "lights", "light", "bags", "bag", "holder", "holders", "cover", "covers",
    "organizer", "organizers", "toy", "toys", "bottle", "bottles", "brush", "brushes",
    "mat", "mats", "rack", "racks", "case", "cases", "decorations", "decoration", "costume",
    "costumes", "mask", "masks", "socks", "blanket", "blankets", "pillow", "pillows",
    "candle", "candles", "charger", "chargers", "adapter", "adapters", "container", "containers",
}


def normalize_title(title: str) -> str:
    text = title.casefold().replace("&", " and ")
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> list[str]:
    tokens = normalize_title(title).split()
    return [token for token in tokens if token not in STOPWORDS and not token.isdigit() and len(token) > 1]


def infer_product_type(title: str, category: str = "") -> str:
    if category.strip():
        return normalize_title(category).title()
    tokens = title_tokens(title)
    if not tokens:
        return "Unknown Product"
    head_index = next((idx for idx in range(len(tokens) - 1, -1, -1) if tokens[idx] in HEAD_NOUNS), None)
    if head_index is None:
        return " ".join(tokens[: min(3, len(tokens))]).title()
    head = tokens[head_index]
    descriptors = [token for token in tokens[:head_index] if token not in HEAD_NOUNS]
    descriptor = descriptors[-1] if descriptors else ""
    return " ".join(part for part in (descriptor, head) if part).title()


def common_product_type(titles: Iterable[str], supplied: Iterable[str] | None = None) -> str:
    supplied_values = [value.strip() for value in (supplied or []) if value and value.strip()]
    if supplied_values:
        return Counter(supplied_values).most_common(1)[0][0]
    inferred = [infer_product_type(title) for title in titles if title]
    return Counter(inferred).most_common(1)[0][0] if inferred else "Unknown Product"
