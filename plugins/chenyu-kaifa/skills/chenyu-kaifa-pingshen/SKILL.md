---
name: chenyu-kaifa-pingshen
description: 晨玙 Amazon 产品开发评审。用于把机会卡与真实供应商现货/报价对应，比较单品、多件装和现货组合，核算欧洲站利润、广告盈亏线和试销资金，形成继续研究/询价验样/建议试销/暂缓/淘汰结论，并导出开发 Excel、Product Master、部门交接和试销卡。也用于导入已有研究结果继续评审；不负责实际采购、付款、上架或广告执行。
version: 0.1.1
---

# 晨玙 Amazon 开发评审

只有证据、现货和经济模型足够时才推进。需求大不能覆盖硬成本门槛，缺数据也不能自动等于淘汰。

## 规则与输入

读取 [runtime-rules.json](references/runtime-rules.json) 和 [评审契约](references/review-contract.md)。优先接收 `chenyu-jihui` 的 Opportunity Card、供应商具体 SKU/报价、站点费用与履约输入。

## 工作流

1. 用 `match_supply` 核对材质、尺寸、件数、SKU、MOQ、交期、样品与报价。
2. 多件装按一个销售单位核价；互补组合用 `build_bundle`，要求共同购买理由并按整套检查采购+包装 ≤ ¥20。
3. 用 `calculate_economics` 分站点/履约路径计算；核心费用缺失保持 pending。
4. 用 `review` 按硬门槛→市场证据→现货/报价→利润→样品顺序输出固定决策。
5. 对拟试销产品用 `create_trial_card` 写价格、数量、广告/损失预算、观察和退出条件；数量仍需人工批准。
6. 用 `export_workbook` 生成固定 10-Sheet 开发 Excel。Product Master 只写已确认自有事实。
7. 有真实试销数据后再做复盘；没有经营数据时不声称已完成复盘。

## 工具

stdin JSON：

```text
printf '<json>' | python scripts/run.py
```

动作：

- `status`
- `match_supply`
- `build_bundle`
- `calculate_economics`
- `review`
- `create_trial_card`
- `export_workbook`

脚本只使用 Python 标准库，不依赖数据库。输出目录由调用方提供；运行结果不写入 Skill 包。

## 边界

- 报价过期、数量档不匹配或规格不明不能证明成本通过。
- 不默认 VAT、佣金、FBA/FBM 费用、CPC、CVR 或退货成本。
- 不自动联系供应商、下单、付款、发货、修改店铺、发布 Listing 或启动广告。
- 合规、专利、认证和平台政策问题保持证据状态，并在实际销售前要求专业复核。
