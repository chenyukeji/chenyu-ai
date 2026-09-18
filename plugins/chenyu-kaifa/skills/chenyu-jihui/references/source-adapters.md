# 发现与市场验证数据入口

## 当前支持

chenyu-jihui/scripts/run.py 当前提供两类真实输入路径：

1. JSON/CSV 发现文件：用于 A / E / J 策略，将卖家精灵导出、浏览器抓取结果或人工结构化记录映射为统一 Candidate。
2. 结构化市场快照：将 Amazon 搜索页、商品页和 Review 已整理结果转换成 Evidence，再生成 Opportunity Card。

若运行宿主没有浏览器采集能力，插件只使用 JSON/CSV/结构化快照输入，不声称已自动登录卖家精灵或 Amazon。浏览器采集能力接入后只需把页面数据转换成这里的字段契约，候选去重、策略验证和机会卡逻辑无需重写。

## import_discovery_file

输入示例：

~~~json
{
  "skill_action": "import_discovery_file",
  "path": "discovery.csv",
  "strategy_id": "J",
  "as_of_date": "2026-09-18",
  "field_map": {
    "asin": "ASIN",
    "fulfillment": "配送方式",
    "source_available_date": "上架日期"
  },
  "requested_filters": {"fulfillment": "FBM", "age_days_max": 60},
  "applied_filters": {"fulfillment": "FBM", "age_days_max": 60}
}
~~~

规则：

- 只支持 .json / .csv，只读，单文件最大 20 MB、最多 50,000 行。
- requested_filters 与 applied_filters 一致时可自动记 verified；不一致为 mismatch。
- A：卖家所属地 CN 才 pass；缺所属地为 unknown。
- E：发现来源只接受 US / DE。
- J：必须 FBM，且 source_available_date 相对 as_of_date 为 0—60 天；缺日期保留 pending，61 天及以上 fail。
- 筛选未核实或 mismatch 的记录不进入 accepted，只进入 pending。
- 输出同时给出 accepted / pending / rejected 和统一去重 Candidate。

## build_market_evidence

输入搜索样本、商品详情和 Review 痛点标注，生成：

- target_market_demand：estimate，只表达当前样本/搜索线索，不冒充竞品真实订单。
- comparable_competition：独立商品组、广告组和覆盖状态。
- comparable_price：样本到手价/有效价 min/median/max。
- product_specs：竞品规格证据，不写入自有产品事实。
- review_pain_points：只接收有来源的人工/模型标注，不自动猜情绪。
- fulfillment_and_delivery：FBA observed / not_observed_in_sample / unknown。
- cn_seller_evidence：当前可比样本中的 CN 卖家证据，仅作准入信号。

### FBA 状态

- 任一相关商品组可信发现 FBA → observed。
- 计划样本完整、至少一组相关商品、配送身份均已知且未见 FBA → not_observed_in_sample。
- 样本未完成、无有效相关商品组或存在关键未知配送身份 → unknown。

任何状态都只描述当前样本，不外推到隐藏报价或全市场。

## 浏览器适配器边界

未来浏览器采集器必须输出：

- 请求筛选条件。
- 页面实际回读筛选条件。
- marketplace / page kind / query / location profile。
- observed_at。
- 页码与覆盖状态。
- ASIN / Parent ASIN / seller location / fulfillment / price / source date 等实际可见字段。
- 原始快照或 source_ref。

采集器不得：

- 编造网站私有 API。
- 绕过登录、验证码或访问限制。
- 只 sleep 后假定筛选已生效。
- 将页面失败解释为“0 个结果”。
- 将 SellerSprite 商品销量归因给当前可见卖家。
