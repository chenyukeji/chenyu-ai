# 输入字段与填写规则

| JSON 字段 | 规则 |
| --- | --- |
| `order_id` | 必填，Amazon 订单号 `000-0000000-0000000`；打印在 `Item No.` 列，分三行居中 |
| `purchase_date` | **必填**，Amazon 订单购买日期，`YYYY-MM-DD`；打印到 `Date:`，格式 `DD/MM/YYYY`。不得使用配送截至日期或生成 PDF 的当天日期 |
| `invoice_date` | 历史输入兼容字段：由 `purchase_date` 自动覆盖，不作为可信日期来源。命令行 `--invoice-date` 如提供必须等于 `purchase_date` |
| `currency` | 本 EUR 原母版**仅支持 EUR**，显示 `€` 和逗号小数 |
| `buyer.company` | 原 Amazon 订单企业买家显示名（如虚构样例 Entreprise Exemple），仅保留为来源元数据；**不填写**第一行，不当作收件人姓名 |
| `buyer.name` | 收件人姓名，填写到 **`Importer/Buyer/Receiver:` 后**。如虚构样例 `Camille EXEMPLE`；不是 Contact，也不是地址行 |
| `buyer.legal_company_name` | 本母版的 `Company Name:` **标签保留、值固定留空**；不把 `buyer.company` 或收件人重复写到这一行 |
| `buyer.address_lines` | **仅街道和楼栋**，不包含收件人、城市和邮编；不重复姓名；最多三行，溢出则提示，不裁剪 |
| `buyer.city`, `buyer.postal_code`, `buyer.country` | 目标城市、邮编、国家。法国时沿用原模板 France；比利时等其他国家仅替换国家值，不改原版布局 |
| `buyer.remote_area` | 仅确认偏远区时填布尔值 `true/false`，否则留空，不沿用旧单 No |
| `buyer.tel` / `tracking_number` | 可选，未经确认留空 |
| `seller` / 独立 `--seller` JSON | 原母版已固定卖家抬头、地址、电话和销售联系人；核对后使用，可选填 seller.vat_number；遇到不一致必须换母版 |
| `items[]` | 每项 `title`、`quantity`、`unit_price`、`line_total` 必填；`description` 推荐填写，若无则从标题中提取确实出现的产品词，不可空着整列 |
| `items[].sku`, `items[].asin` | 只作来源校验；**不要把 SKU 当原模板 Item No.** |
| `shipping_fee` | 订单原始运费，已确认才填；缺失则发票留白，不假设 Amazon 配送运费为零 |
| `shipping_discount` | 运费促销抵扣（用正数录入，如原始运费 0.75、优惠 -0.75 则填 0.75）；发票 Shipping fee 显示净运费 `shipping_fee - shipping_discount`，本例 `0,00` |
| `order_total` | 已确认的订单实付总额；若未提供，原模板 `Total Amount` **仅展示商品小计**，交付时提醒核对 |
| `tax.amount` | 可选；脚本按 `Price / 1.2 * 0.2` 自动算，若填写值与该口径不符则拒绝 |
| `origin` | 有可靠依据才填 `ORGIN:` 后方，否则保持空白，旧发票 `CHINA` 不是默认事实 |
| `shipping_way` / `fulfillment` | 源订单物流信息可保留在 JSON，但发票 **Shipping way 永远显示 Paypal package** |

所有金额用十进制字符串，例如 `"7.99"`，`items[].unit_price × quantity` 须严格等于 `line_total`。模板金额计算是用户指定业务口径，并非对平台代征 VAT 或法国税务规则的自动核实。真实买家订单和税号不进入公开仓库或插件测试数据。

`--text` 支持解析单商品 Seller Central 中文复制文本，但请人工核对缺损的商品标题、收件姓名和地址。多商品统一使用 `items[]`，按每商品一页保持原表格位置。示例 JSON 见 `../assets/order.example.json`，其中买家为虚构人物。

## 生成文件命名

PDF 文件名固定为完整 Amazon 订单编号：`<order_id>.pdf`（例如虚构样例 `403-1234567-7654321.pdf`）。不得添加前缀、日期、金额或“修正版”等后缀。多商品同订单使用同一 PDF 的多页，不为各商品分别编号。
