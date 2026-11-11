# 输入字段与填写规则

| JSON 字段 | 规则 |
| --- | --- |
| `order_id` | 必填，Amazon 订单号 `000-0000000-0000000`；打印在 `Item No.` 列，分三行居中 |
| `purchase_date` | **必填**，Amazon 订单购买日期，`YYYY-MM-DD`；打印到 `Date:`，格式 `DD/MM/YYYY`。不得使用配送截至日期或生成 PDF 的当天日期 |
| `invoice_date` | 不接受此 JSON 字段；可选命令行 `--invoice-date` 仅用于核对，必须等于 `purchase_date` |
| `sales_channel` | 从本单“销售渠道”读取，如 `Amazon.de`；作为订单来源核对，不决定税率，不从商品链接或收件国推断 |
| `marketplace_code` | 销售渠道缺失时，仅可用用户明确确认的 UK/DE/FR/IT/ES/NL/PL/CZ/AT/BE；与 sales_channel 同时给出必须一致 |
| `currency` | 必填实际币种；支持 EUR 与 PLN，默认按原币生成并自动匹配模板文字，不能默认 EUR 或自行换汇 |
| `template_currency` | 可选兼容字段，不是审批字段；通常省略。若提供须与 `currency` 完全一致，否则报冲突，不换算金额 |
| `billing_request` | 同订单买家明确开票留言，含 `order_id` 与完整 `buyer`；先核对订单号，优先于配送资料，不能混用字段。缺项/不匹配时停止，不退回配送地址 |
| `buyer.vat_number` | 已提供的买方税号，在买方栏单独标为 Buyer VAT/NIP；不是卖方 VAT。留言资料放在 `billing_request.buyer` 同名字段 |
| `buyer.company` | 原 Amazon 订单企业买家显示名（如虚构样例 Entreprise Exemple），仅保留为来源元数据；不替代配送地址第一行。若同名出现在配送地址第一行，则按首行规则填写 buyer.name |
| `buyer.name` | 有同单开票留言时用 `billing_request.buyer.name` 的完整公司/个人抬头；否则取配送地址第一行原文。填写到 **`Importer/Buyer/Receiver:` 后**，不改用联系买家显示名，不改写重复词 |
| `buyer.legal_company_name` | 本母版的 `Company Name:` **标签保留、值固定留空**；不把 `buyer.company` 或收件人重复写到这一行 |
| `buyer.address_lines` | **仅街道和楼栋**，不包含收件人、城市和邮编；不重复姓名；最多三行，溢出则提示，不裁剪 |
| `buyer.city`, `buyer.postal_code`, `buyer.country` | 目标城市、邮编、国家。法国时沿用原模板 France；比利时等其他国家仅替换国家值，不改原版布局 |
| `buyer.tax_region` | 葡萄牙配送税区：`mainland` / `madeira` / `azores`；可由有效七位配送邮编识别。地区与邮编矛盾、或均无法识别时停止核对。不能填账单地址地区 |
| `price_tax_basis` | `inclusive`（默认，原金额含税）、`exclusive`（已确认原金额未税）或 `both`（来源同时给出含税、未税金额）；both 的商品、费用及 order_total 统一用含税口径，原未税合计另存 displayed_amounts.net |
| `tax_basis_evidence` | `exclusive` 和 `both` 必填来源说明，记录截图字段或用户明确确认；不得单凭两栏同额或 Business Price 标签猜测 |
| `displayed_amounts` | `both` 必填对象，`gross`、`net` 为来源中同范围的含税／未税合计（十进制字符串）；与实际收货地税率核对，VAT 取两者差额。禁止在其他税基下忽略这组证据；不能把平台结算净收益当未税金额 |
| `gross_amount` | 脚本生成的含税开票总额；含税来源保留原金额，未税来源为原未税金额加已四舍五入 VAT；both 保留 displayed_amounts.gross |
| `net_amount` | 脚本生成的未税金额；含税来源为含税总额减 VAT，未税来源保留原金额，both 保留 displayed_amounts.net，展示在总额与税额之间 |
| `buyer.remote_area` | 仅确认偏远区时填布尔值 `true/false`，否则留空，不沿用旧单 No |
| `buyer.tel` / `tracking_number` | 可选，未经确认留空 |
| `seller_template` / `--template` | `jiuyue`、`renhaoyuan` 或已确认自有卖家的 `imported`；与身份和其他选择须一致 |
| `seller_confirmed` | 自有卖家须为布尔 `true`，依据用户确认或已保存核对快照填写，不能编造批准。`seller.company`、`seller.address_lines` 必填；可选电话、邮箱缺失留空，不继承其他公司 |
| `seller` / 独立 `--seller` JSON | company/store_name/sales_name 可识别已保存的卖家；抬头、地址和联系方式来自匹配母版，可选填已核实 seller.vat_number；登记号不能当税号 |
| `items[]` | 每项 `title`、`quantity`、`unit_price`、`line_total` 必填；`description` 推荐填写，若无则从标题中提取确实出现的产品词，不可空着整列 |
| `items[].net_line_total` | 双金额来源逐项记录可见未税行金额；有一项提供则每项都须提供。按行核对后相加保留逐行舍入结果，例如两行各含税 9.99／未税 8.39，应保留含税 19.98／未税 16.78／VAT 3.20；不得整体重算成未税 16.79 |
| `displayed_amounts.net_shipping` | 逐项双金额并有非零净运费时必填可见未税运费，须与含税净运费对应；未税商品合计加本字段须等于 displayed_amounts.net，不重复加费用 |
| `items[].sku`, `items[].asin` | 只作来源校验；**不要把 SKU 当原模板 Item No.** |
| `shipping_fee` | 订单原始运费，已确认才填；缺失则发票留白，不假设 Amazon 配送运费为零 |
| `shipping_discount` | 运费促销抵扣（用正数录入，如原始运费 0.75、优惠 -0.75 则填 0.75）；发票 Shipping fee 显示净运费 `shipping_fee - shipping_discount`，本例 `0,00` |
| `order_total` | 本次开票金额；both 必须等于 displayed_amounts.gross，其他情形默认直接读单商品订单右侧“商品总计 / Item total”；多商品逐项汇总并核对费用。用户明确额外要求优先，记录依据，不取销售净收益；未税来源按已确认未税单价与数量汇总，原 order_total 保持来源值，含税开票总额另存 gross_amount |
| `amount_source` | 双金额来源填 `displayed_gross_and_net`；默认金额来自可见商品总计时填 `displayed_item_total`，无需另要实付确认；只有确实未见总计才保留小计来源说明 |
| `tax.amount` | 可选；脚本按实际收货国家／地区税率 `r`，含税来源用 `Price / (1 + r) * r`，未税来源用 `Price * r`，双金额来源用 `gross - net` 自动算，若填写值与该口径不符则拒绝 |
| `tax.rate` | 可选，十进制比例（如 `"0.19"`）；必须与实际收货国家／地区税率表一致，不能用于覆盖配送规则 |
| `origin` | 有可靠依据才填 `ORGIN:` 后方，否则保持空白，旧发票 `CHINA` 不是默认事实 |
| `shipping_way` / `fulfillment` | 源订单物流信息可保留在 JSON，但发票 **Shipping way 永远显示 Paypal package** |

所有金额用十进制字符串，例如 `"7.99"`，`items[].unit_price × quantity` 须严格等于 `line_total`。模板金额计算是用户指定业务口径，并非对平台代征 VAT 或法国税务规则的自动核实。真实买家订单和税号不进入公开仓库或插件测试数据。

`--text` 支持解析单商品 Seller Central 中文复制文本，但请人工核对缺损的商品标题、收件姓名和地址。已确认企业订单页面的中英文含税／未税双金额截图必须用结构化 JSON，`--text` 拒绝处理以免丢失税基；同图含税 9.99、未税 8.39 对应 VAT 1.60，不能反算成 9.98。多商品统一使用 `items[]`，两种商品同页保留原列宽与行高，超过两行才分页。示例 JSON 见 `../assets/order.example.json`，其中买家为虚构人物。

## 生成文件命名

PDF 文件名固定为完整 Amazon 订单编号：`<order_id>.pdf`（例如虚构样例 `403-1234567-7654321.pdf`）。不得添加前缀、日期、金额或“修正版”等后缀。多商品同订单使用同一 PDF 的多页，不为各商品分别编号。

税率始终读取原始 `buyer` 配送国家／地区，`billing_request.buyer` 只决定打印抬头和地址。存在开票留言时，至少保留原始 `buyer.country`，葡萄牙还需配送邮编或 `buyer.tax_region`；不能用开票国家、站点或商品链接代替。归一化结果 `tax.destination_country`、`tax.destination_region`、`tax.rate_source` 记录税率来源。

## 退款字段

`document_type` 为 `invoice`（默认销售）或 `refund`。退款必填 `refund_evidence`，记录已退款状态及实际退款金额依据；金额字段可输入正数金额或负数，脚本以退款负金额输出。`items[].quantity` 始终为正整数。`order_total` 必须是实际退款合计，与退款商品及净退款运费一致。部分退款不能沿用原订单总额。`refund_source_amounts` 是脚本保留的原金额记录，仅用于内部溯源。其他金额、币种和税基字段沿用上表。

企业订单英文页面：`Business customer` + 商品行 `Unit price` + `Proceeds` 内 `Item subtotal` / `Item total` 对应已确认中文模式。完整核对后使用 `both`，含税单价乘数量填 `line_total`，未税商品金额单独填 `net_line_total`；不能把含税单价与未税行金额混在一行导致数量校验失败。界面语言变化不构成待补资料。
