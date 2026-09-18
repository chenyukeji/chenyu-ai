# 开发评审执行契约

## 现货匹配

报价必须绑定具体 supplier SKU。优先比较材质、尺寸、件数和用途要求；缺字段为 unknown，关键规格不一致为 alternative，不把图片相似当 exact。

采购加包装硬门槛来自 runtime-rules.json。组合按整套计算，至少包含两个组件并写明 shared_purchase_reason。

## 利润

每个站点/履约路径独立输入。核心字段缺失时返回 pending，不把缺失费用当 0：

- price_gross_eur
- vat_rate
- cny_per_eur
- purchase_cny
- packaging_cny
- referral_fee_eur
- fulfillment_fee_eur
- inbound_eur

仓储、退货预留和其他变动费用允许显式给 0。广告后贡献只有在广告订单占比、CPC、CVR 齐全或明确广告订单占比为 0 时计算。

```text
net revenue = gross price / (1 + VAT)
CM before ads = net revenue - referral - fulfillment - purchase/packaging - inbound - storage - returns reserve - other
ad cost per total order = ad order share × CPC / CVR
CM after ads = CM before ads - ad cost per total order
break-even CPC = CM before ads × CVR
break-even ACoS = CM before ads / explicit ad sales per order
```

## 评审

优先执行硬门槛，再看证据完整度：

- 中国卖家准入、采购包装上限或目标售价明确 fail → 淘汰。
- 市场证据不完整 → 继续研究。
- 现货/报价/样品未确认 → 询价验样。
- 完整基准情景广告后贡献不为正 → 暂缓，重新定价/降成本。
- 市场、现货、利润、样品均就绪 → 建议试销。

“建议试销”仍只是建议；采购数量和下单由人确认。

## Excel

固定输出 10 个 Sheet：00_Task 到 09_Trial_Card。Excel 是交付快照；计算真值仍来自可重复运行的 economics 工具和输入数据。
