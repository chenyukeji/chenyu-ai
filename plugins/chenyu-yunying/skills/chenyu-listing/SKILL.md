---
name: chenyu-listing
description: 从开发 Excel、自有产品事实和统一竞品研究包生成欧洲站 Amazon Listing，默认覆盖德国、法国、意大利和西班牙，英国站按需加入。生成 75 字符 Item Name、125 字符 Item Highlights、高信息量五点、HTML 详情和增量 Search Terms；不负责商品发布。
---

# 晨玙欧洲站 Listing

先读取 [开发文档读取规范](../../references/kaifawendang.md)。需要生成文件时再读取 [输出目录规范](../../references/output-paths.md)，本 Skill 使用 `listing` 交付部分。

开始写作前必须读取插件根目录的 [Listing 规则](../../LISTING_RULES.md)，并按需读取：

- [写作与审核](references/writing-and-review.md)：生成或修改任何 Listing 时读取。
- [欧洲站本地化](references/europe-localization.md)：涉及 DE/FR/IT/ES/UK 任一站点时读取。
- [分析脚本接口](references/analysis-contract.md)：形成、校验或分析 `listing-package.json` 时读取。

## 完成条件

竞品链接、关键词和分析结果只是中间证据。正常完成必须为每个目标站点和在售子体交付 Item Name、Item Highlights、五点、HTML 详情和 Search Terms，并通过事实、格式、长度、变体和语言复核。只有缺少会导致错误产品身份、规格、件数或变体混用的关键事实时才暂停。

本 Skill 不抓取竞品网页。没有 `competitor-research.json` 时，先执行 [竞品研究 Skill](../chenyu-jingpin/SKILL.md)。不登录或发布 Amazon 商品。

## 工作流

1. 确认目标站点、产品身份、售卖数量和变体。用户未限定站点时默认 DE、FR、IT、ES；UK 仅按需加入。只有开发资料或用户确认的自有品牌才能使用品牌。
2. 解析开发 Excel，建立名称、材质、尺寸及测量部位、颜色/图案、结构、包装内容和变体记录，每项保留来源及 `confirmed/unconfirmed/conflict` 状态。
3. 若用户、采购资料或产品证据确认第一条竞品链接为同款，把该 ASIN 设为主要同款参考。开发资料未展开的功能、材质表现、适用范围、安装、清洁、收纳和使用效果可采用“同款确认＋具体竞品点位”作为事实；仍排除品牌、冲突规格/数量/配件、认证、质保、售后和竞品独有版本。未确认同款时，竞品只提供关键词与表达思路。
4. 按站点建立关键词表。Item Name 使用 2–4 个真实核心词；Item Highlights 承接标题放不下的核心/长尾词、规格、结构和场景；五点与详情自然覆盖关键词，不对前台字段执行机械去重。
5. Search Terms 最后生成。候选必须同时来自卖家精灵反查主要同款 ASIN，以及全部有效参考链接标题中的产品词、同义词和长尾词；两类候选都在对应 Amazon 站点检查前 20 个自然结果：同类占比不低于 70% 为高相关，40%–69% 为中等相关，低于 40% 通常排除。最终使用全部已采用且前台未覆盖的有效增量词。美国站数据用于欧洲站时只作为语义候选，不声称当地搜索量。
6. 为每个站点/子体生成：68–75 字符 Item Name（目标 70–75）、不超过 125 字符 Item Highlights（目标 115–125）、严格五条且每条正文超过 200 字符的五点、规定结构的 HTML 详情，以及不超过 249 UTF-8 字节的 Search Terms。
7. 为 Item Name、Item Highlights、每条五点、详情和 Search Terms 写简短来源；形成 `listing-package.json`，运行 `validate_listing_package.py` 和 `analyze_listing.py`，再进行语言、数字、单位、事实、变体及同款证据语义复核。
8. 仅在 `ready_for_delivery=true` 且语义审核通过后交付。
9. 为每个目标站点字段生成完整中文翻译，供中国卖家核对。翻译不得新增原文没有的事实、承诺或使用范围；目标站点原文修改后同步更新中文列。

## 写作关键约束

- Item Name 最多 75 字符，数量大于 1 时本地化数量短语紧贴第一个核心产品词；关键差异按购买重要度前置。主要场景可选，不用 `/` 堆场景。
- Item Highlights 必填且最多 125 字符，用自然句补足关键词、规格、结构和多个场景。
- 五点使用“相关 Emoji＋【本地语言利益点标题】＋2–4 句正文”；只计正文时每条必须超过 200 个可见字符。
- 详情使用 `<p>`、`<br>`、`<b>`，依次包含 2–3 句概述、3–5 项详细编号功能、参数、可选使用/保养、包装和可选注意事项。
- 关键差异、重要尺寸、核心关键词和主要场景可在前台字段自然重复。标题负责识别，Item Highlights 负责补足，五点负责解释，详情负责完整展开。
- Search Terms 必须全部小写、单行、单空格、无标点、无品牌和 ASIN；删除 Item Name、Item Highlights、五点、详情及其他已填属性已经覆盖的词。
- `Design A/B/C`、`Diseño A`、`Variante A` 等内部变体编号不得进入任何买家可见字段；只有用户确认的公开变体名称可写入 `buyer_visible_variant_terms` 后保留。内部编号只能出现在运营表头或参考列。

## 交付

默认在对话中按以下顺序提供可复制内容：

1. 产品信息核对与来源
2. 父体标题，仅在关系与变体主题已核实时提供
3. 子体 Item Name
4. Item Highlights
5. 五点 1–5
6. HTML 详情
7. Search Terms

用户要求 Excel 时生成独立副本，不覆盖开发原文件，并读取 [运营交付大母版](../../references/delivery-master.md)。默认仅建立“产品内容”和用户要求的各目标站点 Listing 工作表；同站点多变体并列。每个变体按“目标站点文案、中文翻译、参考”三列成组，Item Name、Item Highlights、五点1–5、HTML 详情和 Search Terms 均提供完整中文翻译。字符和字节限制只检查目标站点文案，不计算中文翻译。产品内容页统一使用“产品名称、产品图片、产品尺寸、产品材料、产品规格、补充信息”六列并嵌入经确认属于自有产品的图片。不得用竞品图替代自有图，也不默认增加关键词、审核说明或内部分析工作表。

交付前核对每项客观宣称均可追溯、变体不混用、单位正确、内部采购信息未泄漏，且买家文案不包含竞品身份或内部审核语言。
