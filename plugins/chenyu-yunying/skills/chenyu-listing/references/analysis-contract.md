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
    {"marketplace": "DE", "phrase": "Baumschmuck Unterlage", "aliases": [], "decision": "adopt"}
  ],
  "mappings": [
    {
      "marketplace": "DE",
      "variant_id": "V1",
      "fact_ids": ["F1", "F2"],
      "buying_reasons": ["Abdeckung", "einfache Platzierung"],
      "keywords": ["Weihnachtsbaumdecke", "Weihnachtsbaum Rock", "Baumschmuck Unterlage"],
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
    }
  ],
  "listings": [
    {
      "marketplace": "DE",
      "language": "de-DE",
      "variant_id": "V1",
      "title": "...",
      "title_keywords": ["Weihnachtsbaumdecke", "Weihnachtsbaum Rock"],
      "critical_differentiators": ["5-lagig"],
      "title_scene": "",
      "title_quantity": 1,
      "title_quantity_term": "",
      "color_mode": "single",
      "title_color_terms": [],
      "title_reference": "参考开发表及 B012345678 标题",
      "item_highlights": "...",
      "item_highlights_reference": "参考开发表及 B012345678 标题/第2点",
      "bullets": ["...", "...", "...", "...", "..."],
      "bullet_references": ["...", "...", "...", "...", "..."],
      "description": "<p>...</p>",
      "description_reference": "参考开发表及 B012345678 第1-5点",
      "front_end_attributes": ["Rot", "120 cm"],
      "primary_reference_asin": "B012345678",
      "search_terms": "christbaum teppich",
      "search_terms_reference": "参考 B012345678 卖家精灵反查及 Amazon DE 前20个自然结果",
      "claim_fact_ids": ["F1", "F2"],
      "notice_fact_ids": []
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
- 同款证据不得用于迁移品牌、冲突规格/数量/配件、认证、质保、售后或竞品独有版本。

### listings

- `title_keywords` 为 2–4 个不同核心短语，必须在同站点 `keywords` 中标记 `is_core:true`，并以原词或 alias 自然进入标题。
- `critical_differentiators` 只列能影响购买、适配或价格的重要差异；每项必须出现在标题前部。
- `title_scene` 可空；非空时必须出现在标题。
- `title_quantity` 为正整数。等于 1 时 `title_quantity_term` 为空；大于 1 时数量短语必须紧贴第一核心产品词。
- `item_highlights` 与 `item_highlights_reference` 必填。
- `front_end_attributes` 收录未直接写在文案对象中的已填前台属性，Search Terms 去重时一并计算。
- Item Name、Item Highlights、五点和详情可以重复核心词、关键事实、尺寸和场景，不设跨字段机械去重错误。

### search_term_audits

- 每个含竞品证据的站点/变体必须保存卖家精灵反查与 Amazon 搜索相关性记录。
- `source_tool` 固定为 `sellersprite_reverse_asin`，`source_asin` 与该 Listing 的 `primary_reference_asin` 一致。
- `organic_results_checked` 至少 20；`relevant_results / organic_results_checked` 不低于 70% 为 `high`，40%–69% 为 `medium`，低于 40% 为 `low`。
- `decision=adopt` 不能用于 `low` 候选。跨站点数据必须设置 `local_volume_claimed=false`。
- 最终 Search Terms 中的词元必须来自 `decision=adopt` 的候选，并删除所有前台字段已经覆盖的词元。

## 脚本

```powershell
python scripts/validate_listing_package.py listing-package.json --out package-review.json
python scripts/analyze_listing.py listing-package.json --out listing-analysis.json
```

`validate_listing_package.py` 检查站点/变体覆盖、事实与同款证据、75/125 字符限制、2–4 个核心标题词、数量与关键差异位置、五点数量/格式/正文长度、HTML 详情结构、Search Terms 增量词和反查审计。`ready_for_delivery=false` 时不得交付。

`analyze_listing.py` 输出竞品独立商品组频次、字段覆盖、Item Name/Item Highlights/五点/Search Terms 长度，以及与竞品连续 8 词重合的人工复核提示。重合提示不等于抄袭判定，也不会禁止同款事实在多个前台字段自然重复。
