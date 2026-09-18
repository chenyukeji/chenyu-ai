---
name: chenyu-jihui
description: 晨玙 Amazon 产品机会研究。用于多策略找品、统一候选池去重、欧洲目标站需求验证、竞品价格规格、Review 痛点、配送与证据整理，并输出产品机会卡。适用于新品榜、中国卖家、关键词、近期商品、店铺扩品、历史旺季、近60天 FBM 等发现与验证；不负责供应商采购、最终利润评审或商品发布。
version: 0.1.1
---

# 晨玙 Amazon 机会研究

把“发现了什么”与“是否值得开发”分开。先形成统一候选池和可追溯证据，再把少量候选交给开发评审。

## 运行规则

读取 [runtime-rules.json](references/runtime-rules.json) 和 [机会研究契约](references/research-contract.md)。直接调用时仍遵守 DE/FR/IT/ES 销售站、US/DE 新品发现、€5–20、至少一个同类中国卖家仅作为准入信号等统一规则。

## 工作流

1. 接收 Task Brief 或明确的站点/需求/策略。
2. 按启用策略读取网页采集结果或结构化导入；采集失败可回退文件导入。
3. 运行 `python scripts/run.py` 的 `merge_candidates`，按 ASIN/父体/已核实 signature 去重并合并全部发现来源。
4. 对优先候选补目标站需求、竞争、价格、规格、评论和配送证据。
5. 所有关键数字建立 Evidence；缺失项使用 `pending_verification`。
6. 运行 `build_opportunity_card`，生成机会卡和最多三个最小补证动作。
7. 机会卡达到 `ready_for_supply_match` 后交给 `chenyu-kaifa-pingshen`；partial 候选可继续补证，不因缺历史直接淘汰。

## 工具

stdin JSON：

```text
printf '<json>' | python scripts/run.py
```

动作：

- `status`
- `merge_candidates`
- `build_opportunity_card`

工具不联网、不写店铺、不采购。网页采集由当前环境的浏览器/MCP 适配器负责，再把结果转换为契约对象。

## 边界

- 不把榜单前 N 名称为全市场。
- 不把第三方估算销量归因给当前可见卖家。
- 不把父体和子体销量重复累计。
- 不因为未观察到 FBA 就声称全市场没有 FBA。
- 不用竞品规格填补自有产品事实。
- 不把评分当未经校准的全局硬门槛。
