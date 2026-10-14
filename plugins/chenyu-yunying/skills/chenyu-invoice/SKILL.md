---
name: chenyu-invoice
description: 晨玙 Amazon 法国站商业发票生成。按已确认卖家选择 JiuYue 或 Renhaoyuan 空白 PDF 母版，保留原版式；顶部打印完整公司名称，Renhaoyuan 地址用拼音。Item No. 打印订单编号，Description 不得留空；Shipping way 固定 Paypal package；VAT 按含税价格 ÷ 1.2 × 0.2；生成前验证买家和金额，生成后渲染核验。
---

# 晨玙发票生成 `chenyu-invoice`

**核心要求：必须与原始 PDF 母版保持一致，不要重新设计。** 本 Skill 有经过清理、不含原订单客户及金额的实际 WPS PDF 母版 `assets/blank-reference-template.pdf`，脚本直接在其固定位填入新订单数据。禁止换用新 ReportLab 表格，禁止改变原始灰色表头、字号、列宽、边框、行高、页边距、底部总计和原有标签。读取并执行 [原母版 1:1 版式规范](references/invoice-layout.md)。

开始执行会生成文件的任务前，先读取并遵循 [运营插件输出目录规范](../../references/output-paths.md)。

## 输入

订单可以是 Seller Central 的复制文本、截图、PDF 或人工核对后的 JSON；截图/PDF 由当前助手按所见读取，复杂订单整理成 JSON。订单号、收件人姓名、地址、商品标题、数量、单价和金额必须来自本单，不能沿用参考发票的旧买家、旧产品。填写规则见 [订单字段](references/order-fields.md)。

**卖家身份必须与对应母版一致**。已保存两个不含订单买家的母版，详见 [卖家母版选择](references/seller-templates.md) 与 `assets/seller-templates.json`：

| 母版标识 | 顶部完整公司名称 | Sales / 卖家显示名 |
| --- | --- | --- |
| `jiuyue`（原母版） | `shenzhenshijiuyuekejiyouxiangongsi` | `JiuYue_KeJi` |
| `renhaoyuan` | `shenzhenshirenhaoyuanmaoyiyouxiangongsi` | `Renhaoyuan` |

用户明确是 Renhaoyuan、订单含 `Profil vendeur Amazon.fr : Renhaoyuan`，或卖家公司匹配时，直接用 Renhaoyuan 母版，不重复询问已经保存的卖家资料。顶部不能只写店铺名。Renhaoyuan 母版的地址用拼音，电话 `+8613242020247`，邮箱 `renhaoyuanmaoyi@outlook.com`；不打印 Business registration / 注册号。卖家未说明且无法从本单识别时先确认卖家，不能因脚本兼容默认原母版就替用户猜测。新卖家、新站点或币种仍需对应已确认母版。不要把买家私密资料或带买家信息的发票提交进 GitHub。

## 生成步骤

1. 只读提取订单：订单号、`buyer.name`（收件人，如虚构样例 Camille EXEMPLE）、买家类型/企业显示名（仅作来源元数据）、街道、楼栋、城市、邮编、商品标题、数量和金额。**`Importer/Buyer/Receiver:` 后仅填 `buyer.name`；`Contact:`、`Company Name:` 标签保留且不填值；`Address:` 仅打印街道/楼栋，不重复收件人姓名**。地址首行只有取件柜/机构名称时，不编造个人姓名；用户明确要求将该首行当作姓名则按本单指示填入 `buyer.name`，并从地址栏移除重复首行。这不是其他订单的通用姓名规则。
2. 验证 `items[].unit_price × quantity = line_total`；所有金额保留两位小数、法式逗号小数。币种必须是 EUR；Buyer Country 使用本单实际国家，清空或替换母版原值，不假设法国。
3. `Item No.` **使用订单编号**分三行居中，不使用 SKU。`Item Name` 写完整已确认商品标题，衬线粗体居中自动换行；`Description` 写标题中可确认的短品名/规格（优先显式 JSON 的 `description`），不能空着。
4. **发票 `Date:` 必须取 Amazon 订单 `购买日期`**（本地日期，忽略当天生成日期和截止配送日期）；转换为 `DD/MM/YYYY`，没有可核对的购买日期就停止并要求补充。**Shipping way 固定原母版的 `Paypal package`**；Amazon 加急/FBA 来源保留在数据中，不覆盖发票固定文字。
5. **VAT 固定用含税价公式** `VAT = Price / 1.2 * 0.2`，保留两位小数，保留原标签 `VAT(20%*Price):`。`€373.66 → €62.28`；`€7.99 → €1.33`。用户提供 VAT 若与此业务口径不符须停止。该值不等于已经税务核实。
6. `Total Amount:` 优先打印已确认的 `order_total`；如未提供，为满足原表格会显示**已知商品小计**，交付时明确这不是已核实的订单最终实付。未知 `Shipping fee`、`ORGIN`、Tracking、Remote area、VAT number 留空；不默认填零、China 或 No。
7. 用 `scripts/generate_invoice.py` 加载真正空白原母版并覆盖新订单数据，不允许重新绘制原模板。单商品严格占用原一行 110pt 单元格；多商品为保留布局可复制原母版分页。
8. **必须渲染检查**：文字不能重叠、删减或溢出；七列边框/灰色表头要与原图一致，特别检查 `Description`、订单编号而非 SKU、价格/数量和页尾合计。若不能排下，停止并请求更大母版，不悄悄缩为极小字号。
9. **PDF 文件名必须严格等于 Amazon 订单编号**，例如虚构样例 `403-1234567-7654321.pdf`；不加 `Facture`、日期、金额或任何版本后缀。交付生成的实际 PDF、可复用 Skill（如被要求）、待核实事实。只生成文件，不登录、不上传 Seller Central、不联系买家、不修改订单。

## 快速执行

输入 JSON 必须包含 `purchase_date`（例如 `2026-10-01`），否则不得生成。可选 `--invoice-date` 仅作为与购买日期一致性的人工复核参数，不能覆盖购买日期。

Python 3.10+，依赖 `pymupdf>=1.25,<2`（无需外部字体或其他模板文件）：

```bash
python -m pip install -r scripts/requirements.txt

# 已核对的单/多商品订单 JSON
python scripts/generate_invoice.py \
  --input /path/to/order.json \
  --output /path/to/output-directory/

# Renhaoyuan：也可在 JSON 使用 seller_template，或提供匹配 seller.company/store_name
python scripts/generate_invoice.py \
  --input /path/to/order.json \
  --template renhaoyuan \
  --output /path/to/output-directory/

# 原始 Amazon Seller Central 中文复制文本（仅支持单商品）
python scripts/generate_invoice.py \
  --text /path/to/amazon-order.txt \
  --seller /path/to/private-seller.json \
  --output /path/to/output-directory/

# 核对生成器、版式、VAT、配送字段和长标题分页
python scripts/test_invoice.py
```

按卖家从 `assets/blank-reference-template.pdf` 或 `assets/blank-renhaoyuan-template.pdf` 读取空白母版；缺少匹配母版则报错，**不得退回原卖家母版或自动重画**。`--template`、JSON `seller_template` 和卖家身份冲突时停止。默认保存到 `outputs/chenyu-yunying/commercial-invoice/<YYYY-MM-DD_订单编号>/`；`--output` 只接受目录，最终文件名为 `<订单编号>.pdf`。

## 风险边界

- 本 Skill 只是用户指定格式的发票文件生成，不替代 Amazon 正式税务发票、平台开票服务和法国/欧盟税务合规审查。税率、平台代征、法定主体、买方税号与运费等须独立核验。
- **原模板内的静态卖家信息**必须先由公司确认仍然有效；新卖家、新销售站点、新币种需要新的已清理母版。其他 EUR 收件国家只能按本 Skill 的国家栏替换规则处理。不要借用旧买家信息。
- 用户指定的 `Paypal package` 是**发票上的固定印刷字段**，不宣称订单真实交由 PayPal 物流配送。
- 私有订单正文、客户姓名、地址和税号只能放在工作成果目录，不得打入可公开安装的 Skill ZIP、GitHub 或测试样例。

## 其他欧盟收件国家与运费促销

对于法国以外的 EUR 订单（如比利时），严格保持原表格结构，只替换 `Country` 原来印刷的 France 字段为实际英文国家名。若订单给出运费及运费优惠，应分别核对原始金额与抵扣，并在固定 `Shipping fee` 一栏打印净运费；`Total Amount` 保持核对后的最终订单金额。比利时等跨境订单的实际 VAT 适用税率仍需税务核实，20% 公式只代表用户要求的模板计算。
