# 跨语言搜索词与短字段复核

生成或补充 Search Terms 时执行。目标是把实际来源中的产品概念转成当地买家会搜索的叫法，增加高相关覆盖；AI 翻译本身不证明当地搜索量或相关性。

## 原词 → 本地候选 → 搜索证据

1. 收集全部有效参考标题和卖家精灵真实反查中的相关产品短语，保留原词、来源 ASIN、站点与语言。不能只取第一条标题或一个反查词就停止。优先自然搜索词；其他流量类型保留原标签，经本品适用性与当地自然结果验证后也可贡献候选，不把广告流量说成自然流量。
2. 用 AI 将英文或其他外语原词翻译、改写为目标站点的自然商品称呼，兼顾当地同义称呼和具体长尾组合。同一原词可生成多个语义成立的候选，分别审核；不要只逐字翻译，也不要添加原词及本品事实没有的结构、材质、用途或人群。当地买家确实使用的借词可以保留，需记录当地使用依据。
3. 对目标语言候选检查目标站点前 20 个自然结果，保留实际查询词与证据文件/URL。不要把英文原词在法国站的低匹配率当作法语翻译词的结果，不能把未查询计为 0 个相关结果。来源为 US 不代表没有可用法语词；缺少 FR 搜索量只意味着不能声称 FR 搜索量，不是排除理由。
4. 对完整候选短语判定产品相关性和具体程度，再做前台去重。譬如英文 `deer antler headband` 可先生成法语 `serre tête bois de cerf`，再根据产品和当地证据考虑其他自然称呼；示例只是翻译候选，未经当地复核不能直接交付。不能用单独的 `chevreuil` 的搜索结果代替完整产品短语的核查。
5. 高相关候选按新增检索叫法和适用性排序，写入前台未覆盖的词元。目标 240–249 UTF-8 字节；不得为了后台词数删掉前台有价值内容，也不得靠泛词、重复单复数或生硬同义改写填满。

## v3 记录与交付检查

新生成、重做和重新交付的包设置 `search_term_policy_version=3`。命令行与 Python `validate()` 默认均拒绝旧版本；历史数据只可显式用 `validate(..., require_current_search_policy=False)` 诊断，不能把兼容检查当作新交付验收。

每个 `search_term_audits` 条目都保留以下字段（原有 ASIN、来源类型、自然结果数量、相关性与决定字段继续保留）：

```json
{
  "source_phrase": "deer antler headband",
  "source_language": "en",
  "target_language": "fr",
  "localization_method": "ai",
  "phrase": "serre tête bois de cerf",
  "search_marketplace": "FR",
  "search_query": "serre tête bois de cerf",
  "search_evidence": "internal/fr-serre-tete-bois-de-cerf-results.json"
}
```

- `source_phrase` 是实际来源原文；标题来源必须能在所指 ASIN 的标题中找到。卖家精灵原词对照实际反查文件，不伪造来源。
- `phrase` 始终保存待验证的目标语言完整短语；`source_language` 使用两位语言代码，`target_language` 为 de/fr/it/es/en。来源语言不同须 `localization_method=ai`；原词原样保留时需 `localization_note` 说明当地借词依据，不能借此保留不自然英文。
- `search_query` 对应此候选，`search_marketplace` 为目标站点，`search_evidence` 指向实际读取的证据。多个变体共用相同证据时可复用记录。脚本检查字段对应，语义、翻译和证据真实性必须另行复核。
- 排除词必须逐项写 `exclusion_reason` 和具体 `exclusion_detail`。原因只允许 `front_end_covered`（翻译后的全部有效词元已被前台覆盖）、`product_mismatch`（具体结构/用途不符）、`low_relevance`（目标语言查询结果不足高相关）、`byte_limit`（确实放不下）。不得仅写“英文词”“没有本地搜索量”或统一套用“已覆盖或不相关”。前台去重不能在英文原词上进行。

## 少于 240 字节时

继续补查并保留 `search_term_expansion.queries`、`shortfall_reason`，还要列出 `reviewed_phrases`，与该站点/变体全部候选审核中的目标语言 `phrase` 一一对应。`title_candidate_audit.all_user_references` 保存全部有效用户参考 ASIN；每个 ASIN 必须有对应的标题翻译候选或具体排除记录，不能只用首链接代表全部参考。

逐条核实被排除的本地候选及证据，尤其检查翻译后仍有新增词却被标为前台已覆盖的情况。短字段可以是充分研究后的真实结果，但一句笼统说明不构成研究完成。不得为通过字段校验捏造补查、翻译或搜索统计，也不得把旧任务的少词结果原样填几个新字段就重新交付。
