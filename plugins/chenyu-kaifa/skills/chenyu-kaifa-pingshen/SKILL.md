---
name: chenyu-kaifa-pingshen
description: 晨玙 Amazon 产品开发评审。用于导入真实供应商报价并匹配现货 SKU，比较单品、多件装和现货组合，核算欧洲站单价利润、三价格三情景、广告盈亏线和试销资金，生成验样清单、开发评审、Product Master、部门交接、开发 Excel，并导入试销销售/广告/退货/库存数据做复盘。也用于从已有机会卡继续评审；不负责实际采购、付款、上架或广告执行。
version: 0.3.2
---

# 晨玙 Amazon 开发评审

只有证据、现货和经济模型足够时才推进。需求大不能覆盖硬成本门槛，缺数据也不能自动等于淘汰。

## 规则与输入

读取 [runtime-rules.json](references/runtime-rules.json)、[评审契约](references/review-contract.md) 和 [报价/交付/试销工具](references/import-delivery-trial.md)。优先接收 `chenyu-jihui` 的 Opportunity Card、供应商报价文件、站点费用与履约输入。

## 工作流

1. 若有供应商 JSON/CSV 报价，先用 `import_supplier_quotes` 校验 supplier SKU、实际数量档、报价有效期、币种和包装包含关系。失效报价不能证明当前成本。
2. 用 `match_supply` 核对材质、尺寸、件数、SKU、MOQ、交期与样品。多件装用 `build_multipack` 按整个销售单位核价；互补组合用 `build_bundle`，要求共同购买理由并按整套检查采购+包装 ≤ ¥20。
3. 用 `build_sample_checklist` 生成实物验样项；生成清单不等于样品已通过。
4. 用 `calculate_economics` 分站点/履约路径计算；核心费用缺失保持 pending，不把缺费率当 0。
5. 用 `calculate_scenario_matrix` 比较 €5 / 当前目标价 / €20 与 conservative/base/optimistic 三情景。初始 profile 标记为 proposed_not_calibrated，允许用户覆盖。
6. 用 `calculate_trial_funding` 算采购包装、头程、广告和明确固定投入形成的首批资金需求；它不批准采购数量。
7. 用 `review` 按硬门槛→市场证据→现货/报价→利润→样品顺序输出固定决策。
8. 对拟试销产品用 `create_trial_card` 写价格、数量、广告/损失预算、观察和退出条件；数量仍需人工批准。
9. 用 `build_delivery_sections` 生成 confirmed-only Product Master 与采购/运营/美工待办，再用 `export_workbook` 生成固定 10-Sheet 开发 Excel。
10. 有真实试销数据时用 `import_trial_data` 导入 JSON/CSV，再用 `review_trial` 对照 trial plan 的显式阈值输出继续测试、补货评审、调整或退出评审建议。

## 工具

在 Skill 包根目录运行：

```text
printf '<json>' | python scripts/run.py
```

动作：

- `status`
- `import_supplier_quotes`
- `match_supply`
- `build_multipack`
- `build_bundle`
- `build_sample_checklist`
- `calculate_economics`
- `calculate_scenario_matrix`
- `calculate_trial_funding`
- `review`
- `create_trial_card`
- `build_delivery_sections`
- `import_trial_data`
- `review_trial`
- `export_workbook`

脚本只使用 Python 标准库，不依赖数据库。输入文件只读；输出目录由调用方提供；运行结果不写入 Skill 包。

## 评审状态

员工展示固定为：

- 继续研究
- 询价验样
- 建议试销
- 暂缓
- 淘汰

试销复盘动作固定为建议：

- continue_test
- replenishment_review
- adjust
- exit_review

试销阈值来自 trial plan；没有阈值时不自行发明“成功标准”。

## 边界

- 报价过期、数量档不匹配、规格不明或币种未处理不能证明成本通过。
- 包装已含在报价里时不能再重复计包装成本。
- 不默认 VAT、佣金、FBA/FBM 费用、CPC、CVR 或退货成本。
- 生成验样清单不代表实物已验证。
- 试销复盘只建议动作，不自动补货、停广告、清货或下单。
- 不自动联系供应商、采购、付款、发货、修改店铺、发布 Listing 或启动广告。
- 合规、专利、认证和平台政策问题保持证据状态，并在实际销售前要求专业复核。
