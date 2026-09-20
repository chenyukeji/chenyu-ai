# 晨玙 Amazon 开发插件

插件名称为 `chenyu-kaifa`，当前只包含一个选品 Skill：`chenyu-xuanpin`。

当前版本：`1.0.0`。已完成的能力和后续待办见 [STATUS.md](STATUS.md)。

输入自然语言选品要求后，插件自动识别找品策略。用户没有说明策略时默认使用 E，从 Amazon 美国站和德国站新品榜获取 ASIN，再通过卖家精灵按 ASIN 补充数据，分析评分并生成按得分降序的 `开品结果.xlsx`。

卖家精灵补数现在独立运行：实时榜单、历史 JSON 和续跑任务中的 ASIN，只要缺少上架日期、Review、售价、BSR、所在品类、预估月销量或图片，都会自动查询并回填。可用 `enrich_sellersprite` 对已有运行目录强制补数。

## 示例

```json
{
  "skill_action": "run_discovery_flow",
  "request": "针对玩具类目的派对用品找新品"
}
```

派对用品已内置以下新品榜节点：

- US：Toys & Games > Party Supplies
- DE：Spielzeug > Partyzubehör

## 输出

- 原始请求和策略识别结果。
- Amazon US/DE ASIN清单。
- 卖家精灵按 ASIN 补充的数据。
- 去重候选池。
- 100分制评分明细。
- 按得分降序的开品 Excel。

Excel 列结构参考业务现有开品表，包含站点、上架日期、Review、售价、BSR、品类、月销量、中文优缺点、生命周期、ASIN、链接、图片、结论和理由。内部得分只用于降序排序，表格结论显示“强开、开、条件开、偏弱、观察、不建议”。图片直接嵌入 Excel；“缺点”是产品本身的不足或评论痛点；“生命周期”是全年或具体可售月份。

## 浏览器

采集使用插件内部 Python/Playwright，不使用 Browser/Playwright MCP。依赖安装：

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
```

卖家精灵账号可保存在仓库根目录 `.chenyu-secrets/sellersprite.json`。该目录已被 Git 忽略，输出不会回显密码。

## 当前边界

当前只做选品与分析，不处理供应商报价、利润、采购、试销、Listing 或广告。
