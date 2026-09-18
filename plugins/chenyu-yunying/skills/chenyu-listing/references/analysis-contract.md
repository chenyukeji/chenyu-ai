# 分析脚本接口

相关脚本使用 Python 3.10+ 标准库，无第三方依赖。路径相对当前 Skill 目录；实际执行时解析绝对路径，输入输出使用独立任务目录。不得把真实开发表、竞品快照、图片或生成结果写入插件及 Git。

```bash
python ../chenyu-yunying/scripts/extract_development_brief.py "input.xlsx" --out "task/brief"
python scripts/validate_listing_package.py "task/listing-package.json" --out "task/package-review.json"
python scripts/analyze_listing.py "task/listing-package.json" --out "task/content-review.json"
```

提取器保留原始单元格及公式缓存（缓存可能过期），不执行公式；文字链接、真正超链接、常量 HYPERLINK 均保留来源。动态 HYPERLINK 只警告，需助手根据单元格证据补读。媒体原样导出，图片锚点为1起始行列；附件只清点，WPS单元格图片等不支持的对象发出警告。未知图片不自动归属变体。输出目录须为空。

最终包示例（虚构数据，仅说明接口）：

```json
{
  "targets": ["DE"],
  "variants": [{"id":"V1","marketplaces":["DE"]}],
  "facts": [
    {"id":"F1","source_type":"own_product","status":"confirmed","field":"material","value":"Papier","variant_ids":["V1"],"source":{"sheet":"Product","cell":"B2"}}
  ],
  "competitors": [
    {"id":"C1","marketplace":"DE","product_group":"P1","status":"partial","url":"https://example.com/item","retrieved_at":"2026-01-01","title":"Baumschmuck aus Papier","bullets":[],"description":""}
  ],
  "keywords": [
    {"marketplace":"DE","phrase":"Baumschmuck","aliases":["Baumdeko"],"type":"product","decision":"adopt","fact_source":"自有产品身份"},
    {"marketplace":"DE","phrase":"Papieranhänger","aliases":["Anhänger aus Papier"],"type":"attribute","decision":"adopt","fact_source":"F1"},
    {"marketplace":"DE","phrase":"Weihnachtsdekoration","aliases":["Festdeko"],"type":"scene","decision":"adopt","fact_source":"已确认场景"}
  ],
  "mappings": [
    {"marketplace":"DE","variant_id":"V1","fact_ids":["F1"],"buying_reasons":["Leicht zu platzieren"],"keywords":["Baumschmuck","Papieranhänger","Weihnachtsdekoration"],"listing_fields":["title","bullet_1","bullet_2","bullet_3","bullet_4"]}
  ],
  "listings": [
    {"marketplace":"DE","language":"de-DE","variant_id":"V1","title_keywords":["Baumschmuck","Papieranhänger","Weihnachtsdekoration"],"title_scene":"für Weihnachtsfeiern","title":"Baumschmuck, Papieranhänger und Weihnachtsdekoration für Weihnachtsfeiern","bullets":["📦【Lieferumfang】Der Baumschmuck besteht aus Papier. Der Lieferumfang bezieht sich auf die gewählte Variante.","🧩【Material】Die Papieranhänger sind leicht zu platzieren. Die bestätigten Materialangaben bleiben in allen Feldern einheitlich.","✨【Dekoration】Die Festdeko lässt sich als dekoratives Element einsetzen. Ihre Gestaltung ergänzt verschiedene Arrangements.","🎉【Anlässe】Die Dekoration eignet sich für bestätigte Weihnachtsfeiern. Sie kann mit vorhandener Tisch- oder Raumdeko kombiniert werden.","💡【Hinweis】Verwenden Sie nur die im Paket enthaltenen Teile. Bewahren Sie die Dekoration passend zum bestätigten Material auf."],"description":"概述。\n\nEigenschaften:\n1. Material:说明。\n2. Gestaltung:说明。\n3. Anlass:说明。\n\nProduktdetails:\nMaterial: Papier\n\nLieferumfang:\n1 × Baumschmuck","search_terms":"baumschmuck papieranhaenger festdeko weihnachtsfeiern","claim_fact_ids":["F1"]}
  ],
  "brands": [],
  "limits": {}
}
```

站点仅 DE/FR/IT/ES/UK，status 使用 complete/partial/failed。product_group 由研究证据确定，不由脚本猜测。aliases 必须经过语义判断。brands 填入已知自有与竞品品牌以检查泄漏，不用于生成文案。

facts 只能记录自有产品证据，source_type 固定 own_product；竞品信息只进入 competitors/keywords，不得转成 facts。confirmed 事实可进入买家文案，unconfirmed/conflict 只进入待确认摘要。variants 可用 marketplaces 限定实际销售站点，省略则应用全部 targets。每个应交付的站点/变体必须有 mapping 和 listing；claim_fact_ids 列出该文案使用的已确认事实。每条 listing 的 title_keywords 必须正好引用同站点 keywords 中 3 个不同的主 phrase，title_scene 记录标题采用的主要场景；标题和五点可用该关键词记录中的 aliases，自行猜测的相似词不算覆盖。

limits 默认空：仅在核实规则后填入站点下的 title_chars / search_terms_bytes，并在任务记录保留官方来源、类目和查询日期。脚本报告未核实项，不内置通用限制。

package-review.json 检查目标站点/变体齐全、单行标题、3 个标题关键词及场景、标题/五点的原词或 alias 覆盖、五点数量及默认“Emoji＋【小标题】＋2—3句”格式、四段式描述、Search Terms、事实来源和映射；标题 150—190 字符仅作为编辑警告，不冒充平台限制。ready_for_delivery=false 时不得交付。content-review.json 包含原词/语义组覆盖数、各字段样本分母、证据位置、标题词在各字段采用的具体形式、长度和重复片段。两个检查都不负责语义审核、自动翻译、事实推断或发布；三个标题词是否语义重复、标题自然度、五点职责、品牌候选及8词重合须由模型复核。输出文件已存在时拒绝覆盖。
