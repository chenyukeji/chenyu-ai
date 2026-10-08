# 箱唛到发货发票的字段规则

## 输入 JSON

`carrier` 为 `lianhang` 或 `yiluda`。`shipment` 是本次发货资料，`cartons` 是照片识别并人工/领星核对后的箱列表。每箱一个唯一 `cartonNo`，正数 `weightKg`、三个正数的 `dimensionsCm`（单位 cm），以及至少一个 `items`。每款商品的 `quantity` 是**该箱数量**；同箱多款商品不重复写箱重和尺寸。

```json
{
  "carrier": "yiluda",
  "shipment": {
    "customerOrderNo": "本次订单号",
    "service": "本次确认的渠道",
    "addressCode": "FBA仓库地址编码",
    "recipient": { "postalCode": "本次仓库邮编，可用于交叉核对", "countryCode": "FR" },
    "taxMode": "包税",
    "declarationMode": "买单报关",
    "customsMode": "快件清关",
    "currency": "USD",
    "insurance": false,
    "flags": {
      "battery": false,
      "magnet": false,
      "liquid": false,
      "powder": false,
      "dangerous": false,
      "wood": false,
      "textile": false
    }
  },
  "cartons": [{
    "cartonNo": "本次FBA箱号",
    "weightKg": 12.5,
    "dimensionsCm": [58, 36, 36],
    "items": [{
      "msku": "领星匹配的MSKU",
      "nameZh": "中文品名",
      "nameEn": "英文品名",
      "quantity": 49,
      "declaredUnitPrice": 2,
      "material": "已核实材质",
      "hsCode": "已确认海关编码",
      "purpose": "用途",
      "brand": "品牌或无",
      "model": "型号或无",
      "salesUrl": "稳定商品页面链接",
      "imageUrl": "稳定且可访问的图片链接"
    }]
  }]
}
```

额外的可选字段：`shipment.poNumber`、`shipment.remarks`、`shipment.storeUrl`、`shipment.vatNo`、`shipment.eoriNo`、`shipment.insuredAmount`、`shipment.sender`（联航发件人资料）；商品 `sku`、`asin`、`fnsku`、`brandType`、`salePrice`、`productWeightKg`。驿路达的 `insurance` 是必需布尔值；联航若填写保险也须明确是或否。可选项若无可信来源则留空，不用旧订单值填充。

## 来源优先级与匹配

| 发票字段 | 首选来源 | 不可做的替代 |
| --- | --- | --- |
| 每箱件数、箱重、尺寸 | 对应箱唛照片及人工复核 | 不能从领星产品单重估算箱重 |
| FBA 箱号、仓库地址、渠道 | 本次货件/用户确认 | 不能沿用历史发票中的箱号和 XCD2/CDG7 |
| 品名、SKU/MSKU、材质、销售链接、图片 | 领星对应的同一商品/变体 | 不能只靠同名猜变体，不能取其他商品图片 |
| 申报单价、HS 编码、危险品等声明 | 本次发货资料或领星中明确维护且经确认的字段 | 采购价、售价、材料自动推算均不算确认 |

如果领星图片只有需要登录的缩略图或短时效地址，不把临时链接填入承运商表。可询问用户提供稳定的商品图链接；图片列本身不是这两类模板的星号必填列。销售链接同理：应取对应商品的稳定上架链接，未找到时保留空白并报告。

## 承运商映射

联航第 18 行表头，A:U：货箱编号、箱重、长、宽、高、英文品名、中文品名、申报单价、单箱数量、材质、HS 编码、用途、品牌、型号、销售链接、销售价格、图片链接、产品重量、ASIN、FNSKU、SKU。顶部用 A/B、E/F、I/J 三组标签和值。

驿路达第 17 行表头，A:S：货箱编号、箱数、箱重、长、宽、高、中文品名、英文品名、申报单价、单箱数量、材质、HS 编码、用途、品牌、品牌类型、型号、销售链接、图片链接、PO Number。顶部用 A/B、E/F 两组标签和值。

两种原模板的地址信息都由 `B3` 地址库编码通过已有公式自动带出；生成器不覆盖公式，也不新增公式。件数与重量、尺寸保持数值类型，FBA 箱号及邮编保持文本。海关编码也保持文本，防止前导零丢失。联航只使用原模板第 19–51 行，驿路达只使用第 18–45 行；超过已格式化行数时停止，不擅自插入行或延展样式。

## 生成前阻断

- 承运商、渠道、FBA 箱号、仓库地址缺失；同箱照片与箱号不能一一对应。
- 手写品名或数量、重量、尺寸无法辨认，或一款商品匹配多个领星变体而无确定 SKU/MSKU。
- 申报单价、材质、HS 编码或承运商星号必填字段缺失；禁限运声明未确认。
- 数量不是正整数、重量/尺寸不是正数，或箱号重复。
- 同一照片和领星档案互相矛盾，尚未由用户确认取值。

报错时按箱号、商品与字段列出待补项。不为凑齐模板而插入看似合理的默认值。
