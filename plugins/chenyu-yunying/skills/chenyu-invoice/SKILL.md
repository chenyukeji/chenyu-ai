---
name: chenyu-invoice
description: 晨玙 Amazon 商业发票生成。按已确认卖家选择 JiuYue 或 Renhaoyuan 空白 PDF 母版，保留原版式；顶部打印完整公司名称，Renhaoyuan 地址用拼音。配送地址首行统一作为收件人；Item No. 打印订单编号，Description 不得留空；Shipping way 固定 Paypal package；从订单销售渠道识别站点，按用户税率表计算含税 VAT 并同步替换右下角百分比；生成前验证买家和金额，生成后渲染核验。
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

用户明确是 Renhaoyuan、订单含 `Profil vendeur Amazon.fr : Renhaoyuan`，或卖家公司匹配时，直接用 Renhaoyuan 母版，不重复询问已经保存的卖家资料。顶部不能只写店铺名。Renhaoyuan 母版的地址用拼音，电话 `+8613242020247`，邮箱 `renhaoyuanmaoyi@outlook.com`；不打印 Business registration / 注册号。卖家未说明且无法从本单识别时先确认卖家，不能因脚本兼容默认原母版就替用户猜测。新卖家或非 EUR 币种仍需对应已确认母版；税率表内站点的 EUR 订单可沿用所选卖家母版并动态替换 VAT 标签。不要把买家私密资料或带买家信息的发票提交进 GitHub。

浏览器采集的中文卖家地址按 [紧凑拼音格式](references/seller-templates.md#浏览器采集卖家地址后的拼音格式) 转换：街道及门牌拼音小写连写，城市与区小写、省名首字母大写、国家代码大写；数字和字母编号保留原值与大小写，城市、区、省与邮编按已确认发票格式分行；原始中文留作来源核对。已有卖家复用母版已确认写法。

## 生成步骤

1. 只读提取订单：**销售渠道**（如 `Amazon.de`，保存为 `sales_channel`）、订单号、`buyer.name`（本单配送地址第一行，个人或机构名称均可）、买家类型/企业显示名（仅作来源元数据）、街道、楼栋、城市、邮编、商品标题、数量和金额。**`Importer/Buyer/Receiver:` 后仅填 `buyer.name`；`Contact:`、`Company Name:` 标签保留且不填值；`Address:` 仅打印街道/楼栋，不重复收件人姓名**。**所有订单统一把“配送地址”第一行原样作为 `buyer.name`**，无论该行是个人、公司、机构或取件点名称，均直接填写，不再因其不是个人姓名而要求确认。保留首行原有重复词，不擅自去重或改写；后续行再拆分街道/楼栋、城市、邮编与国家，不在地址栏重复首行。不使用“联系买家”的显示名或其他位置的企业买家名称替代配送地址第一行；只有首行缺失、模糊或被截断时才要求补充。
2. 验证 `items[].unit_price × quantity = line_total`；所有金额保留两位小数、法式逗号小数。币种必须是 EUR；Buyer Country 使用本单实际国家，清空或替换母版原值，不假设法国。
3. `Item No.` **使用订单编号**分三行居中，不使用 SKU。`Item Name` 写完整已确认商品标题，衬线粗体居中自动换行；`Description` 写标题中可确认的短品名/规格（优先显式 JSON 的 `description`），不能空着。
4. **发票 `Date:` 必须取 Amazon 订单 `购买日期`**（本地日期，忽略当天生成日期和截止配送日期）；转换为 `DD/MM/YYYY`，没有可核对的购买日期就停止并要求补充。**Shipping way 固定原母版的 `Paypal package`**；Amazon 加急/FBA 来源保留在数据中，不覆盖发票固定文字。
5. **先按销售站点选税率，再计算并打印**：读取截图/复制文本中的“销售渠道”，按下方税率表设置 `r`，计算 `VAT = Price / (1 + r) * r`，四舍五入到两位小数；PDF 右下角同步显示 `VAT(19%*Price):` 等对应百分比。不能只换标签或只换金额。销售渠道不清楚时要求补充；不得根据订单号、收件国家、语言或商品链接猜测，也不得默认 20%。用户提供的税率/税额若与该站点业务口径不符须停止核对；本表不是自动税务核实。
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
- **原模板内的静态卖家信息**必须先由公司确认仍然有效；新卖家、新币种需要对应已清理母版；税率表内的 EUR 订单按本 Skill 动态替换 VAT 标签。收件国家只决定 Country 字段。不要借用旧买家信息。
- 用户指定的 `Paypal package` 是**发票上的固定印刷字段**，不宣称订单真实交由 PayPal 物流配送。
- 私有订单正文、客户姓名、地址和税号只能放在工作成果目录，不得打入可公开安装的 Skill ZIP、GitHub 或测试样例。

## 其他欧盟收件国家与运费促销

对于法国以外的 EUR 订单（如比利时），严格保持原表格结构，只替换 `Country` 原来印刷的 France 字段为实际英文国家名。若订单给出运费及运费优惠，应分别核对原始金额与抵扣，并在固定 `Shipping fee` 一栏打印净运费；`Total Amount` 保持核对后的最终订单金额。销售站点与收件国家分开记录：例如 Amazon.fr 寄往比利时，按用户指定站点规则取 FR 20%，Country 填 Belgium；Amazon.com.be 则取 BE 21%。实际税务适用性仍须独立核实。


## 按订单销售站点匹配 VAT

以下是用户指定的业务税率表；截图由助手读取“销售渠道”后写入 `sales_channel`，脚本负责匹配、计算与打印。单价和总价仍按含税金额处理，`Price` 优先为已确认订单总额，缺失时为已知商品小计。

| 站点/代码 | 销售渠道 | 税率 |
| --- | --- | --- |
| 英国 UK | Amazon.co.uk | 20% |
| 德国 DE | Amazon.de | 19% |
| 法国 FR | Amazon.fr | 20% |
| 意大利 IT | Amazon.it | 22% |
| 西班牙 ES | Amazon.es | 21% |
| 荷兰 NL | Amazon.nl | 21% |
| 波兰 PL | Amazon.pl | 23% |
| 捷克 CZ | 需用户明确确认代码 CZ | 21% |
| 奥地利 AT | 需用户明确确认代码 AT | 20% |
| 比利时 BE | Amazon.com.be | 21% |

- 支持销售渠道域名或完整 URL；比利时使用 `Amazon.com.be`。不编造 CZ/AT 的 Amazon 销售域名。不能看到捷克/奥地利收件地址就推断销售站点。
- 只有订单销售渠道缺失而用户明确确认了站点时，才可用 `marketplace_code` 填上述代码；若同时存在，两者必须一致。未知渠道或冲突会阻止生成。
- 例如含税价 119.00、DE 19% → VAT 19.00，右下角 `VAT(19%*Price):`；含税价 122.00、IT 22% → VAT 22.00。
- 本次增加的是站点税率规则；现有 PDF 母版的货币仍固定为 EUR。GBP、PLN、CZK 等订单需要已确认的对应币种母版，不得把金额直接标成欧元或自行换汇。
