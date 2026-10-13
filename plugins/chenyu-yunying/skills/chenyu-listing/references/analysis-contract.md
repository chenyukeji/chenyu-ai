# 分析脚本接口

`listing-package.json` 是生成、校验和交付之间的内部接口。买家可见内容不得包含内部审核字段。

## 最小结构

```json
{
  "source_mapping_version": 2,
  "search_term_policy_version": 2,
  "targets": ["DE"],
  "variants": [{"id": "V1", "marketplaces": ["DE"]}],
  "facts": [
    {
      "id": "F1",
      "source_type": "own_product",
      "status": "confirmed",
      "field": "material",
      "value": "Polyester",
      "variant_ids": ["V1"],
      "source": {"sheet": "Product", "cell": "B2"}
    },
    {
      "id": "F2",
      "source_type": "same_product_evidence",
      "same_product_confirmed": true,
      "status": "confirmed",
      "field": "installation",
      "value": "Mittige Öffnung und Seitenschlitz",
      "variant_ids": ["V1"],
      "source": {"asin": "B012345678", "field": "bullet_3", "user_message": "同款确认"}
    }
  ],
  "competitors": [
    {
      "id": "C1",
      "marketplace": "DE",
      "product_group": "P1",
      "status": "complete",
      "asin": "B012345678",
      "url": "https://www.amazon.de/dp/B012345678",
      "title": "...",
      "bullets": ["竞品第1点原文", "竞品第2点原文", "竞品第3点原文", "竞品第4点原文", "竞品第5点原文"],
      "description": "..."
    }
  ],
  "keywords": [
    {"marketplace": "DE", "phrase": "Weihnachtsbaumdecke", "aliases": ["Baumdecke"], "is_core": true},
    {"marketplace": "DE", "phrase": "Weihnachtsbaum Rock", "aliases": [], "is_core": true},
    {"marketplace": "DE", "phrase": "Tannenbaumdecke", "aliases": [], "is_core": true},
    {"marketplace": "DE", "phrase": "Baumschmuck Unterlage", "aliases": [], "decision": "adopt"}
  ],
  "mappings": [
    {
      "marketplace": "DE",
      "variant_id": "V1",
      "fact_ids": ["F1", "F2"],
      "buying_reasons": ["Abdeckung", "einfache Platzierung"],
      "keywords": ["Weihnachtsbaumdecke", "Weihnachtsbaum Rock", "Tannenbaumdecke", "Baumschmuck Unterlage"],
      "listing_fields": ["title", "item_highlights", "bullet_1", "bullet_2", "bullet_3", "bullet_4", "bullet_5", "description", "search_terms"]
    }
  ],
  "search_term_audits": [
    {
      "marketplace": "DE",
      "variant_id": "V1",
      "phrase": "christbaum teppich",
      "source_asin": "B012345678",
      "source_tool": "sellersprite_reverse_asin",
      "source_marketplace": "DE",
      "organic_results_checked": 20,
      "relevant_results": 16,
      "relevance_band": "high",
      "specificity": "product_specific",
      "product_match_reason": "完整短语指向铺在圣诞树底部的装饰垫，结构与用途匹配",
      "decision": "adopt",
      "local_volume_claimed": false
    },
    {
      "marketplace": "DE",
      "variant_id": "V1",
      "phrase": "christbaum unterlage",
      "source_asin": "B012345678",
      "source_tool": "reference_title_terms",
      "source_field": "title",
      "source_marketplace": "DE",
      "organic_results_checked": 20,
      "relevant_results": 15,
      "relevance_band": "high",
      "specificity": "product_specific",
      "product_match_reason": "完整短语指向铺在圣诞树底部的装饰垫，结构与用途匹配",
      "decision": "adopt",
      "local_volume_claimed": false
    }
  ],
  "listings": [
    {
      "marketplace": "DE",
      "language": "de-DE",
      "variant_id": "V1",
      "title": "...",
      "title_keywords": ["Weihnachtsbaumdecke", "Weihnachtsbaum Rock", "Tannenbaumdecke"],
      "title_size_term": "",
      "title_size_reason": "",
      "critical_differentiators": ["5-lagig"],
      "title_scene": "",
      "title_quantity": 1,
      "title_quantity_term": "",
      "color_mode": "single",
      "title_color_terms": [],
      "compatibility_required": false,
      "primary_compatibility_term": "",
      "compatibility_terms": [],
      "title_reference": "Weihnachtsbaumdecke ← B012345678 标题（原文短语）；5-lagig ← 自有事实 F1",
      "title_phrase_sources": [
        {"phrase": "Weihnachtsbaumdecke", "asin": "B012345678", "source_field": "title", "source_phrase": "竞品标题原文短语"},
        {"phrase": "5-lagig", "fact_id": "F1"}
      ],
      "item_highlights": "...",
      "item_highlights_reference": "重要词组 ← B012345678 第2点（原文短语）；自有规格 ← 自有事实 F1",
      "item_highlights_phrase_sources": [
        {"phrase": "重要词组", "asin": "B012345678", "source_field": "bullet_2", "source_phrase": "竞品第2点原文短语"},
        {"phrase": "自有规格", "fact_id": "F1"}
      ],
      "bullets": ["...", "...", "...", "...", "..."],
      "bullet_references": ["B012345678 第1点（采用的主题）", "B012345678 第2点（采用的主题）", "B012345678 第3点（采用的主题）", "B012345678 第4点（采用的主题）", "B012345678 第5点（采用的主题）"],
      "description": "<p>...</p>",
      "description_reference": "参考开发表及 B012345678 第1-5点",
      "front_end_attributes": ["Rot", "120 cm"],
      "buyer_visible_variant_terms": [],
      "primary_reference_asin": "B012345678",
      "search_terms": "christbaum teppich unterlage",
      "search_terms_reference": "参考 B012345678 卖家精灵反查、参考标题及 Amazon DE 前20个自然结果",
      "claim_fact_ids": ["F1", "F2"],
      "field_fact_ids": {
        "title": ["F1"],
        "item_highlights": ["F1", "F2"],
        "bullet_1": ["F1"],
        "bullet_2": ["F2"],
        "bullet_3": ["F1"],
        "bullet_4": ["F2"],
        "bullet_5": ["F1"],
        "description": ["F1", "F2"]
      },
      "notice_fact_ids": [],
      "translations": {
        "title": "...",
        "item_highlights": "...",
        "bullets": ["...", "...", "...", "...", "..."],
        "description": "<p>...</p>",
        "search_terms": "..."
      }
    }
  ],
  "limits": {
    "DE": {"title_chars": 75, "item_highlights_chars": 125, "search_terms_bytes": 249}
  }
}
```

## 字段规则

### facts

- `source_type=own_product`：来自开发资料、自有图片或用户明确说明。本工作流按用户已授权的“默认参考第一条链接，仅改本品明确的实质差异”执行时，适用于当前变体且不与已有事实冲突的细节可作为本次写作采用的产品属性，仍保留 `status=confirmed`，但须在内部 `source` 记录首链接 ASIN、原文点位和用户授权；此状态表示本次可用于草稿，不表示已独立测量实物。交付“产品内容”只显示属性值，供后续人工微调。
- `source_type=same_product_evidence`：必须同时满足 `same_product_confirmed=true`、`status=confirmed`，并在 `source` 中保存有效 ASIN 和同款确认来源。
- `source_type=material_match_evidence`：自有材料与竞品材料一致且其功能适用于本品时，可记录竞品 ASIN/五点位置及自有材料来源，并将该功能作为已确认事实用于 Listing；不要求把竞品整体确认为同款。材料匹配说明保留在内部事实记录，不写给买家。
- 同款或同材料功能依据不得用于迁移品牌、冲突规格/数量/配件、认证、质保、售后或竞品独有版本。

### listings

标题只从竞品标题取材，五点只从竞品五点取材，分别综合全部有效链接，不跨字段引用。使用开发表值修正时，在内部 `development_corrections` 记录 `reference_text`、`development_source`（文件/工作表/单元格）、`development_value`、`material_difference` 和 `affected_field`。仅明确、实质性的差异允许覆盖对应参考内容；本品表未提及的参考属性不作为差异。这个记录用于真实语义复核，不是新增交付工作表或靠填写字段自动获得通过。

`field_fact_ids` 是本字段实际属性的核对记录，不是扩写授权，不得所有字段套用全量事实编号。`title_phrase_sources`、`clause_sources` 的具体原文必须支持对应修饰词、工艺、作用及结果；同一部位的词语不等于支持整句。作图方案或 AI 效果图不能标为已确认本品事实，即使曾被复制进产品内容页也须追溯上游来源。

- `title_keywords` 为恰好三个不同核心短语，必须在同站点 `keywords` 中标记 `is_core:true`，并以原词或 alias 自然进入标题。优先产品名称、同义称呼及图案/主题与产品名称的组合；搜索需求依据记录在关键词来源中，不用标题频次冒充搜索量，不默认选择场景词。核心词相关性和搜索依据须语义复核，脚本只检查数量、标记和覆盖。全部有效竞品标题的 ASIN/站点、产品搜索短语、图案/主题组合、补充属性、采用词义与排除理由记入内部 `title_candidate_audit`。`title_reference` 只展示实际采用词组的来源，不追加未贡献标题内容或仅用于后台搜索词的链接。标题的有意义词组只来自全部适用竞品标题；Highlights 可来自竞品标题或五点；本品事实只用于明确实质差异的局部修正，先整合共有重点和互补细节。v2 校验器按 `title_phrase_sources` 核对实际采用来源；全部候选阅读、取舍与语义合并仍须核对，内部审计不作为来源数量指标。
- `title_size_term`、`title_size_reason` 默认空。竞品标题中出现尺寸即可采用并填写，不额外判断其是否为主要卖点；标题最多一组尺寸，必须与 `title_size_term` 一致并置于末尾，`title_size_reason` 记录参考 ASIN、标题原文及必要的本品差异修正。
- `critical_differentiators` 只列能影响购买、适配或价格的重要差异；每项必须出现在标题前部。
- `title_scene` 可空；非空时必须出现在标题。
- `title_quantity` 为正整数。等于 1 时 `title_quantity_term` 为空；大于 1 时数量短语必须紧贴第一核心产品词。若 Item Highlights 又用同一整包数量修饰同一产品名称，校验器报错；不同含义的数量必须明确所数对象并人工复核。
- `item_highlights` 与 `item_highlights_reference` 必填。
- `front_end_attributes` 收录未直接写在文案对象中的已填前台属性，Search Terms 去重时一并计算。
- `buyer_visible_variant_terms` 默认空数组。只有用户明确确认属于买家公开名称的变体词才可加入；没有进入此清单的 `Design A/B/C` 等内部编号不得出现在买家可见字段。
- `primary_reference_asin` 指向用户第一条参考，作为缺失产品属性的默认依据，不限制五点取材或顺序；五点充分整合全部有效链接，优先覆盖相关实质内容并合并同义信息。本品描述明确且有实质差异时才局部替换。五条 `bullet_references` 逐短句映射实际原文来源，且各自至少引用一个已在 `competitors[].bullets` 读取的 `ASIN 第N点（采用的主题）`；一条可列多个来源，但每个点位分别写完整 ASIN 和编号，自有事实可作为附加依据。新包的完整短句结构见下节。校验器检查点位存在，实际写作须按 [五点取材与去重](bullet-evidence.md) 复核主题、展开细节与原文的语义对应及五条的信息差异；标题、图册和开发文档不能替代原始竞品五点。与 `field_fact_ids.bullet_1` 至 `bullet_5` 对应核对本品事实；详情另用 `description_reference` 和 `field_fact_ids.description` 记录。五条不要求与首链接固定映射。允许一个来源中的不同事实分配到不同条，但同一事实换说法不算独立主题；内部 `bullet_outline` 保留主题、采用点位、信息增量和合并/排除理由，不增加交付工作表。
- `title_phrase_sources`、`item_highlights_phrase_sources` 各为非空数组，将两个字段中所有有购买含义的词组逐一映射。标题来源项的 `source_field` 只允许 `title`，Highlights 可用 `title` 或 `bullet_1`…`bullet_5`。竞品来源项用 `{ "phrase": "目标文案中的词组", "asin": "B012345678", "source_field": "title 或 bullet_1…bullet_5", "source_phrase": "竞品原文中的短语" }`；自有事实项用 `{ "phrase": "目标文案中的词组", "fact_id": "F1" }`。`phrase` 必须出现在相应目标文案，`source_phrase` 必须能在该竞品的对应标题或五点找到；翻译和语义适配另由人工复核。标题三个核心词组须各有竞品来源；目标文案使用同义词形时，可在来源项额外写 `keyword` 指向对应 `title_keywords` 原词。`title_reference` 与 `item_highlights_reference` 逐项显示同一映射，例如 `collier de perles ← B012345678 标题（pearl necklace）；trois perles ← 自有事实 F1`，供卖家直接核对。
- `field_fact_ids` 必须为 `title`、`item_highlights`、`bullet_1` 至 `bullet_5` 和 `description` 分别提供至少一个已确认事实编号；这些编号必须同时存在于 `claim_fact_ids`，且适用于当前变体。字段新增任何具体宣称时先更新事实映射，再写文案。
- 适配型产品设置 `compatibility_required=true`。`primary_compatibility_term` 保存必须进入 Item Name 和五点 1 的主要系列/型号/替换件号；`compatibility_terms` 保存必须由 Item Name＋Item Highlights 完整覆盖、并在 HTML 详情完整列出的已确认兼容标识。中文标题＋Item Highlights、五点 1 和详情也必须保留相同标识。非适配型产品保留 `false` 和空值。
- `translations` 必填，逐字段保存完整中文翻译。它只翻译目标语言买家文案，不得混入事实状态、资料来源、包装核算、竞品差异或审核过程；五点必须正好五条。`translations.description` 必须是与 `description` 标签序列及编号顺序对应的中文 HTML，只翻译可见文字，保留 `<p>`、`<b>`、`<br>` 原始标签。生成 Excel 前，目标语言和此对象必须一起通过校验。
- Item Name、Item Highlights、五点和详情可以重复核心词、关键事实、尺寸和场景，不设跨字段机械去重错误。

### 逐短句来源（新包必填）

新生成包顶层设置 `source_mapping_version: 2`。旧包可读取，但修改或重新交付时升级；旧版校验通过不代表已满足逐短句溯源。

每个 listing 新增 `clause_sources` 对象，键为 `bullet_1` 至 `bullet_5`、`description`，值为短句数组。条目格式：

```json
{"text": "目标文案中的一个最小有意义短句", "sources": [
  {"asin": "B012345678", "source_field": "bullet_2", "source_phrase": "实际读取的原文短句"}
]}
```

- `sources` 记录实际内容来源，`field_fact_ids` 单独记录本品适用性核对。同一参考描述被本品事实核实后，sources 仍保留参考 ASIN，不必追加 fact_id；事实编号只用于它实际补充或校正的短语。若参考写45cm而本品为40cm，通用产品卖点仍映射参考，40cm独立映射本品事实，不能把整句尺寸称为参考原文支持。
- 每个独立属性、用途或结果分别映射；同句中的几个分句来自不同位置时拆开。一个不可再拆的表达确实由多个来源共同支持时，sources 可有多项；不要整条五点或整篇详情挂一组混合来源。
- 五点的竞品 `source_field` 只允许 `bullet_1`…`bullet_5`，可融合不同参考的不同点位；详情的竞品来源可为 `title`、`bullet_1`…`bullet_5`、`description`、`aplus_text`；详情/A+ 必须先把实际原文保存到 competitors 对应字段，不得用 URL 或图片描述替代。主要依据仍是竞品标题和五点。
- 原文 source_phrase 必须真实存在于所指字段；目标 text 必须存在于去 HTML 标签后的目标文案。本品事实必须适用当前变体，且列于该字段 field_fact_ids。
- 每条 `bullet_references` 与 `description_reference` 逐项写 `目标短句 ← ASIN 第N点（原文短句）`、`目标短句 ← ASIN 详情（原文短句）` 或 `目标短句 ← 自有事实 F1`；融合来源分别列映射。保留现有 Excel 参考列，可换行，不新建审核表。每条五点至少有一个短句实际绑定竞品原始五点；有竞品研究时，详情也必须采用真实五点、详情或A+内容，不能整篇仅映射自有事实。这只是结构最低检查，实际核心内容仍须以适用参考为主，不能靠引用一句或在参考列额外挂点位充数。
- 去 HTML 后正文、小标题里的具体卖点及参数都须覆盖。纯栏目标题（如“产品参数”）或语法连接词可写 `{"text":"...", "kind":"editorial", "reason":"栏目标题/语法连接"}`；不能用此类型豁免产品属性、修饰词或用途。标题与 Highlights 继续用已有逐词组映射；冠词/介词可随所属词组一起映射，无须为其寻找独立来源。若有连接词未被词组覆盖，在 `editorial_phrases.title` 或 `editorial_phrases.item_highlights` 数组记 `{"text":"und", "reason":"语法连接词"}`，用于完整覆盖检查。
- 校验器检查短句覆盖、字段点位、原文存在、事实绑定及可见参考对应；语义是否支持、翻译是否准确、短句是否足够细和 editorial 是否滥用须实际复核。不能声称这些语义问题已被脚本证明。

### search_term_audits

- 每个含竞品证据的站点/变体保存卖家精灵反查、全部有效参考链接标题词以及 Amazon 搜索相关性记录；前台去重后有效词不足时，继续加入其他同类商品标题词。
- 卖家精灵候选使用 `source_tool=sellersprite_reverse_asin`；必须包含 `primary_reference_asin` 的反查，补查其他相关 ASIN 时可增加记录，所有反查 `source_asin` 均须存在于 `competitors`。
- 参考标题候选使用 `source_tool=reference_title_terms`、`source_field=title`，其 `source_asin` 必须存在于 `competitors`；可以来自任一有效参考链接，不限第一条。
- 额外同类商品标题候选使用 `source_tool=same_category_title_terms`、`source_field=title`；对应 ASIN 与标题须加入 `competitors`，并先排除不同产品结构、用途、规格和配件词。此来源补充前两类，不替代全部有效参考链接的检查。
- `organic_results_checked` 至少 20；`relevant_results / organic_results_checked` 不低于 70% 为 `high`，40%–69% 为 `medium`，低于 40% 为 `low`。
- 新生成或重做包设置顶层 `search_term_policy_version=2`。`decision=adopt` 只允许 `high`，并要求 `specificity=product_specific` 与非空 `product_match_reason`（具体解释产品类型、结构或用途匹配）；泛词即使自然位比例高也不采用。`medium` 先细化后再验证。跨站点数据必须设置 `local_volume_claimed=false`。旧包默认版本 1 可读取，但会收到升级提示，修改或交付须升级。
- 最终 Search Terms 中的词元必须来自 `decision=adopt` 的候选，并删除所有前台字段已经覆盖的词元；反过来，已采用且前台未覆盖的有效词元也必须全部写入。有充足高相关词时目标 240–249 UTF-8 字节。低于 240 字节时每个 listing 必须保存 `search_term_expansion: {"queries": ["实际执行的补查站点、查询词或反查 ASIN"], "shortfall_reason": "补查后仍无法扩充的具体原因，对应候选及排除记录"}`；不允许空值或未执行的查询。短字段有真实补查和具体原因即可通过，不强制填充泛词。超过上限时允许把放不下的合格候选记为 `decision=exclude`、`exclusion_reason=byte_limit`，按相关性和新增检索叫法择优；校验器拒绝仍可容纳的字节排除理由。来源审查与产品匹配为人工语义审核，脚本只能检查字段和数值。

## 脚本

```powershell
python scripts/validate_listing_package.py listing-package.json --out package-review.json
python scripts/analyze_listing.py listing-package.json --out listing-analysis.json
```

`validate_listing_package.py` 检查站点/变体覆盖、事实与同款证据、逐字段事实绑定、75/125 字符限制、恰好三个核心标题词及标题尺寸末尾规则、数量与关键差异位置、适配型产品在标题/Highlights/五点 1/详情及中文翻译中的兼容标识覆盖、五点来源记录与逐字段已确认事实映射、内部变体编号泄漏、五点数量/格式/正文长度、HTML 详情结构、Search Terms 增量词、卖家精灵与参考标题来源审计（含额外同类标题），以及已采用增量词是否全部写入。它同时拒绝目标语言和中文翻译中的证据状态、资料来源、参考产品、竞品差异和其他内部审核叙述。`ready_for_delivery=false` 时不得将文案标为已完成审核。

`analyze_listing.py` 输出竞品独立商品组频次、字段覆盖、Item Name/Item Highlights/五点/Search Terms 长度，以及与竞品连续 8 词重合的人工复核提示。重合提示不等于抄袭判定，也不会禁止同款事实在多个前台字段自然重复。
