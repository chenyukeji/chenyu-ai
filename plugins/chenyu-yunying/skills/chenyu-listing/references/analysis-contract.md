# 分析脚本接口

`listing-package.json` 是生成、校验和交付之间的内部接口。买家可见内容不得包含内部审核字段。

## 最小结构

```json
{
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
      "bullets": ["..."],
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
      "title_reference": "B012345678 / DE：产品名称与同义称呼候选；按搜索证据和自有事实筛选，不预设场景词名额",
      "item_highlights": "...",
      "item_highlights_reference": "参考开发表及 B012345678 标题/第2点",
      "bullets": ["...", "...", "...", "...", "..."],
      "bullet_references": ["...", "...", "...", "...", "..."],
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

- `source_type=own_product`：来自开发资料、自有图片或用户明确说明。
- `source_type=same_product_evidence`：必须同时满足 `same_product_confirmed=true`、`status=confirmed`，并在 `source` 中保存有效 ASIN 和同款确认来源。
- `source_type=material_match_evidence`：自有材料与竞品材料一致且其功能适用于本品时，可记录竞品 ASIN/五点位置及自有材料来源，并将该功能作为已确认事实用于 Listing；不要求把竞品整体确认为同款。材料匹配说明保留在内部事实记录，不写给买家。
- 同款或同材料功能依据不得用于迁移品牌、冲突规格/数量/配件、认证、质保、售后或竞品独有版本。

### listings

- `title_keywords` 为恰好三个不同核心短语，必须在同站点 `keywords` 中标记 `is_core:true`，并以原词或 alias 自然进入标题。优先产品名称、同义称呼及图案/主题与产品名称的组合；搜索需求依据记录在关键词来源中，不用标题频次冒充搜索量，不默认选择场景词。核心词相关性和搜索依据须语义复核，脚本只检查数量、标记和覆盖。`title_reference` 列出全部有效竞品标题的 ASIN/站点，记录其产品搜索短语、图案/主题组合、补充属性、采用词义和排除项；标题描述词只使用能在至少一个竞品标题中找到语义对应、且符合自有事实的内容。校验器会检查全部有 ASIN 和标题的竞品是否被引用，语义合并仍须人工复核。
- `title_size_term`、`title_size_reason` 默认空。仅当尺寸已证实直接影响适配、覆盖或变体选择时填写；标题最多一组尺寸，必须与 `title_size_term` 一致并置于末尾，`title_size_reason` 说明具体购买理由。
- `critical_differentiators` 只列能影响购买、适配或价格的重要差异；每项必须出现在标题前部。
- `title_scene` 可空；非空时必须出现在标题。
- `title_quantity` 为正整数。等于 1 时 `title_quantity_term` 为空；大于 1 时数量短语必须紧贴第一核心产品词。
- `item_highlights` 与 `item_highlights_reference` 必填。
- `front_end_attributes` 收录未直接写在文案对象中的已填前台属性，Search Terms 去重时一并计算。
- `buyer_visible_variant_terms` 默认空数组。只有用户明确确认属于买家公开名称的变体词才可加入；没有进入此清单的 `Design A/B/C` 等内部编号不得出现在买家可见字段。
- `primary_reference_asin` 保留主要同款与关键词反查身份，不决定五点顺序。按输入链接原始顺序保留参考优先级，越靠前权重越高；五条 `bullet_references` 各自记录实际采用的 ASIN/原点位，一条可列多个来源，也可引用自有资料。与 `field_fact_ids.bullet_1` 至 `bullet_5` 对应核对适用内容；详情用 `description_reference` 和 `field_fact_ids.description` 记录。无需生成 `primary_reference_bullet_outline` 或逐点 `description_excerpt`，不再校验五条与首链接的固定映射。来源优先级、内容整合、具体信息覆盖及去重须语义复核。
- `field_fact_ids` 必须为 `title`、`item_highlights`、`bullet_1` 至 `bullet_5` 和 `description` 分别提供至少一个已确认事实编号；这些编号必须同时存在于 `claim_fact_ids`，且适用于当前变体。字段新增任何具体宣称时先更新事实映射，再写文案。
- 适配型产品设置 `compatibility_required=true`。`primary_compatibility_term` 保存必须进入 Item Name 和五点 1 的主要系列/型号/替换件号；`compatibility_terms` 保存必须由 Item Name＋Item Highlights 完整覆盖、并在 HTML 详情完整列出的已确认兼容标识。中文标题＋Item Highlights、五点 1 和详情也必须保留相同标识。非适配型产品保留 `false` 和空值。
- `translations` 必填，逐字段保存完整中文翻译。它只翻译目标语言买家文案，不得混入事实状态、资料来源、包装核算、竞品差异或审核过程；五点必须正好五条。生成 Excel 前，目标语言和此对象必须一起通过校验。
- Item Name、Item Highlights、五点和详情可以重复核心词、关键事实、尺寸和场景，不设跨字段机械去重错误。

### search_term_audits

- 每个含竞品证据的站点/变体保存卖家精灵反查、全部有效参考链接标题词以及 Amazon 搜索相关性记录；前台去重后有效词不足时，继续加入其他同类商品标题词。
- 卖家精灵候选使用 `source_tool=sellersprite_reverse_asin`，其 `source_asin` 与 Listing 的 `primary_reference_asin` 一致。
- 参考标题候选使用 `source_tool=reference_title_terms`、`source_field=title`，其 `source_asin` 必须存在于 `competitors`；可以来自任一有效参考链接，不限第一条。
- 额外同类商品标题候选使用 `source_tool=same_category_title_terms`、`source_field=title`；对应 ASIN 与标题须加入 `competitors`，并先排除不同产品结构、用途、规格和配件词。此来源补充前两类，不替代全部有效参考链接的检查。
- `organic_results_checked` 至少 20；`relevant_results / organic_results_checked` 不低于 70% 为 `high`，40%–69% 为 `medium`，低于 40% 为 `low`。
- `decision=adopt` 不能用于 `low` 候选。跨站点数据必须设置 `local_volume_claimed=false`。
- 最终 Search Terms 中的词元必须来自 `decision=adopt` 的候选，并删除所有前台字段已经覆盖的词元；反过来，已采用且前台未覆盖的有效词元也必须全部写入。

## 脚本

```powershell
python scripts/validate_listing_package.py listing-package.json --out package-review.json
python scripts/analyze_listing.py listing-package.json --out listing-analysis.json
```

`validate_listing_package.py` 检查站点/变体覆盖、事实与同款证据、逐字段事实绑定、75/125 字符限制、恰好三个核心标题词及标题尺寸末尾规则、数量与关键差异位置、适配型产品在标题/Highlights/五点 1/详情及中文翻译中的兼容标识覆盖、五点来源记录与逐字段已确认事实映射、内部变体编号泄漏、五点数量/格式/正文长度、HTML 详情结构、Search Terms 增量词、卖家精灵与参考标题来源审计（含额外同类标题），以及已采用增量词是否全部写入。它同时拒绝目标语言和中文翻译中的证据状态、资料来源、参考产品、竞品差异和其他内部审核叙述。`ready_for_delivery=false` 时不得将文案标为已完成审核。

`analyze_listing.py` 输出竞品独立商品组频次、字段覆盖、Item Name/Item Highlights/五点/Search Terms 长度，以及与竞品连续 8 词重合的人工复核提示。重合提示不等于抄袭判定，也不会禁止同款事实在多个前台字段自然重复。
