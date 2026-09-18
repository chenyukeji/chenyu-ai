---
name: chenyu-kaifa
description: 晨玙 Amazon 产品开发总入口。用于接收开发目标、站点、类目/需求、预算、售价和时间要求，建立 Task Brief，选择多策略找品计划，并协调 chenyu-jihui 的机会研究与 chenyu-kaifa-pingshen 的现货/利润/评审/交付。适用于从“找产品”一直到开发 Excel、试销卡和复盘入口的综合任务；不直接采购、付款、上架或投放广告。
version: 0.2.1
---

# 晨玙 Amazon 产品开发

围绕 **找产品 → 验证需求 → 匹配现货 → 算利润 → 验样试销 → 交接复盘** 工作。总入口只负责任务理解、路由、阶段控制与汇总，不在这里复制专业 Skill 的研究和计算逻辑。

## 开始任务

读取 [运行规则](references/runtime-rules.json)、[数据契约](references/data-contracts.md) 和 [执行流程](references/workflow.md)。

对结构化任务运行：

```text
printf '<json>' | python scripts/run.py
```

支持：

- `status`
- `create_task`：建立 Task Brief，应用统一站点/价格/成本上限和策略规则。
- `plan`：形成 discovery → market_validation → supply_and_economics → handoff 四阶段计划。

未指定策略时 MVP 默认启用 A（中国卖家同类现货）、E（US/DE 新品榜）和 J（近60天 FBM）；有关键词、Review、组合、季节或店铺种子时再增加对应策略。策略只是发现入口，同一产品必须进入统一候选池去重。

## 专业路由

| 任务 | 执行 |
|---|---|
| 多策略找品、候选去重、市场与竞品验证、机会卡 | 读取并执行 [chenyu-jihui](../chenyu-jihui/SKILL.md) |
| 真实报价/现货、单品/多件装/组合、利润、评审、Excel、试销卡 | 读取并执行 [chenyu-kaifa-pingshen](../chenyu-kaifa-pingshen/SKILL.md) |
| 综合开发任务 | 先 Task Brief，再机会研究，再开发评审；复用同一 Candidate/Evidence，不重新研究 |

这里的路由由当前助手读取专业 Skill 并执行，不依赖独立后台 Agent。

## 统一业务基线

- 销售站点：DE / FR / IT / ES。
- 新品发现参考站点：US / DE。
- 目标含税售价：€5–20。
- 每个销售单位采购 + 包装 ≤ ¥20；组合按整套计算。
- 至少一个同类中国卖家只通过中国卖家准入项；仍须独立验证目标站需求、现货和利润。
- 方案优先现货单品、多件装和现货组合。
- 评分权重、销量门槛、采样数量保持可配置，未经真实试跑校准不作为全局硬门槛。
- 事实、估算、假设、待验证必须分开。

## 完成条件

综合 MVP 任务只有在以下成果真实存在时才算完成：

1. Task Brief 与执行计划。
2. 去重后的 Candidate Pool 与全部发现来源。
3. 至少一个 Opportunity Card，关键结论可回到 Evidence。
4. 真实 supplier SKU/报价对应或明确的待报价状态。
5. 可复算 Economics；缺费用时不得伪造最终利润。
6. 继续研究/询价验样/建议试销/暂缓/淘汰之一及 reason codes。
7. 需要交接时生成标准开发 Excel、Product Master、部门待办和试销卡。

不能把设计文档、空模板、未运行脚本或不存在的文件路径当完成。

## 边界

默认只读研究和计算。未经用户明确授权，不联系供应商、不采购、不付款、不修改 Amazon 店铺、不发布 Listing、不投放广告。合规、专利、认证和平台规则保持证据状态并要求适用的专业复核。
