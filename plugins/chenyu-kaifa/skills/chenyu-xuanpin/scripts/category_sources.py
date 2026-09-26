"""Resolve user-defined categories into validated Amazon collection inputs."""
from urllib.parse import urlsplit, urlunsplit


class CategoryInputError(ValueError):
    pass


DOMAINS = {"US": "amazon.com", "DE": "amazon.de"}


def normalize_url(value, market):
    if not isinstance(value, str):
        raise CategoryInputError(f"{market} 新品榜入口必须是 URL 字符串")
    parsed = urlsplit(value.strip())
    domain = DOMAINS[market]
    if (parsed.scheme != "https" or parsed.hostname not in {domain, "www." + domain}
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise CategoryInputError(f"{market} 需要 https://www.{domain}/ 下的新品榜链接")
    path = parsed.path.split("/ref=", 1)[0].rstrip("/")
    prefix = "/gp/new-releases/"
    if prefix not in path or not path.split(prefix, 1)[1].strip("/"):
        raise CategoryInputError(f"{market} 需要具体类目的新品榜链接，不能使用搜索页、畅销榜或全站首页")
    # Tracking and pagination parameters must not produce duplicate sources/cache keys.
    return urlunsplit(("https", "www." + domain, path, "", ""))


def resolve_sources(resolution, markets):
    categories = resolution["categories"]
    sources, missing, seen = [], [], set()
    for category in categories:
        urls = dict(category.get("amazon_new_releases") or {})
        for market in markets:
            values = urls.get(market)
            if not values:
                missing.append(f"{category['name']} / {market}")
                continue
            values = values if isinstance(values, list) else [values]
            for value in values:
                url = normalize_url(value, market)
                key = (market, url, category["name"])
                if key not in seen:
                    sources.append({"marketplace": market, "url": url, "category": category["name"]})
                    seen.add(key)
    if missing:
        raise CategoryInputError("待补充新品榜入口：" + "；".join(missing)
                                 + "。类目可自定义，无需加入预设；查找并核实入口后写入 task.categories，再续跑同一 run_dir。")
    return sources
