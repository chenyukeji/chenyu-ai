# 照片物流表 JSON

表头顺序：箱号/箱唛、箱重（kg）、长（cm）、宽（cm）、高（cm），再按参考截图顺序排列产品英文品名、中文品名、申报单价、申报数量、材质、海关编码、用途、品牌、型号、销售链接、销售价格、产品图片。商品必填标记保留在表头，资料不全也生成核对表。

```json
{
  "cartons": [{
    "cartonId": null,
    "sourcePhotos": ["箱唛照片.jpg"],
    "sourceDocuments": ["本次已确认的内容表截图.png"],
    "weightKg": null,
    "dimensionsCm": [null, null, null],
    "notes": ["照片数字的单位待核"],
    "items": [{
      "rawText": "箱唛上的商品原文及变体与数量",
      "nameZh": "识别的商品名及变体",
      "nameEn": null,
      "quantity": 12,
      "declaredUnitPrice": null,
      "material": null,
      "hsCode": null,
      "purpose": null,
      "brand": null,
      "model": null,
      "salesUrl": null,
      "salePrice": null,
      "imagePath": null,
      "msku": null,
      "evidence": "照片及核对资料的出处",
      "notes": []
    }]
  }]
}
```

- 每箱一个对象；cartonId 可用本次真实箱标识，缺失由脚本生成临时编号；不同箱须唯一。
- quantity 是该箱该申报行的件数，正整数。默认保留变体；本次有明确合并依据时，添加 `sourceItems: [{"name":"装备A","quantity":12},{"name":"装备B","quantity":6}]`，`quantity: 18`，以及 `consolidationEvidence` 记录确认来源。脚本强制校验加总，并将明细写入识别依据。
- 重量、尺寸和价格须为正数；缺失填 null，不用 0、待确认等字符串。hsCode 为字符串以保留前导零。
- notes 为字符串数组。sourcePhotos 为实际箱唛照片文件名数组；sourceDocuments 为本次已确认资料文件名数组，不把它们当作单纯格式样例。rawText 保留原文；evidence 记录补充资料来源、英文翻译或核对结果。
- imagePath 仅接受已核对的本品本地图片路径；可先从本次商品资料提取。已确认同货件截图中的对应商品缩略图也可原样裁取并注明来源；未找到则 null，不拿箱唛整图填充。
- 币种由本次资料确认；提供价格时在 evidence 记录数值来源；已确认资料有价格但未注明币种时保留价格，在 notes 单列币种待核。表格不默认为 USD。
- 脚本自动列出每一行空缺字段；额外歧义用 notes 补充。「待补信息」和「识别依据」都保留在同一个工作簿中。
