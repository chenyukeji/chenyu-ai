---
name: chenyu-jihui
description: 晨玙 Amazon 产品机会研究。用于从 JSON/CSV、浏览器采集结果或结构化市场快照执行多策略找品、统一候选池去重、欧洲目标站需求验证、竞品价格规格、Review 痛点、配送与证据整理，并输出产品机会卡。适用于新品榜、中国卖家、关键词、近期商品、店铺扩品、历史旺季、近60天 FBM 等发现与验证；不负责供应商采购、最终利润评审或商品发布。
version: 0.2.1
---

# 晨玙 Amazon 机会研究

把“发现了什么”与“是否值得开发”分开。先形成统一候选池和可追溯证据，再把少量候选交给开发评审。

## 运行规则

读取 [runtime-rules.json](references/runtime-rules.json)、[机会研究契约](references/research-contract.md) 和 [来源适配契约](references/source-adapters.md)。直接调用时仍遵守 DE/FR/IT/ES 销售站、US/DE 新品发现、€5–20、至少一个同类中国卖家仅作为准入信号等统一规则。

## 工作流

1. 接收 Task Brief 或明确的站点、需求和策略。
2. 若有 JSON/CSV 发现结果，优先用 `import_discovery_file` 标准化。A/E/J 已实现策略级校验；筛选状态未核实时保留 pending。
3. 若运行宿主有浏览器采集能力，可按来源适配契约采集页面并转换成同一字段；没有浏览器能力时使用文件或结构化快照，不声称已实时采集。
4. 用 `merge_candidates` 按 ASIN、父体、已核实跨站 signature 去重，合并全部发现来源，并保留每次策略命中的 pass/unknown 与筛选核实状态。
5. 对优先候选用 `build_market_evidence` 形成目标站 Evidence：需求线索、独立商品组、价格、竞品规格、Review 痛点、配送/FBA 和中国卖家样本。
6. 所有关键数字区分 fact / estimate / assumption / pending_verification；缺失项不补造。
7. 用 `build_opportunity_card` 生成机会卡和最小补证动作。
8. 机会卡达到 `ready_for_supply_match` 后交给 `chenyu-kaifa-pingshen`；partial 候选继续补证，不因缺历史直接淘汰。

## 工具

在 Skill 包根目录运行：

```text
printf '<json>' | python scripts/run.py
```

动作：

- `status`
- `import_discovery_file`
- `merge_candidates`
- `build_market_evidence`
- `build_opportunity_card`

脚本只读输入文件，不联网、不写店铺、不采购。页面抓取属于运行宿主的浏览器能力，抓取结果必须先转换成契约对象。

## 关键语义

- A：中国卖家所属地明确为 CN 才通过该策略项；这只是准入信号。
- E：新品发现来源只接受 US / DE，欧洲四站继续单独验证。
- J：必须 FBM，且源可用日期相对 as-of 日期为 0—60 天；缺日期为 unknown，61 天及以上 fail。
- 请求筛选与页面/文件实际筛选不一致时为 mismatch，不能按成功筛选解释。
- SellerSprite 等第三方商品销量是 estimate，不归因给当前可见卖家。
- FBA 未观察到只有在样本完整、身份已知时才可写“本次样本未发现”；其他情况为 unknown。
- 父体和子体销量不能重复累计。

## 边界

- 不把榜单前 N 名称为全市场。
- 不把搜索结果总数当精确竞争规模。
- 不用竞品规格填补自有产品事实。
- 不把评分当未经校准的全局硬门槛。
- 不绕过登录、验证码或访问限制，不编造网站私有 API。
