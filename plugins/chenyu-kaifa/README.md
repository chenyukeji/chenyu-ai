# 晨玙 Amazon 开发插件

插件名称为 `chenyu-kaifa`，当前包含两个专业 Skill：

| Skill | 用途 | 主要输出 |
| --- | --- | --- |
| `chenyu-xuanpin` | 找品、补数、评分和开品判断 | 按得分降序的开品结果 Excel |
| `chenyu-kaifawendang` | 把已确认产品、竞品、供应商、变体和图片整理成开发文档 | 每个产品一个三表开发 Excel |

当前版本：`1.2.1`。已完成的能力和后续待办见 [STATUS.md](STATUS.md)。

输入自然语言选品要求后，插件自动识别找品策略。用户没有说明策略时默认使用 E，从 Amazon 美国站和德国站新品榜获取 ASIN，再通过卖家精灵按 ASIN 补充数据，分析评分并生成按得分降序的 `开品结果.xlsx`。

明确选择 J 时，从卖家精灵“选产品”独立筛查近60天上架、FBM 配送且达到最低预估月销量的商品，不以 Amazon 新品榜作为候选来源。J 输出各商品的资格证据和近期火爆原因；低价、季节性、站外流量、功能创新、变体数量会逐项标注观察证据或待验证，不能把相关性写成因果关系。

卖家精灵补数现在独立运行：实时榜单、历史 JSON 和续跑任务中的 ASIN，只要缺少上架日期、Review、售价、BSR、所在品类、预估月销量或图片，都会自动查询并回填。可用 `enrich_sellersprite` 对已有运行目录强制补数。

六种策略的使用方式、历史月份窗口和导入字段见 [六种选品策略](skills/chenyu-xuanpin/references/six-strategies.md)。H 新增卖家精灵去年同期及随后 2～3 个月的销量飙升分析；I/C/K 支持真实证据导入，尚无专用自动采集器。

## 示例

```json
{
  "skill_action": "run_discovery_flow",
  "request": "针对玩具类目的派对用品找新品"
}
```

J 示例（与新品榜无关）：

```json
{
  "skill_action": "run_discovery_flow",
  "request": "寻找近60天 FBM 热销商品并分析火爆原因",
  "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
  "discovery": {"j_min_monthly_sales": 100, "j_keyword": "kitchen"}
}
```

`j_keyword` 可省略；省略时按所选站点全品类筛查。当前仅 J 单策略独立执行，不能与 E 组合自动采集。

派对用品已内置以下新品榜节点：

- US：Toys & Games > Party Supplies
- DE：Spielzeug > Partyzubehör

## 输出

- 原始请求和策略识别结果。
- E 的 Amazon US/DE ASIN 清单，或 J 的卖家精灵选产品原始结果与资格审核。
- 卖家精灵按 ASIN 补充的数据。
- 去重候选池。
- 100分制评分明细。
- 按得分降序的开品 Excel。

E 的 Excel 列结构参考业务现有开品表，包含站点、上架日期、Review、售价、BSR、品类、月销量、中文优缺点、生命周期、ASIN、链接、图片、结论和理由。内部得分只用于降序排序，表格结论显示“强开、开、条件开、偏弱、观察、不建议”。J 在原有15列后追加原文标题、FBM资格证据和近期火爆原因。图片直接嵌入 Excel；“缺点”是产品本身的不足或评论痛点；“生命周期”是全年或具体可售月份。

默认任务目录为 `outputs/chenyu-kaifa/product-discovery/YYYY-MM-DD_产品简称/`。同一天同名的新任务追加 `_02`、`_03`；续跑时显式传入原 `run_dir`，不覆盖其他运行结果。详细规则见 [输出目录规范](references/output-paths.md)。

## 产品开发文档

`chenyu-kaifawendang` 负责把已经选定或确认的产品资料整理成公司现有开发文档格式。一次输入多个产品时，每个产品独立生成一个工作簿；同一产品的颜色、尺寸、数量和图案变体保留在该产品文件的详情表中。

每个开发工作簿固定包含：

1. `参考产品信息调研`：站点、价格、排名、销量、ASIN、Amazon 链接和嵌入参考图。
2. `产品确认`：产品图、成本、重量、交期、供应商、采购链接、首单数量和变体情况。
3. `产品简称`：各变体的价格/克重、供应商产品名称或图片、内容清单、产品属性和自有产品图。

开发文档使用插件内的去业务数据母版，产品图和供应商图直接嵌入 Excel。默认输出目录为 `outputs/chenyu-kaifa/product-development/YYYY-MM-DD_批次简称/`，同一批次的多个产品文件放在同一目录，但不合并成一个工作簿。

## 浏览器

采集使用插件内部 Python/Playwright，不使用 Browser/Playwright MCP。依赖安装：

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
```

卖家精灵账号由本地环境变量 `CHENYU_SELLERSPRITE_USERNAME` 和 `CHENYU_SELLERSPRITE_PASSWORD` 提供；不要写入源码或任务文件。 J 会先检查账号身份；若当前会话是游客且两个变量可用，会在同一浏览器会话中自动登录并核验，再开始筛选。已缓存的部分采集结果会重新采集，避免恢复登录后仍沿用游客结果。

卖家精灵单条 ASIN 查询默认最多等待 8 秒；正常命中、查询请求完成但无匹配，或页面明确返回空结果时都会立即进入下一条。每条查询在原始结果中记录实际耗时和结束原因，普通续跑会跳过已经确认查不到的 ASIN。

## 当前边界

`chenyu-xuanpin` 只做选品与分析。`chenyu-kaifawendang` 可以整理用户已提供的供应商报价、采购数量和产品资料，但不负责供应商比较、议价、采购决策、利润核算、下单、试销、Listing、作图要求或广告。
