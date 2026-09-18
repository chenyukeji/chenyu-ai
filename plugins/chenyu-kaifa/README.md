# 晨玙 Amazon 产品开发插件

面向产品开发岗位，围绕：

```text
找产品 → 验证需求 → 匹配现货 → 算利润 → 验样试销 → 交接复盘
```

## 当前可执行 Skill

| Skill | 职责 |
|---|---|
| `chenyu-kaifa` | Task Brief、策略路由、阶段计划和综合交付总入口 |
| `chenyu-jihui` | A/E/J JSON/CSV 发现导入、多策略候选合并、ASIN/父体去重、市场 Evidence 与 Opportunity Card |
| `chenyu-kaifa-pingshen` | 供应商报价导入、supplier SKU 匹配、组合/验样、三价格三情景利润、资金、评审、Excel、交接和试销复盘 |

三个 Skill 都带有可从包根目录运行的标准库脚本，stdin 输入 JSON，stdout 输出 JSON；不依赖数据库。

## 统一规则

- 销售站点：DE / FR / IT / ES。
- 新品发现：US / DE。
- 目标含税售价：€5–20。
- 每个销售单位采购 + 包装 ≤ ¥20，组合按整套。
- 至少一个同类中国卖家只代表该准入项通过。
- 现货单品、多件装、互补现货组合优先。
- 非硬性评分、销量阈值和采样数量等待真实试跑校准。

运行规则位于各 Skill 的 `references/runtime-rules.json`；仓库测试要求三份规则内容完全一致，保证子 Skill 可独立安装又不发生口径漂移。

## 可执行动作

`chenyu-kaifa/scripts/run.py`

- status
- create_task
- plan

`chenyu-jihui/scripts/run.py`

- status
- import_discovery_file
- merge_candidates
- build_market_evidence
- build_opportunity_card

`chenyu-kaifa-pingshen/scripts/run.py`

- status
- import_supplier_quotes
- match_supply
- build_multipack
- build_bundle
- build_sample_checklist
- calculate_economics
- calculate_scenario_matrix
- calculate_trial_funding
- review
- create_trial_card
- build_delivery_sections
- import_trial_data
- review_trial
- export_workbook

## Excel

开发 Excel 固定包含：

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

Excel 是交付快照，利润计算真值来自可重复运行的 economics 工具。

## 设计文档

根目录的 `01-欧洲站AI开品-业务与策略设计.md`、`02-欧洲站AI开品-工程实现与验收.md` 和 `03-欧洲站AI开品-初始规则配置.json` 保留为设计与追溯材料。真正运行时以 Skill 内的 runtime rules 和脚本为准。

详细研发状态见 [TASK-BOARD.md](TASK-BOARD.md)。

## 边界

默认只做研究、计算和文件交付。未经明确授权，不联系供应商、不采购、不付款、不修改 Amazon 店铺、不发布 Listing、不执行广告。实时市场结论必须来自实际采集或用户导入资料，不能把设计示例当当前数据。
