# 跨语言搜索词与短字段复核

生成或补充 Search Terms 时执行。目标是把实际来源中的产品概念转成当地买家会搜索的叫法，增加高相关覆盖；AI 翻译本身不证明当地搜索量或相关性。

## 词池先于前台写作，交付前逐站闭环

首次生成和微调都按“产品概念 → 各站完整候选 → 前台分配 → 后台去重装填 → 缺口补查 → 逐站复核”执行。后台词长度只是容量指标，不是相关性得分；不能以德国站词池充分代替法国、意大利、西班牙站的研究，也不要求四站字数或词数相同。

1. **写作前建立词池。** 从实际参考标题、真实反查词及本品事实核对中提取适用的产品名称、当地别称、结构、主题、真实用途；本品事实用于确认适用性，不凭空创造搜索来源。保存 `search_term_concepts` 和各目标站点/变体的完整短语审核 `search_term_audits`。原始词池保留完整短语及排除项，不因后来进入前台就删除候选记录。各语言独立组织自然商品叫法，不先写德国版再逐词翻译；同一概念可有多个自然表达，不为凑候选条数排列词序或批量添加形容词。
2. **先审核短语，再拆词。** 逐条判断“买家搜索这个短语，是否在找当前产品”，保留来源和具体适用理由。优先产品名称、真实别称和能区分商品的具体长尾；单独的“漂亮、优质、礼物、节庆”等不作为补字素材。准确的材质、结构或主题修饰可以保留在完整产品短语中，不把所有形容词一律禁用；品牌、错误用途和其他产品类型排除。
3. **前台按阅读需要分配。** 核心词自然进入标题和正文，适用别称进入有意义的句子，仍遵守各字段既有取材规则。不把词池全塞入正文，也不为了后台长度删掉前台必要信息。后台承接尚未覆盖的有效词元，完整短语始终留在审核表；后台拆词后的外观不能代替完整短语相关性判断。
4. **用当前成品重算覆盖。** 前台定稿后装填 Search Terms，运行下方覆盖工具，分别检查每个站点/变体的完整短语、前台位置、后台词和遗漏词。`exact_front_end_fields` 是完整词组实际出现的位置；`front_end_tokens_by_field` 只表示词元出现，不代表短语自然、不代表 Amazon 已索引。`target_reached=true` 也不代表质量通过。
5. **按缺口补查。** 优先补回尚未落位的已采用候选和被误排除的词；原始产品概念没有本地候选时先补本地化。剩余词池确实不足时，再查目标站点的其他同类标题、相关 ASIN 反查和自然别称。后台短但词池大部分已在前台覆盖时，检查产品概念是否遗漏，并记录充分补查后的不足原因；不能为填满容量引入泛词、假属性或无来源叫法。补词后重新装填和复核。
6. **每次修改重新检查。** 改标题、五点、详情或关键词后都重算覆盖。基于选定基底填写 `previous_search_terms`；有旧包时可用工具 `--previous` 对比，没有旧包则从原 Excel 相应站点/变体读出，不用空串冒充基底。检查原词是进入前台、仍在后台，还是有依据地被删除；不得仅因后台字节减少判定退步，也不得把无理由丢词视为完成。变体 ID 变更须核对真实对应关系，不猜测配对。

### 内部覆盖表

使用既有包字段直接计算，不手填一份可能过时的覆盖结果。写作中可以对草稿运行，最终交付前必须用最终包再运行：

```sh
python scripts/review_keyword_coverage.py internal/listing-package.json --out internal/keyword-coverage.json --csv internal/keyword-coverage.csv
```

已有选定版本的包时加 `--previous internal/previous-listing-package.json`。JSON 按站点/变体输出字符数、UTF-8 字节数、词池去重前后规模、候选位置、遗漏概念与历史词去向；CSV 逐条显示“完整短语｜来源｜适用理由｜前台位置｜后台词｜遗漏词｜排除原因”。报告只放 `internal/`，不改变买家 Excel 的工作表和文案。历史包对比不会修改输入；需要将核实后的历史词及删除理由同步到当前包，再运行最终校验。工具不生成新词、不证明真实来源或研究充分性，不替代 `validate_listing_package.py` 与语言/产品适用性复核。

逐站处理 `next_actions`：缺候选补研究，已采用词未落位则补前台或后台，无审核的后台词补真实审核或删除；短字段先完成上述缺口检查和真实补查，再决定留短。完整包校验会重新计算覆盖报告，不能拿早先报告批准后来改过的文案。

### 采集与异常

使用运营任务注入的卖家精灵账号和带 Playwright 的 Python 运行 `scripts/collect_sellersprite_keywords.py --request US:B012345678 --out internal/sellersprite-keywords.json`，按实际站点和 ASIN 改参数，可重复 `--request`。服务器当前可用 `/home/ubuntu/chenyu/chenyu-crawler/.venv/bin/python`。未发现账号先核对任务环境与管理员配置的凭据注入状态，不直接跳过；共享浏览器与登录失败处理遵守入口 Skill 的会话规则。

页面或网络失败可重试查询并补查同站点竞品；登录失败停止自动提交密码。美国站数据只作欧洲站语义候选，不声称当地搜索量。已有真实标题/反查来源和产品事实时可以采用准确 AI 本地化词继续交付；仅当缺乏可靠产品及来源依据时暂停受影响站点的 Search Terms，说明具体缺口。不在 Excel 写臆测词或“待验证”。

## 原词 → 本地候选 → 搜索证据

1. 收集全部有效参考标题和卖家精灵真实反查中的相关产品短语，保留原词、来源 ASIN、站点与语言。不能只取第一条标题或一个反查词就停止。优先自然搜索词；其他流量类型保留原标签，确认本品适用性后也可贡献候选，不把广告流量说成自然流量。
2. 用 AI 将英文或其他外语原词翻译、改写为目标站点的自然商品称呼，兼顾当地同义称呼和具体长尾组合。同一原词可生成多个语义成立的候选，分别审核；不要只逐字翻译，也不要添加原词及本品事实没有的结构、材质、用途或人群。当地买家确实使用的借词可以保留，需记录当地使用依据。
3. 以完整短语是否准确描述本品为主；当地搜索只辅助核对有歧义的叫法，不要求每个候选搜索或搜满 20 条，不以 70%/40% 集中度筛词。已执行搜索时保留实际查询词与证据文件/URL。不要把英文原词在法国站的低匹配率当作法语翻译词的结果，不能把未查询计为 0 个相关结果。来源为 US 不代表没有可用法语词；缺少 FR 搜索量只意味着不能声称 FR 搜索量，不是排除理由。
4. 对完整候选短语判定产品相关性和具体程度，再做前台去重。譬如英文 `deer antler headband` 可先生成法语 `serre tête bois de cerf`，再根据产品和当地证据考虑其他自然称呼；示例须根据实际产品和来源确认适用性，不要求逐个长尾通过搜索集中度门槛。不能用单独的 `chevreuil` 的搜索结果代替完整产品短语的核查。
5. 高相关候选按新增检索叫法和适用性排序，写入前台未覆盖的词元。目标 240–249 UTF-8 字节；不得为了后台词数删掉前台有价值内容，也不得靠泛词、重复单复数或生硬同义改写填满。

## v4 记录与交付检查

新生成、重做和重新交付的包设置 `search_term_policy_version=4`。命令行与 Python `validate()` 默认均拒绝旧版本；历史数据只可显式用 `validate(..., require_current_search_policy=False)` 诊断，不能把兼容检查当作新交付验收。

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
- 排除词必须逐项写 `exclusion_reason` 和具体 `exclusion_detail`。原因只允许 `front_end_covered`（翻译后的全部有效词元已被前台覆盖）、`product_mismatch`（具体结构/用途不符）、`low_relevance`（语义或购买意图确实偏离本品，不能仅因结果占比低）、`byte_limit`（确实放不下）。不得仅写“英文词”“没有本地搜索量”或统一套用“已覆盖或不相关”。前台去重不能在英文原词上进行。

## 少于 240 字节时

继续补查并保留 `search_term_expansion.queries`、`shortfall_reason`，还要列出 `reviewed_phrases`，与该站点/变体全部候选审核中的目标语言 `phrase` 一一对应。`title_candidate_audit.all_user_references` 保存全部有效用户参考 ASIN；每个 ASIN 必须有对应的标题翻译候选或具体排除记录，不能只用首链接代表全部参考。

逐条核实被排除的本地候选及证据，尤其检查翻译后仍有新增词却被标为前台已覆盖的情况。短字段可以是充分研究后的真实结果，但一句笼统说明不构成研究完成。不得为通过字段校验捏造补查、翻译或搜索统计，也不得把旧任务的少词结果原样填几个新字段就重新交付。

## v4：先保留产品概念，再翻译和选词

从每条有效标题及相关反查词中分别提取产品称呼、结构/形状、主题/图案、风格和适用属性，不把含多个有效概念的长句压成一个通用品名。只提取来源实际包含且适用于本品的维度，不凑固定类别或数量。`Big Candy Hoop Dangle Earrings` 中的圈形、糖果主题和垂挂是不同概念；翻译成“圈形耳环”不算覆盖了其他概念。

顶层 `search_term_concepts` 保存 `{id, source_phrase, meaning}`，每项对应一个最小有用概念；所有站点/变体的审核项用 `concept_id` 关联，每个概念都须有目标语言候选或明确排除决定。一个概念可以贡献多个自然的当地同义称呼；AI 翻译成立且产品适用即可，不要求每个同义表达另有当地标题逐字命中。先完成这个词池，再做前台去重；前台覆盖了“耳环”，不意味着“糖果主题耳环”中的主题词也已覆盖。

### 相关性分两类依据

- `relevance_basis=organic_results`：按真实当地搜索记录数量与比例，high/medium/low 仅描述集中度，不控制采用。只要短语准确描述本品且来源明确，低比例仍可采用；比例不代表搜索量。
- `relevance_basis=source_product_match`：这是无需额外当地搜索的常用路径：真实参考原词及本品事实支持的产品称呼、主题、结构和自然同义表达都可以采用，不限于少数特殊长尾。保存 `relevance_fact_ids`、`source_evidence`、`product_match_reason`、`specificity=product_specific` 和 `local_volume_claimed=false`。需说明完整短语如何准确描述本品，不能只绑定一个事实编号。
- 搜索结果明确指向另一产品/用途时不可通过第二类依据强行采用。`search_intent` 只允许 `same_product` 或 `not_measured`；已搜索则保留真实统计，不能为了过关改数。未做当地搜索则 `relevance_band=not_measured`，数量留 null，不声称“前20条已核实”或当地高流量。
- 第二类依据允许对已确认的条纹、糖果主题、扭转等具体概念进行自然本地化，不意味着允许写来源没有的属性，可用 AI 扩展自然同义词，不要求每个表达在来源中逐字出现。

### 完整研究与重做对比

先从原始搜索文件自动生成查询清单，避免只检查最终选中的候选：

```sh
python scripts/collect_search_query_inventory.py internal --out internal/query-inventory.json
```

把结果原样写入顶层 `search_query_inventory`。每条已保存的当地查询必须有对应审核，或在 listing 的 `search_query_exclusions` 写 `{query, reason, detail}`；原因使用 `front_end_covered`、`product_mismatch`、`low_relevance`、`byte_limit` 或 `invalid_capture`，明确具体排除依据；集中度低本身不构成排除依据。不能只留一个“其余不相关”的总说明。原始文件不采用工具格式时先转换事实记录，不能留空清单掩盖已执行的查询。

重做时把原版词填入每条 listing 的 `previous_search_terms`，逐词检查：仍适用的保留，已进入前台的去重，不再适用的在 `previous_term_exclusions` 中记录 `{term, reason, detail}`（原因 product_mismatch/low_relevance/byte_limit）。同时检查原版完整短语的概念，不能只换一组同义词就声称“扩词完成”。输出内部对比包含原字节数、新字节数、新增词与有理由删除词；有价值的来源尚未处理时继续补查，而不是宣布无法达到长度目标。

### 接近字节上限的装填

候选先按本品匹配程度、来源和新增检索价值排序，交给 `scripts/pack_search_terms.py`。输入 JSON 为 `{"marketplace":"FR", "front_end":"全部前台文字", "candidates":["已审核的完整短语"]}`；运行 `python scripts/pack_search_terms.py internal/packing-input.json --out internal/packing-result.json`。工具按 UTF-8 计算，删除前台词、停用词和重复词，某短语放不下时继续尝试后续较短短语，避免提前停止。它只负责装填，不能替代词义审核；将采用/排除结果同步到审计，按实际词元生成中文翻译。

默认持续扩充到 240–249 字节；尚有空间时优先补齐主题、图案、造型、当地品名和相关长尾，不限定每个来源只翻译出一个叫法。若未达到目标，检查是否误删原版有效词、漏审搜索文件或把多个来源概念压缩成通用品名，再补充词池。只有确实没有更多准确增量词时才说明剩余空间，不用不相关的词硬填。
