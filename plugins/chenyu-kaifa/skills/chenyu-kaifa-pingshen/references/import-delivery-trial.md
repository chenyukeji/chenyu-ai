# 报价、交付与试销数据工具

## 供应商报价导入

import_supplier_quotes 支持 JSON / CSV，只读导入并校验：

- supplier / supplier_sku。
- 实际数量档 min/max/MOQ。
- 报价有效期。
- 币种。
- 单价。
- 包装是否已包含，避免重复计费。
- 材质、尺寸、件数等 SKU 对应字段。

只有当前计划数量落在报价区间、报价未过期、SKU 存在且成本字段足够时才进入 valid。失效报价保留在 invalid，不得证明当前成本通过。

每条 valid quote 会产出 match_supplier_item，可以直接传给 match_supply。

## 三价格 × 三情景

calculate_scenario_matrix 默认以 €5、当前目标价、€20 三个价格参考运行：

- conservative
- base
- optimistic

初始 profile 明确标记为 proposed_not_calibrated。其中保守情景沿用设计稿的售价下降、CPC 上升、CVR 下降、采购/头程上升、退货预留增加思路；乐观参数也只是初始可调 profile，不是预测概率。

用户可传入自己的 profile 覆盖默认值。

## 验样

build_sample_checklist 根据候选规格、supplier SKU 和单品/组合模式生成实物检查清单。生成清单不等于样品已通过，所有检查项初始都是 pending_physical_verification。

组合额外检查：

- 共同购买理由。
- 组件兼容。
- 实际数量。
- 整套包装。
- 包装后尺寸与重量。

## 试销资金

calculate_trial_funding 计算：

- 采购 + 包装。
- 头程现金。
- 广告预算。
- 固定准备成本。
- 其他明确初始现金。

输出是资金需求，不自动批准采购数量。定金/尾款时点、可抵扣进口 VAT 等没有显式输入的现金项会列为排除项。

## Product Master 与部门交接

build_delivery_sections 只把 status=confirmed 的自有产品事实放进 Product Master；未确认事实单列 pending。

固定生成采购、运营、美工待办，分别围绕：

- supplier SKU / 报价 / MOQ / 交期 / 样品。
- 站点 / 售价 / 评审 / 试销参数。
- 已确认产品事实和待确认产品事实。

## 试销数据导入与复盘

import_trial_data 支持 JSON / CSV，字段可包含：

- sessions / orders / units / revenue。
- ad_spend / ad_sales。
- returns / refunds。
- inventory / stockout_days。
- rating。
- actual_landed_cost。
- contribution_total。

review_trial 只根据 trial plan 中显式的 review_thresholds 判定，不自行发明成功门槛。可输出：

- continue_test
- replenishment_review
- adjust
- exit_review

所有动作仅是建议，不自动补货、停广告、清仓或下单。
