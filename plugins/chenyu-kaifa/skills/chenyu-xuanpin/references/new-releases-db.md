# new_releases.db 只读契约

## 职责边界

- 采集器是唯一写入方，负责按站点、类目和日期保存 Amazon New Releases 原始快照。
- `chenyu-xuanpin` 只以 SQLite `mode=ro` 打开数据库，计算时间窗口和选品信号，不创建表、不迁移、不更新数据。
- 不需要 MCP。数据库文件可由同机路径、挂载目录或服务器生成的一致性快照提供。
- 若复制一个启用 WAL 的在线数据库，必须用 SQLite backup/checkpoint 生成一致性快照；不能只复制尚未 checkpoint 的 `.db` 而遗漏 `-wal` 中的数据。

## 必需表

`observations` 是唯一硬依赖。每一行表示一个 ASIN 在某次新品榜日快照中的事实。

| 字段 | 类型 | 规则 |
|---|---|---|
| `source_url` | TEXT | 榜单来源 URL；同一站点不同节点不能混用空值 |
| `marketplace` | TEXT | 大写站点代码，如 `US`、`DE` |
| `category` | TEXT | 稳定类目标识，如 `party-supplies` |
| `snapshot_date` | TEXT | `YYYY-MM-DD`，表示榜单快照业务日期 |
| `rank` | INTEGER | 正整数，数值越小排名越高 |
| `asin` | TEXT | 大写 ASIN |
| `title` | TEXT | 当日页面可见标题 |
| `image_url` | TEXT | 当日主图地址；用于运行时视觉相似度比较，不得写占位图地址 |

推荐结构：

```sql
CREATE TABLE observations (
    source_url TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    category TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank > 0),
    asin TEXT NOT NULL,
    title TEXT NOT NULL,
    image_url TEXT NOT NULL,
    review_count INTEGER,
    price REAL,
    price_text TEXT,
    rating REAL,
    product_url TEXT,
    created_at TEXT,
    PRIMARY KEY (source_url, snapshot_date, asin)
);
```

推荐可选字段：

| 字段 | 类型 | 用途 |
|---|---|---|
| `review_count` | INTEGER | 快照时 Review 数 |
| `price` | REAL | 可比较的数值价格；未知时为 0 或 NULL |
| `price_text` | TEXT | 带币种的页面原文 |
| `rating` | REAL | 快照时星级 |
| `product_url` | TEXT | Amazon 商品链接 |
| `created_at` | TEXT | 实际写入时间 |

数据库只保存采集事实，不建立产品类型、分组标签、相似度、图片向量或模型结论字段。插件先用标题相似度做预筛，再读取 `image_url` 指向的主图做视觉相似度比较；结果只包含相似商品组的成员和成对证据，不给组命名，也不写回数据库。

当前实现要求 `image_url` 列存在。值为空、占位图、下载失败或图片不可解析时，该商品对没有完整视觉证据，不能判为同类。插件对一个分析请求中的相同图片地址只读取一次，并且仅为标题预筛通过的商品对读取图片，避免无差别下载全部图片。

## 推荐采集批次表

`collection_runs` 用来区分“当天确实为空”和“采集任务失败”，属于采集事实，不保存分析结论：

```sql
CREATE TABLE collection_runs (
    run_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    category TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE', 'FAILED')),
    item_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);
```

`observations` 可增加 `run_id TEXT` 外键关联此表。当前分析器不依赖该表，但采集器应保留它用于数据完整性审计。

## 推荐身份表

`product_seen` 不是硬依赖，但建议永久保留，用于回答“是否历史上第一次出现”。

```sql
CREATE TABLE product_seen (
    marketplace TEXT NOT NULL,
    asin TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    product_url TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (marketplace, asin)
);
```

若没有此表，插件把 `MIN(observations.snapshot_date)` 标记为“当前保留快照中首次出现”，不会声称它是全历史首次。若要保证“第一次出现”永远准确，不应按 10 天窗口删除 `product_seen`；原始 `observations` 可以单独设置保留期。

## 推荐索引

```sql
CREATE INDEX idx_observations_market_date
ON observations(marketplace, snapshot_date, asin);

CREATE INDEX idx_observations_asin_date
ON observations(marketplace, asin, snapshot_date);

CREATE INDEX idx_observations_category_date
ON observations(marketplace, category, snapshot_date, rank);
```

## 插件动作

只分析数据库：

```json
{
  "skill_action": "analyze_new_releases_db",
  "db_path": "D:/data/new_releases.db",
  "marketplaces": ["US", "DE"],
  "category": "party-supplies",
  "days": 10,
  "limit": 100,
  "history": {
    "recent_days": 3,
    "min_repeat_days": 3,
    "min_group_asins": 2,
    "max_similarity_products": 100,
    "title_similarity_min": 0.35,
    "image_similarity_min": 0.72,
    "combined_similarity_min": 0.68,
    "min_rank_improvement": 5,
    "min_rising_consistency": 0.6
  }
}
```

必须传入 `db_path` 或设置环境变量 `CHENYU_NEW_RELEASES_DB`；插件不会自动扫描目录猜测数据库位置。

用历史信号进入完整开品流程：

```json
{
  "skill_action": "run_discovery_flow",
  "request": "从过去10天新品榜找持续出现和排名上升的派对用品",
  "discovery": {
    "source": "new_releases_db",
    "history": {
      "db_path": "D:/data/new_releases.db",
      "category": "party-supplies",
      "days": 10,
      "min_repeat_days": 3,
      "min_rank_improvement": 5
    }
  }
}
```

历史数据库负责产生 `NEW`、`REPEAT`、`RISING` 候选信号；卖家精灵仍负责补上架日期、BSR和预估月销量，现有透明评分与 Excel 输出保持不变。

## 固定计算口径

- “今天”：分析日的精确快照。未传 `as_of_date` 时，分析日取数据库最新快照日，而不是强行使用系统日期。
- “昨天”：分析日前一个自然日；若当天漏采则返回空，同时另给 `previous_available`。
- “过去 N 天”：分析日向前包含当天的 N 个自然日，并报告其中实际有多少个快照日。
- “首次出现”：优先使用 `product_seen.first_seen`；没有身份表时使用当前保留快照中的最早日期并输出警告。
- “连续出现”：按数据库实际存在的快照日计算，漏采日不自动判定为商品断榜；同时输出出现次数、快照总数和连续次数。
- “最近扎堆”：不生成类型名或标签。插件仅在同站点、同类目内先比较标题，再比较主图；标题和图片证据均达到阈值、且组内任意两件商品都通过时，才返回一个无名称的相似商品组。输出组内 ASIN、标题、主图地址和成对相似度，不写回数据库。
- “排名越来越高”：分析日仍在榜、窗口首尾净提升达到阈值，并且上升步数占全部相邻变化的比例达到一致性阈值。排名数字下降表示排名提高。
- 数据库最新日不是系统今天时必须输出滞后警告，不能把旧快照表述为实时数据。
