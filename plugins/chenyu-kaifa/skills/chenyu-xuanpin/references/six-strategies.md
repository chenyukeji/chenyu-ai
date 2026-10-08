# 六种选品策略

每次 `run_discovery_flow` 明确选择一种策略。网页保存的 `strategy_selection` 优先；组合任务逐项运行后按站点与 ASIN 汇总，保留各策略证据。原有 A/B/D/F 策略与这六种策略一并保留在菜单中。A 支持导入数据；B/D/F 仍标明“暂未开放”，待实现后启用。

| ID | 名称 | 数据与执行方式 |
| --- | --- | --- |
| J | 近期 FBM 机会 | 卖家精灵实时筛选；沿用近 60 天、FBM、最低月销量和 AI 分析流程 |
| E | 新品榜发现 | Amazon 美德新品榜实时采集，卖家精灵补数 |
| I | 优质店铺上新跟踪 | 导入用户选定店铺的前后快照，比较新发现的 ASIN |
| C | 搜索热词机会 | 导入热词指标及对应 ASIN，按搜索量及可核验增长排列调研优先级 |
| H | 历史季节性选品 | 卖家精灵历史月份销量飙升筛选，也支持导入历史导出表 |
| K | 排名跃升发现 | 导入同站同类目的前后排名、统计窗口，识别名次改善商品 |

I/C/K 当前为数据导入流程，尚无专用自动采集器。不能把这些选项描述为已经自动访问店铺、热词榜或 Movers & Shakers。资料不足时说明具体缺项，不切换到新品榜代跑。

## H：历史季节性选品

以任务日期的去年同月为起点，加上随后 2 或 3 个月。默认 `h_following_months=2`，共 3 个自然月。12 月会正确跨年；不要截断到当年 12 月。例如以 2026-10-08 为任务日期，2 对应 2025-10、11、12；3 再包含 2026-01。

H 使用卖家精灵“选产品”的历史月份及销量飙升筛选，默认月销量至少 300、环比增幅至少 10%。该页面的历史月份和推荐模式参见[卖家精灵功能手册](https://www.sellersprite.com/cn/v3/knowledge/feature/product-research-for-beginners)。账号必须能够访问对应历史月份；账号身份、所选月份或对应查询响应无法验证时保留阻塞信息。未覆盖月份和分页截断须报告为部分覆盖。实际采集条件以保存的任务和原始结果为准。

```json
{
  "skill_action": "run_discovery_flow",
  "request": "通过去年同期销量飙升榜寻找季节性产品",
  "as_of_date": "2026-10-08",
  "strategy_selection": {
    "strategy_ids": ["H"],
    "source_marketplaces": ["US", "DE"],
    "parameters": {"h_following_months": 2}
  },
  "discovery": {"h_min_monthly_sales": 300, "h_min_growth_percent": 10, "h_keyword": "christmas"}
}
```

`h_keyword` 可省略，省略即所选站点全品类，不能把自然语言类目声称为已应用的筛选。原始记录包含 `marketplace`、`asin`、`history_month`、`estimated_sales`、`sales_growth_percent`（百分数，50 表示 50%）和 `source_ref`。历史月销绝不覆盖为今天的月销，H 不使用 `new_releases.db`。同站同 ASIN 同月去重，不因多次抓取提高命中月份数；没有出现在飙升榜不等于当月零销量。

输出各月销量、环比变化、命中月份最高销量及来源。仅凭一年的窗口只能称“季节性候选（待跨年复核）”。调研优先级公式为 `min(100, 25 + 15×命中月份数 + 0.15×min(最大增幅,200) + 0.01×min(命中月份最高月销,2000))`，不是季节性概率，也不直接给采购结论。确认可重复的季节性还要核对另一个年度及今年曲线。

## I / C / K 的原始证据

公共字段：`marketplace`、`asin`、`source_ref`。可附商品标题、品类、图片、售价、月销量和评论数。只使用输入中真实存在的指标。

- I：`seller_id`、`snapshot_date`（YYYY-MM-DD）、`snapshot_complete`（布尔值）。使用同站同店铺最近两次快照；首次只有一个快照不能声称有新上架。此前快照不完整时，差集只标为“新发现，不能确认实际新上架”。此前完整快照差集优先级 70，部分快照差集 40。“优质店铺”由用户的目标店铺清单确定，流程不凭店铺外观认定质量，也不创建定时跟踪任务。
- C：`keyword`、`search_volume`、`search_period`、对应的 `asin`。可附 `previous_search_volume`、`previous_search_period`；只有同站同口径的可比周期才输入上期值。缺少上期周期或上期量时不计算增长，不能把 0 基数算作无限增长。优先级为 `min(100,30+min(搜索量/1000,40)+min(max(增长百分数,0)/5,30))`。搜索需求并不等于商品销量。
- K：`current_rank`、`previous_rank`、`rank_category`、`window_hours`、`observed_at`；前后排名必须属于同站同类目同排名口径。只有排名数字下降才是改善；计算 `(此前排名-当前排名)/此前排名`，明确标为名次改善比例，不当作销量增幅，也不冒充 Amazon 页面展示的涨幅算法。优先级为 `min(100,30+70×改善比例)`，还需复核持续表现。

## 文件导入和续跑

`discovery_paths` 支持 JSON、UTF-8 CSV 和 XLSX（第一行表头）。中文常用字段可直接读取，如“站点、ASIN、历史月份、月销量、月销量增长率、搜索词、搜索量、卖家ID、快照日期、当前排名、此前排名”。其他复杂导出格式先检查原表并规范化，不能猜测不明字段。

文件缺少公共上下文时，可显式声明：

```json
{
  "discovery_paths": [
    {"path": "/path/to/2025-10.xlsx", "marketplace": "US", "history_month": "2025-10"},
    {"path": "/path/to/2025-11.xlsx", "marketplace": "US", "history_month": "2025-11"}
  ],
  "discovery": {"collect_live": false}
}
```

文件中的明确字段优先；没有 URL 时保留文件、工作表和行号作为来源。先确认文件确为目标历史月份，不能把下载日期当成统计月份。H 的窗口不足时如实说明资料覆盖；数据来源年份不能换成今年。续跑传原 `run_dir`、相同 `as_of_date` 和筛选参数；重新采集时用 `discovery.refresh=true`。`AWAITING_DISCOVERY_INPUT` 和 `NO_QUALIFIED_CANDIDATES` 不是已找到产品。
