# 分析脚本接口

两个脚本使用 Python 3.10+ 标准库，无第三方依赖。路径相对当前 Skill 目录；实际执行时解析绝对路径，输入输出使用独立任务目录。不得把真实开发表写入插件。

```bash
python scripts/extract_development_brief.py "input.xlsx" --out "task/brief"
python scripts/analyze_listing.py "task/analysis-input.json" --out "task/review.json"
```

提取器保留原始单元格及公式缓存（缓存可能过期），不执行公式；文字链接、真正超链接、常量 HYPERLINK 均保留来源。动态 HYPERLINK 只警告，需助手根据单元格证据补读。媒体原样导出，图片锚点为1起始行列；附件只清点，WPS单元格图片等不支持的对象发出警告。未知图片不自动归属变体。输出目录须为空。

分析输入示例（虚构数据，仅说明接口）：

```json
{
  "competitors": [
    {"id":"C1","marketplace":"DE","product_group":"P1","status":"partial","url":"https://example.com/item","retrieved_at":"2026-01-01","title":"Baumschmuck aus Papier","bullets":[],"description":""}
  ],
  "keywords": [
    {"marketplace":"DE","phrase":"Baumschmuck","aliases":[],"type":"product","decision":"adopt","fact_source":"自有产品身份"}
  ],
  "listings": [
    {"marketplace":"DE","variant_id":"V1","title":"Baumschmuck aus Papier","bullets":["...","...","...","...","..."],"description":"实际四段式纯文本","search_terms":"..."}
  ],
  "brands": [],
  "limits": {}
}
```

站点仅 DE/FR/IT/ES/UK，status 使用 complete/partial/failed。product_group 由研究证据确定，不由脚本猜测。aliases 必须经过语义判断。brands 填入已知自有与竞品品牌以检查泄漏，不用于生成文案。

limits 默认空：仅在核实规则后填入站点下的 title_chars / search_terms_bytes，并在任务记录保留官方来源、类目和查询日期。脚本报告未核实项，不内置通用限制。

输出包含原词/语义组覆盖数、各字段样本分母、证据位置、精确覆盖、长度和重复片段。无语义审核、自动翻译、事实推断或发布能力；品牌候选及8词重合须人工语义复核。来源缺失不可伪造，完整性及事实审核由 Skill 执行。review.json 已存在时拒绝覆盖。
