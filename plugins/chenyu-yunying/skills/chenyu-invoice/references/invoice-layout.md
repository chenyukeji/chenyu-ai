# PDF 原母版 1:1 版式规范

这不是“参考样式重新画一张发票”。`assets/blank-reference-template.pdf` 是用户提供的原始 WPS 商业发票经过**清理旧订单数据**得到的可复用 PDF 母版。母版保留原始 WPS 输出中的公司抬头、字体、灰色横条、右侧联系方式、买卖方字段标签、灰色七列表头、七列格线、两条底部边线和固定文案。已清理旧买家、旧订单号、旧商品、旧金额、旧税额、旧城市和旧邮编；**不提供旧买家发票原件**。

## 版式必须原样保留

- 纸张：A4，595.3 × 841.9 pt，页边距和上下留白均使用 PDF 母版原位置。
- 抬头：居中 `shenzhenshijiuyuekejiyouxiangongsi`，左侧地址、电话、`COMMERCIAL INVOICE` 原样保留；不得替换为统一新字体。
- 左栏：`Importer/Buyer/Receiver:` **仅填收件人姓名**（如虚构样例 Camille EXEMPLE），不填企业买家显示名；`Contact:` 和 `Company Name:` **标签不删除，但值留空**；`Address:` 仅填写街道与楼栋，不重复姓名；其余标签 `City:`、`Country:`、`Post code:`、`Tel:`、`Remote area:`、`Shipping way`、`Tracking number:` 的位置不变。
- 右栏：`Manufacturer/Seller/Shipper:`、`Sales:`、原卖家公司地址、`VAT number:`、`Date:` 均使用原位置；卖家公司和电话是固定模板信息，卖家主体若发生变化必须换母版，不能默默套用。
- **Shipping way 固定为 `Paypal package`**，本值已经印在原母版上，不因 Amazon FBA / 加急改变。
- **表格的列宽、边框、灰色表头、留白都从原母版读取，不重新绘制。** `Item No.` 使用 Amazon 订单号分三行居中，**不是 SKU**；`Item Name` 用约 12pt Times 粗体居中自动换行，`Description` 用粗体居中短商品名且不得默认空白；单价、数量和行金额用 12pt 衬线字体居中。长标题必要时小幅缩小字号，不可截断和溢出。
- 页尾：保留原样的 `Shipping fee:`、`Total Amount:`、`VAT(20%*Price):`，底部 `TRADIN` / `G TERM:` / `ORGIN:` 以及横线。不要加原模板没有的 `Items subtotal:` 行或页脚装饰。
- 原模板 `Total Amount` 缺少订单实付总额时显示**已知商品小计**，并在交付说明提示这不是已核实的最终支付额；不能编造运费。已提供真正 `order_total` 时显示已确认的总额。
- VAT 只按含税口径 `Price / 1.2 * 0.2` 计算；价款 €373,66 → VAT €62,28；价款 €7,99 → VAT €1,33，保留原标签 `VAT(20%*Price):`。这只是用户要求的固定业务计算规则，实际税务适用性须人工确认。
- **VAT 同行对齐**：原母版 `VAT(20%*Price):`、欧元符号 `€` 的文字基线均为 PDF y=`664.13 pt`；新金额必须以 x=`506.4 pt`、y=`664.13 pt`、Arial 近似 Helvetica `9.95 pt` 绘制，金额紧跟 `€`，不得使用 Courier 字体产生松散字距，也不得使用 `666.0 pt` 的下沉基线。验收时以 PDF 文字 span 的 `origin.y` 差小于 `0.2 pt` 为准。
- 未确认的买家税号、运费、原产国、Tracking 和 Remote area 保持空白。**不能复制旧发票中的 `CHINA` 或 `No` 作为新订单事实**。

## 几何参数（PDF 左上角原点，单位 pt）

| 元素 | 原 PDF 固定位置 |
| --- | --- |
| 七列分界 x | `9.9, 65.3, 122.3, 288.8, 381.9, 460.55, 507.05, 558.9` |
| 灰色表头 | y≈458.1—494.8 |
| 商品行 | y≈500.8—610.5，不能移动 |
| 收件人姓名 | `Importer/Buyer/Receiver` 值 x≈157；Contact 和 Company Name 不填值 |
| 买家地址 | x≈106.9。第 1 行街道、第 2 行楼栋（两行 baseline 314.0 / 329.5）；三行时字号约 9.55pt，baseline 308.4 / 319.3 / 330.2，不得压到 City 内容 |
| Total Amount / VAT | 原 PDF 标签保持不动，仅替换右侧数值 |

## 页面和异常

- 仅针对**法国站 EUR** 与此卖家原母版；其他站点/币种需要用户提供对应样式母版，不能假装“完全匹配”。
- 一页一个商品项；多商品复制原母版到第二页，不压缩行高。合计与 VAT 只在最后一页出现。
- 卖家主体不符、国家名或地址无法在固定栏中排下、超长标题最小字号仍超出时，停止并说明需要扩展模板；不偷偷删字。
- 生成后渲染 A4 图像，逐项检查 PDF 原母版灰色表头及边线、收件人、地址、`Item No.`、`Item Name`、`Description`、单价、数量、合计与 VAT，所有新内容均可选择复制。

## 跨国订单与运费促销

- `Country` 原母版静态打印 France：若订单实际为 Belgium 等非法国地址，必须先仅擦除 France 值，再以相同位置/字号打印实际英文国名，不可出现两国叠字。
- `shipping_fee` 与 `shipping_discount` 均记录原值；固定表格的 `Shipping fee` 单行展示净运费，金额 `shipping_fee - shipping_discount`，无运费时留空，不能把促销抵扣再当成额外收入。
- 原模板的 `VAT(20%*Price)` 保留用户指定的含税计算口径，但是否适用于 Belgium 等跨境订单必须与 Amazon 税务记录核实，不把模板口径宣传为法定正确税率。

## 日期填写规范

`Date:` 为订单购买日期（`purchase_date`），统一写 `DD/MM/YYYY`；不能用 PDF 创建日期、Amazon 配送截至日期或模板中的旧日期。购买日期缺失时停止并请求真实订单日期，不猜测。
