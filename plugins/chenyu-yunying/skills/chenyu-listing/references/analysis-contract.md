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
    {"marketplace":"DE","phrase":"Baumschmuck","aliases":["Baumdeko"],"type":"product","is_core":true,"decision":"adopt","fact_source":"自有产品身份"},
    {"marketplace":"DE","phrase":"Papieranhänger","aliases":["Anhänger aus Papier"],"type":"attribute","is_core":true,"decision":"adopt","fact_source":"F1"},
    {"marketplace":"DE","phrase":"Weihnachtsdekoration","aliases":["Festdeko"],"type":"scene","is_core":true,"decision":"adopt","fact_source":"已确认场景"},
    {"marketplace":"DE","phrase":"Weihnachtsanhänger","aliases":[],"type":"secondary","is_core":false,"decision":"adopt","fact_source":"竞品字段证据"}
  ],
  "mappings": [
    {"marketplace":"DE","variant_id":"V1","fact_ids":["F1"],"buying_reasons":["Lieferumfang klar","Papiermaterial bestätigt","leicht in Arrangements integrierbar","für festliche Dekoration","sachgerechte Aufbewahrung"],"keywords":["Baumschmuck","Papieranhänger","Weihnachtsdekoration"],"listing_fields":["title","bullet_1","bullet_2","bullet_3","bullet_4","bullet_5","description"]}
  ],
  "listings": [
    {
      "marketplace":"DE",
      "language":"de-DE",
      "variant_id":"V1",
      "title_keywords":["Baumschmuck","Papieranhänger","Weihnachtsdekoration"],
      "title_scene":"für Weihnachtsfeiern",
      "title_quantity":1,
      "title_quantity_term":"",
      "color_mode":"not_applicable",
      "title_color_terms":[],
      "title":"Baumschmuck, Papieranhänger und Weihnachtsdekoration für Weihnachtsfeiern",
      "bullets":[
        "📦【Klarer Lieferumfang】Der Lieferumfang ist auf die gewählte Variante abgestimmt und nennt die enthaltenen Dekorationsteile eindeutig. So lässt sich die geplante Anordnung vor dem Dekorieren besser einschätzen, während zusätzlich abgebildete Szenenartikel nicht mit dem Inhalt verwechselt werden.",
        "🧩【Bestätigtes Papiermaterial】Die Dekoration besteht aus Papier und lässt sich dadurch gut in vorhandene saisonale Arrangements integrieren. Materialangaben bleiben in Titel, Beschreibung und Produktdetails einheitlich, ohne daraus unbestätigte Eigenschaften wie Wasserfestigkeit oder besondere Haltbarkeit abzuleiten.",
        "✨【Flexibel kombinierbar】Die einzelnen Dekorationselemente können als ruhiger Akzent verwendet oder mit bereits vorhandener Tisch- und Raumdekoration kombiniert werden. Dadurch entsteht eine zusammenhängende Gestaltung, ohne dass zusätzliche, nicht enthaltene Accessoires als Bestandteil des Sets dargestellt werden.",
        "🎉【Für festliche Arrangements】Die Gestaltung eignet sich für bestätigte Weihnachtsfeiern und saisonale Innenraumdekorationen. Sie kann je nach Platzangebot auf geeigneten Flächen arrangiert werden und ergänzt unterschiedliche festliche Stilrichtungen, ohne einen bestimmten Aufbau vorzuschreiben.",
        "💡【Sachgerechter Umgang】Verwenden Sie ausschließlich die im Lieferumfang genannten Teile und behandeln Sie die Papieroberfläche entsprechend dem bestätigten Material. Lagern Sie die Dekoration trocken und geschützt, damit Form und Erscheinungsbild zwischen den Einsätzen erhalten bleiben."
      ],
      "description":"<p>Diese Papierdekoration verbindet eine klar erkennbare festliche Gestaltung mit flexiblen Möglichkeiten für vorhandene Arrangements. Sie kann als einzelner Akzent oder zusammen mit passender Tisch- und Raumdekoration eingesetzt werden, ohne zusätzlich gezeigte Szenenartikel als Lieferumfang darzustellen.</p><p><b>Eigenschaften:</b><br>1. Bestätigtes Material: Die Dekoration besteht aus Papier; weitergehende Materialeigenschaften werden nicht vorausgesetzt.<br>2. Flexible Gestaltung: Die Elemente lassen sich je nach verfügbarem Platz einzeln oder zusammen anordnen.<br>3. Festlicher Einsatz: Die Gestaltung unterstützt Weihnachtsfeiern und andere bestätigte saisonale Innenszenen.</p><p><b>Produktdetails:</b><br>Material: Papier</p><p><b>Lieferumfang:</b><br>1 × Baumschmuck</p>",
      "search_terms":"baumschmuck papieranhaenger festdeko weihnachtsfeiern",
      "claim_fact_ids":["F1"]
    }
  ],
  "brands": [],
  "limits": {}
}
```

站点仅 DE/FR/IT/ES/UK，status 使用 complete/partial/failed。product_group 由研究证据确定，不由脚本猜测。aliases 必须经过语义判断。brands 填入已知自有与竞品品牌以检查泄漏，不用于生成文案。

facts 只能记录自有产品证据，source_type 固定 own_product；竞品信息只进入 competitors/keywords，不得转成 facts。confirmed 事实可进入买家文案，unconfirmed/conflict 只进入待确认摘要。variants 可用 marketplaces 限定实际销售站点，省略则应用全部 targets。每个应交付的站点/变体必须有 mapping 和 listing；claim_fact_ids 列出该文案使用的已确认事实。

每条 listing 的 `title_keywords` 必须正好引用同站点 keywords 中 3 个不同且 `is_core:true` 的主 phrase，`title_scene` 记录标题采用的主要场景。`title_quantity` 是已确认的实际售卖件数，必须是正整数：等于 1 时 `title_quantity_term` 必须为空且标题不写数量；大于 1 时必须提供本地化 `title_quantity_term`，并让它紧贴在第一个核心关键词或其 alias 正前方。数量短语不能写入 `title_keywords`，开发表中的采购数量不能用于该字段。`color_mode` 使用 `single`、`multi` 或 `not_applicable`；单色可在 `title_color_terms` 声明至多一个标题颜色，多色和不适用时必须为空。标题可使用关键词的 aliases，自行猜测的相似词不算覆盖。关键词表中未用于标题且 `decision` 不是 exclude 的词是五点、详情和 Search Terms 的候选；优先分散覆盖，但不能为了“一点一词”破坏语法或重复卖点。

不主动新增评论痛点分析。研究包已有或用户明确提供评论时，评论只能调整写作重点，评论计数、观点和竞品缺陷不能进入 facts 或被写成自有产品优势。`notice_fact_ids` 为可选字段；提供时必须来自已确认事实，并在详情包装块之后生成本地化注意事项标题。没有可靠注意事项事实时省略该字段和该 HTML 块。

limits 默认空：仅在核实规则后填入站点下的 title_chars / search_terms_bytes，并在任务记录保留官方来源、类目和查询日期。脚本报告未核实项，不内置通用限制。

package-review.json 检查目标站点/变体齐全、单行标题、规范标点空格、3 个核心标题关键词及场景、标题数量规则、颜色模式、标题中的原词或 alias、五点数量及默认“Emoji＋【小标题】＋2—4句且正文至少180个可见字符”格式、基础 HTML 描述、Search Terms、事实来源和映射。五点超过约420个可见字符或存在可用次要词但未自然覆盖时只提示人工复核，不强制塞词；标题 150—190 字符也仅作为编辑警告，不冒充平台限制。字符和句数校验不能代替语义审核；模型还必须确认每条有事实锚点，并具体展开作用/效果、买家价值、使用方式或适用边界中的至少两项，且不含内部审核措辞。ready_for_delivery=false 时不得交付。

content-review.json 会先剥离 HTML 标签，再计算原词/语义组覆盖数、各字段样本分母、证据位置、长度和重复片段。两个检查都不负责语义审核、自动翻译、事实推断或发布；三个标题词是否语义重复、标题自然度、五点是否真正汇总多竞品主题、品牌候选及8词重合须由模型复核。输出文件已存在时拒绝覆盖。
