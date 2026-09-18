# 晨玙 Amazon 开发 AI 插件 Task Board

> 目标：把现有“欧洲站 AI 开品”设计落成可执行插件，围绕 **找产品 → 验证需求 → 匹配现货 → 算利润 → 验样试销 → 交接复盘** 建设。
>
> 第一版原则：先跑通一条真实完整链路，再扩策略和自动化；不为了“看起来完整”提前引入数据库。输入、过程证据和交付优先使用 JSON / CSV / Excel / Markdown 等可复核文件。

---

## 当前实际实现进度（2026-09-18）

已落地并通过真实验证：

- `chenyu-kaifa 0.3.1`：Task Brief、统一业务规则、策略路由和阶段计划。
- `chenyu-jihui 0.2.1`：A/E/J JSON/CSV 发现导入、筛选回读状态、60 天 FBM 语义、统一候选池去重、结构化市场 Evidence 与 Opportunity Card。
- `chenyu-kaifa-pingshen 0.3.2`：供应商报价导入与数量档/有效期校验、单品/多件装/组合、验样清单、三价格三情景利润、Break-even、试销资金、评审、Product Master、部门交接、10-Sheet Excel、试销数据导入与复盘。
- 开发插件自动化测试 33/33；仓库全量测试 50/50。
- 三个 Skill 均已通过 portable lint（0 error / 0 warning）和 package validate，并在 AgentDock 安装激活。
- Windows/AgentDock stdin 统一按 UTF-8 解码；开发 Excel 对 UTF-16 surrogate/非法 XML 字符安全清洗并采用临时文件原子写入，中文和 emoji 已用激活版本回放验证。
- 已用激活版本真实回放：J 文件导入 → Candidate → DE 市场 Evidence → Opportunity Card → 供应商报价文件 → exact SKU 匹配 → Economics → 9 个价格/情景组合 → 试销资金 → TRIAL_RECOMMENDED → Product Master/采购/运营/美工交接 → 试销 CSV → replenishment_review。
- 单品通过、组合通过、硬成本淘汰、中国卖家准入失败、缺数据、去重、报价失效/数量档错误等均有自动化验收。

当前宿主没有浏览器/Playwright MCP，因此 A/E/J 的“网页自动导航与采集”没有冒充完成。现在可直接使用 JSON/CSV/结构化网页快照；未来浏览器适配器只需按 source-adapters contract 输出相同字段，不需要重写候选池和验证逻辑。

仍属后续增强：B/C/D/F/H/I 其余策略的专用采集适配器、浏览器实时采集、报价版本差异报告、任务断点恢复、完整开发预测 vs 实际偏差归因与自动校准数据集。
---

## 1. 最终能力地图

| 能力 | 主责 Skill | 配套实现 | 固定交付 |
|---|---|---|---|
| 1. 开发任务入口 | `chenyu-kaifa` | 任务解析、策略路由、阶段状态 | Task Brief、执行计划 |
| 2. 多策略找品 | `chenyu-jihui` | 策略适配、候选标准化、去重 | 统一候选池、发现来源 |
| 3. 市场与竞品验证 | `chenyu-jihui` | 市场证据、竞品样本、评论痛点 | 产品机会卡、证据表、待验证项 |
| 4. 现货与组合方案 | `chenyu-kaifa-pingshen` | 报价/现货映射、单品/多件装/组合比较 | 货源对应表、产品方案、验样要求 |
| 5. 利润与资金测算 | `chenyu-kaifa-pingshen` | 可复算计算器 | 利润表、盈亏线、试销资金 |
| 6. 开发评审 | `chenyu-kaifa-pingshen` | 阶段门槛、状态机、理由码 | 继续/询价验样/建议试销/暂缓/淘汰 |
| 7. 开发文档与交接 | `chenyu-kaifa-pingshen` | Excel/Product Master 导出 | 标准开发 Excel、Product Master、部门待办 |
| 8. 试销复盘 | `chenyu-kaifa-pingshen` | 真实销售数据导入、预期对比 | 继续测试/补货/调整/退出建议 |

---

## 2. Skill 结构

### 2.1 `chenyu-kaifa`：开发总入口

只负责：

1. 理解任务。
2. 校验必要输入。
3. 选择策略与阶段。
4. 调用机会研究或开发评审能力。
5. 汇总最终交付。
6. 明确当前缺口和下一步。

不在总入口里重复实现采集、去重、利润公式或 Excel 生成。

### 2.2 `chenyu-jihui`：机会研究

负责：

- 多策略候选发现。
- 统一候选池。
- ASIN / 产品实体 / 来源去重。
- 欧洲目标站需求验证。
- 竞品、价格、规格、Review 痛点、配送验证。
- 生成机会卡和证据包。

### 2.3 `chenyu-kaifa-pingshen`：开发评审

负责：

- 供应商现货和具体 SKU 对应。
- 单品、多件装、组合设计。
- 成本、平台费用、广告、退货、利润、现金需求。
- 样品与小批量试销条件。
- 开发 Excel、Product Master 和部门交接。
- 试销结果复盘。

---

## 3. P0 业务基线：任何功能开发前先锁定

这些规则不是评分建议，而是第一版业务基线：

- 销售站点：DE / FR / IT / ES。
- 新品发现参考站点：US / DE。
- 目标含税售价：€5–20。
- 采购 + 包装：每个销售单位不超过 ¥20；组合按整套计算。
- 至少 1 个同类中国卖家在卖，只表示“中国卖家准入”通过；不得替代目标站需求和利润验证。
- 前期方案：现货单品、多件装、现货组合。
- 评分权重、销量门槛、采样数量保持可配置，未经试跑校准不得变成不可绕过的全局硬门槛。
- 事实、估算、假设必须分开记录。
- 缺数据时输出 `pending_verification`，不得虚构。
- 同一产品被多个策略发现时合并来源，不重复研究、不重复计算市场销量。

### P0 配置任务

| ID | Status | 任务 | 产物 | 验收 |
|---|---|---|---|---|
| BASE-01 | DONE | 把 03 设计配置整理成正式运行配置 | `runtime-rules.json` | DE/FR/IT/ES、€5–20、¥20、中国卖家准入规则可被测试读取 |
| BASE-02 | DONE | 统一 `chenyu-kaifa` / `chenyu-kaipin` 命名 | 全插件一致命名 | 运行插件及设计文件已统一为 `chenyu-kaifa` |
| BASE-03 | DONE | 定义证据状态 | `fact / estimate / assumption / pending_verification` | Opportunity Card 已强制校验并保留 pending |
| BASE-04 | DONE | 定义时间语义 | `observed_at / period_start / period_end / source_market` | 已进入运行契约；真实网页采集仍待适配 |

---

## 4. 核心数据契约

### 4.1 开发任务 Task Brief

最低字段：

```text
task_id
sales_marketplaces[]
category_or_need
target_price_min/max
purchase_packaging_cap_cny
budget_cny
deadline
strategy_ids[]
excluded_products[]
required_outputs[]
```

验收：缺少非必要项可以继续；缺少会影响结论的项必须进入“待确认”，但不能阻塞可先执行的研究步骤。

### 4.2 统一候选池 Candidate Pool

每个候选必须至少有：

```text
candidate_id
need_cluster
product_name_normalized
product_signature
marketplace_listings[]
source_strategies[]
source_refs[]
first_seen_at
dedupe_confidence
merge_reason
research_status
```

去重规则分层：

1. 同 marketplace + 同 ASIN：直接合并来源。
2. Parent/Child：保留 listing 身份，但市场汇总必须防止父子销量重复累计。
3. 跨站点同款：只有规格/图片/型号等证据足够时才合并产品实体。
4. 仅标题相似：不得自动强合并。
5. 被 A/E/J 等多个策略同时发现：`source_strategies[]` 追加来源，不新建重复研究任务。

### 4.3 Evidence 证据对象

```text
evidence_id
candidate_id
field
value
unit
evidence_status
source_type
source_ref
source_market
observed_at
period_start/end
notes
```

验收：最终结论中的关键数字都能反查 evidence。

### 4.4 Supply Match 现货匹配

```text
supplier
supplier_sku
candidate_id
match_type: exact / compatible / alternative / unknown
material
size
color
pack_count
unit_quote_cny
packaging_cny
moq
lead_time_days
sample_available
sample_status
mismatch_notes
```

### 4.5 Economics 利润模型

输入至少包括：

- 含税售价。
- VAT / 税口径。
- 采购。
- 包装。
- 国内段/头程。
- Amazon referral fee。
- FBA 或 FBM 履约费用。
- 仓储预留。
- 广告。
- 退货/退款预留。
- 汇率。
- 其他可选费用。

输出至少包括：

- 单件贡献利润。
- 贡献利润率。
- 广告前利润。
- Break-even ACoS。
- Break-even CPC（有转化率时）。
- 不同售价情景。
- 保守/基准/乐观三情景。
- 首批试销量对应资金需求。
- 成本或汇率变化敏感性。

---

## 5. Task Board

状态统一使用：

- `TODO`
- `DOING`
- `BLOCKED`
- `REVIEW`
- `DONE`

优先级：

- **P0**：第一条端到端链路必须完成。
- **P1**：MVP 稳定后立即补齐。
- **P2**：规模化、自动化、体验增强。

### Epic A — 基础架构与 3-Skill 骨架

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| A-01 | P0 | DONE | 重构 `chenyu-kaifa` 总入口 | BASE | 能按“研究/评审/复盘”路由，不重复实现子能力 |
| A-02 | P0 | DONE | 新建 `chenyu-jihui` | BASE | 描述能稳定触发找品、竞品、需求验证 |
| A-03 | P0 | DONE | 新建 `chenyu-kaifa-pingshen` | BASE | 描述能稳定触发现货、利润、评审、交接、复盘 |
| A-04 | P0 | DONE | 为三个 Skill 建立 references / tests | A-01~03 | 核心规则不塞进超长 SKILL.md，引用可独立读取 |
| A-05 | P0 | DONE | 更新 plugin.json / agents UI | A-01~03 | 三个 Skill 均进入插件且名称/描述一致 |
| A-06 | P0 | DONE | 建立跨 Skill 数据契约测试 | A-02~03 | Candidate/Evidence/Supply/Economics 字段兼容 |

### Epic B — 开发任务入口

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| B-01 | P0 | DONE | Task Brief 解析 | A-01 | 能识别站点、价格、预算、时间、类目/需求 |
| B-02 | P0 | DONE | 默认业务规则补全 | B-01 | 未显式覆盖时使用 DE/FR/IT/ES、€5–20、¥20 |
| B-03 | P0 | DONE | 策略选择器 | B-01 | 支持单选、多选和“自动推荐策略组合” |
| B-04 | P0 | DONE | 阶段计划生成 | B-03 | 输出本次要跑的阶段、输入缺口、交付件 |
| B-05 | P1 | TODO | 任务恢复/继续执行 | B-04 | 能从现有候选池/机会卡/报价表继续，而非重新研究 |

### Epic C — 多策略找品与统一候选池

策略注册表保留：A / B / C / D / E / F / H / I / J。

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| C-01 | P0 | DONE | 策略注册表 contract | A-02 | 每个策略声明输入、输出、站点、时间语义 |
| C-02 | P0 | DONE | 候选标准化函数 | C-01 | 不同来源统一成 Candidate |
| C-03 | P0 | DONE | ASIN/产品实体去重 | C-02 | 同款多来源只保留一条研究主体 |
| C-04 | P0 | DONE | 来源合并与理由记录 | C-03 | 可看到“新品榜 + 关键词 + 店铺”等多来源 |
| C-05 | P0 | DOING | A：中国卖家同类发现 | C-01 | 至少一个可比中国卖家只通过该准入项 |
| C-06 | P0 | DOING | E：US/DE 新品榜发现 | C-01 | US/DE 用于发现，欧洲目标站另行验证 |
| C-07 | P0 | DOING | J：近60天 FBM 发现 | C-01 | 年龄、FBM、销量/Review 信息保留证据时间语义 |
| C-08 | P1 | TODO | B：近期商品需求 | C-01 | 候选可进入统一池 |
| C-09 | P1 | TODO | C：关键词需求 | C-01 | 关键词来源不生成重复候选 |
| C-10 | P1 | TODO | D：Review 痛点反推产品 | C-01 | 痛点能关联到 need_cluster |
| C-11 | P1 | TODO | I：店铺扩品 | C-01 | 店铺来源进入同一候选池 |
| C-12 | P1 | TODO | F：现货组合发现 | Supply contract | 组合候选有共同购买理由与整套成本 |
| C-13 | P1 | TODO | H：历史旺季 | 时间规则 | 历史月份和今年验证分开 |
| C-14 | P2 | TODO | 多策略并行/批量运行优化 | C-05~13 | 并行不产生重复研究和重复销量 |

> MVP 不要求一次实现所有采集器；要求先实现统一策略 contract + 候选池 + 去重，并至少用 A/E/J 或导入数据跑通多来源合并。

### Epic D — 市场与竞品验证

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| D-01 | P0 | DONE | 目标站需求验证模板 | C | DE/FR/IT/ES 分站记录证据 |
| D-02 | P0 | DONE | 价格带与可比竞品样本 | D-01 | 目标售价和真实竞争价格不混淆 |
| D-03 | P0 | DONE | 规格/材质/件数对比 | D-01 | 可直接服务后续现货匹配 |
| D-04 | P0 | DONE | Review 痛点归类 | D-01 | 痛点有频次/来源/证据，不只写总结 |
| D-05 | P0 | DONE | 配送/FBA/FBM 情况 | D-01 | 履约路径进入利润模型 |
| D-06 | P0 | DONE | 机会卡生成 | D-02~05 | 一张卡含事实、估算、缺口和下一步 |
| D-07 | P0 | DONE | 待验证项机制 | D-06 | 缺少关键证据不被自动包装成肯定结论 |
| D-08 | P1 | TODO | 机会评分可配置 | D-06 | 权重/阈值可修改且不会覆盖硬门槛 |

### Epic E — 现货、组合与验样

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| E-01 | P0 | DONE | 导入供应商报价/现货表 | Supply contract | 能映射 supplier SKU |
| E-02 | P0 | DONE | 真实款式/尺寸/材质匹配 | E-01,D-03 | 有 exact/compatible/alternative/unknown |
| E-03 | P0 | DONE | 单品方案 | E-02 | 成本和规格可进入利润计算 |
| E-04 | P0 | DONE | 多件装方案 | E-02 | pack_count、包装、整套成本正确 |
| E-05 | P0 | DONE | 两款现货组合 | E-02 | 必须有明确共同购买理由 |
| E-06 | P0 | DONE | 组合硬约束 | E-05 | 组合采购+包装按整套检查 ¥20 规则 |
| E-07 | P0 | DONE | 验样清单 | E-03~05 | 规格、外观、功能、包装、质量逐项确认 |
| E-08 | P1 | TODO | 报价版本对比 | E-01 | 能识别价格/交期/MOQ变化 |

### Epic F — 利润、资金与开发评审

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| F-01 | P0 | DONE | 利润计算器 | E | 输入输出可序列化，可复算 |
| F-02 | P0 | DONE | DE/FR/IT/ES 分站计算 | F-01 | VAT/费用口径不跨站混用 |
| F-03 | P0 | DONE | €5/目标价/€20 或指定价格情景 | F-01 | 至少 3 个售价情景可比较 |
| F-04 | P0 | DONE | 保守/基准/乐观情景 | F-01 | 广告、退货、成本等假设可追溯 |
| F-05 | P0 | DONE | Break-even ACoS | F-01 | 公式有测试 |
| F-06 | P0 | DONE | 试销资金需求 | F-01 | 数量×采购/包装/物流/费用口径清楚 |
| F-07 | P0 | DONE | 开发状态机 | D,E,F | 阶段不可跳过关键证据 |
| F-08 | P0 | DONE | 决策理由码 | F-07 | 每个决策可解释且能反查证据 |
| F-09 | P1 | TODO | 敏感性分析 | F-01 | 成本/汇率/广告变化能重算 |

推荐评审状态：

```text
DISCOVERED
→ SCREENED
→ MARKET_VERIFIED
→ SUPPLY_MATCHED
→ ECONOMICS_READY
→ SAMPLE_REQUIRED
→ TRIAL_RECOMMENDED
→ TRIAL_RUNNING
→ REVIEWED
```

可在任何适用阶段转入：

```text
NEEDS_MORE_RESEARCH
QUOTE_SAMPLE
HOLD
REJECTED
EXITED
```

对员工展示的业务决策固定为：

- 继续研究
- 询价验样
- 建议试销
- 暂缓
- 淘汰

### Epic G — 固定交付与部门交接

第一版 Excel 固定 Sheet：

```text
00_Task
01_Candidates
02_Evidence
03_Opportunity_Cards
04_Supply_Match
05_Economics
06_Decision
07_Product_Master
08_Handoff
09_Trial_Card
```

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| G-01 | P0 | DONE | 标准开发 Excel Schema | B~F | 字段固定、可版本化 |
| G-02 | P0 | DONE | Excel 导出器 | G-01 | 同一输入重复生成结果稳定 |
| G-03 | P0 | DONE | Product Master | E,F | 只写已确认事实，未确认字段明确标记 |
| G-04 | P0 | DONE | 采购待办 | E | SKU、报价、样品、MOQ、交期明确 |
| G-05 | P0 | DONE | 运营待办 | D,F | 站点、定位、价格、试销假设明确 |
| G-06 | P0 | DONE | 美工待办 | D,E | 产品事实、尺寸、材质、场景与参考资料明确 |
| G-07 | P0 | DONE | 试销卡 | F | 目标、数量、价格、广告、成功/退出条件明确 |
| G-08 | P1 | TODO | Markdown/JSON 同步导出 | G-02 | 便于 AI 后续继续处理 |

### Epic H — 试销复盘

真实数据输入至少支持：

```text
units
revenue
sessions
orders
conversion_rate
ad_spend
ad_sales
acos
tacos
returns
refunds
rating
review_issues
actual_landed_cost
inventory
stockout_days
observed_period
```

| ID | Pri | Status | 任务 | 依赖 | 验收标准 |
|---|---|---|---|---|---|
| H-01 | P1 | DONE | 试销结果导入 | G-07 | 能读取真实销售/广告/退货/库存 |
| H-02 | P1 | DOING | 预期 vs 实际对比 | H-01 | 对开发时假设逐项复盘 |
| H-03 | P1 | DOING | 偏差理由 | H-02 | 价格、流量、转化、广告、成本、质量分开 |
| H-04 | P1 | DONE | 复盘决策 | H-02 | 输出继续测试/补货/调整/退出 |
| H-05 | P1 | TODO | 规则校准数据 | H-02 | 真实试跑结果可用于后续调整评分/门槛 |

---

## 6. MVP 垂直切片：必须先跑通

第一版只要这条链路没有真实跑通，就不进入“功能已完成”：

```text
创建开发任务
→ 选择策略
→ 导入/采集候选
→ 统一候选池去重
→ 选 1 个候选做目标站验证
→ 生成机会卡
→ 导入真实供应商报价
→ 对应具体 supplier SKU
→ 单品/多件装/组合至少选一种
→ 可复算利润
→ 形成评审结论
→ 输出开发 Excel
→ 输出试销卡
```

### MVP 必做任务

```text
BASE-01~04
A-01~06
B-01~04
C-01~07
D-01~07
E-01~07
F-01~08
G-01~07
TEST-01~05
```

P1/P2 不得阻塞这条主链路上线验收。

---

## 7. 三个强制验收案例

### TEST-01 单品通过案例

场景：

- 候选从至少两个策略来源进入统一候选池。
- 同一产品只生成一个 candidate。
- 目标欧洲站有独立需求证据。
- 有真实 supplier SKU 和报价。
- 采购+包装 ≤ ¥20。
- 利润模型通过。

必须产出：

- 候选来源合并记录。
- 机会卡。
- 货源对应表。
- 利润表。
- “建议试销”或“询价验样”评审。
- 开发 Excel。
- 试销卡。

### TEST-02 组合通过案例

场景：

- 两个现货 SKU。
- 有明确共同购买理由。
- 组合按整套核算。
- 采购+包装整套 ≤ ¥20。
- 组合相对单品有可解释价值。

必须产出：

- bundle components。
- bundle reason。
- 整套成本。
- 包装要求。
- 组合利润。
- 验样清单。

### TEST-03 有依据淘汰案例

场景至少命中一个真实淘汰原因：

- 目标站需求证据不足且补证后仍不成立。
- 现货无法匹配关键规格。
- 采购+包装超过硬约束。
- 利润/广告盈亏线不可接受。
- 合规/产品风险无法在当前项目内解决。

必须证明：

- 不是因为“AI 觉得不好”。
- 有明确理由码。
- 有证据引用。
- 能区分“暂缓”和“淘汰”。

### TEST-04 去重案例

同一产品分别由新品榜、关键词、店铺或 FBM 策略发现：

- Candidate 只保留一个主体。
- `source_strategies[]` 至少两个。
- 市场销量不会重复叠加。

### TEST-05 缺数据案例

缺少关键报价、费用或市场证据时：

- 不生成虚假值。
- 标记 pending。
- 利润结果说明不可决策或显示区间。
- 输出下一步最小补证动作。

---

## 8. 工程质量任务

| ID | Pri | Status | 任务 | 验收 |
|---|---|---|---|---|
| Q-01 | P0 | DONE | 单元测试：去重 | 父子体、同 ASIN、多策略、跨站点边界覆盖 |
| Q-02 | P0 | DONE | 单元测试：利润公式 | 已知输入得到固定结果 |
| Q-03 | P0 | DONE | 单元测试：硬门槛 | ¥20、中国卖家准入语义正确 |
| Q-04 | P0 | DONE | 单元测试：证据状态 | estimate 不会被输出成 fact |
| Q-05 | P0 | DONE | Excel round-trip 检查 | 打开后字段和公式/数值完整 |
| Q-06 | P0 | DONE | Skill lint | portable=true |
| Q-07 | P0 | DONE | plugin/skill validate | 包合法 |
| Q-08 | P0 | DONE | 本地安装激活验证 | AgentDock 能索引并读取 3 个 Skill |
| Q-09 | P0 | DONE | 端到端回放 | 三个强制案例通过 |
| Q-10 | P1 | DONE | 页面/采集适配失败回退 | 可使用文件导入继续，不把采集失败变业务失败 |

---

## 9. 建议实施顺序

### Milestone M0 — 契约冻结

目标：先解决“大家说的是不是同一件事”。

完成：

```text
BASE-01~04
A-01~06
```

Exit Criteria：

- 3 Skill 边界明确。
- 统一 Candidate / Evidence / Supply / Economics contract 定稿。
- 业务硬规则与可调规则分离。

### Milestone M1 — 机会研究可执行

完成：

```text
B-01~04
C-01~07
D-01~07
```

Exit Criteria：

- 能从至少两种发现来源生成统一候选池。
- 能去重。
- 能生成欧洲目标站机会卡。
- 每个关键结论有证据状态。

### Milestone M2 — 报价、利润与评审

完成：

```text
E-01~07
F-01~08
```

Exit Criteria：

- 能把候选对应到真实 supplier SKU。
- 能比较单品/多件装/组合。
- 利润可复算。
- 能输出明确开发状态和原因。

### Milestone M3 — 固定交付

完成：

```text
G-01~07
```

Exit Criteria：

- 一键形成开发 Excel、Product Master、部门待办、试销卡。
- 输出不依赖聊天记录才能理解。

### Milestone M4 — MVP 验收

完成：

```text
TEST-01~05
Q-01~09
```

Exit Criteria：

- 单品案例通过。
- 组合案例通过。
- 有依据淘汰案例通过。
- 多策略去重通过。
- 缺数据不造数。
- AgentDock 当前激活版本验证通过。

### Milestone M5 — 复盘和扩策略

完成：

```text
H-01~05
C-08~14
F-09
G-08
Q-10
```

Exit Criteria：

- 可导入真实试销数据。
- 能对比开发预测与实际。
- 能用真实结果校准非硬性阈值。
- 扩策略不会破坏统一候选池。

---

## 10. Definition of Done

一个任务只有同时满足以下条件才可改成 `DONE`：

1. 有真实代码/Skill/配置/模板变更，不是只写设计说明。
2. 有测试或可重复的验收步骤。
3. 输出字段能追溯到输入或证据。
4. 不虚构实时销量、Review、费用、报价或供应商能力。
5. 不把可调评分阈值误做成未经验证的全局硬门槛。
6. 新增行为后版本号按规范递增。
7. 相关 Skill lint / validate 通过。
8. 需要 AgentDock 激活的变更已在当前激活版本验证。
9. 不引入真实 Token、Cookie、账号凭据或设备私有状态。
10. 与本任务无关的仓库文件不改动。

---

## 11. 每次研发提交建议

为了避免“纸上谈兵”，每个任务提交尽量包含：

```text
1. 实现
2. 测试
3. 一个最小输入样例
4. 一个真实输出样例或 fixture
5. README / reference 更新
6. 验证结果
```

推荐提交粒度：

```text
feat(kaifa): add candidate pool contract and dedupe
test(kaifa): cover multi-strategy candidate merging

feat(jihui): add opportunity card generation
test(jihui): keep missing evidence pending

feat(kaifa-pingshen): add economics calculator
test(kaifa-pingshen): verify break-even acos

feat(kaifa): export development workbook
test(kaifa): validate workbook sheets
```

不要把一个 Milestone 的全部内容压成一个超大提交。

---

## 12. 当前执行起点

当前应从以下顺序开始：

1. **BASE-01~04**：把设计稿变成正式可执行 contract。
2. **A-01~03**：建立 3 个 Skill。
3. **C-02~04**：先实现统一候选池与去重。
4. **D-06**：机会卡固定输出。
5. **E-01~02**：导入真实报价并对应 supplier SKU。
6. **F-01~06**：利润和资金模型。
7. **G-01~07**：开发 Excel 和试销卡。
8. 用 **TEST-01 / TEST-02 / TEST-03** 做第一轮端到端验收。

只要这 8 步跑通，插件就从“设计文档”进入了“员工可实际使用的 MVP”。
