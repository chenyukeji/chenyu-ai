# 晨玙 Amazon 开发插件

`chenyu-kaifa` 包含一个总入口和两个专业 Skill。当前版本见 [plugin.json](plugin.json)。

## 能力

| Skill | 输入 | 交付 |
| --- | --- | --- |
| [开发总入口](skills/chenyu-kaifa/SKILL.md) | 自然语言需求、已确认产品和选品资料 | 自动选择选品、开发文档或两者，复用已有证据 |
| [选品分析](skills/chenyu-xuanpin/SKILL.md) | 类目、站点、选品条件或真实候选数据 | 按调研优先级排序的开品 Excel |
| [开发文档](skills/chenyu-kaifawendang/SKILL.md) | 已确认的产品、竞品、供应商、变体和图片 | 每个产品一个三表工作簿，同产品变体保留在详情表 |

## 选品策略和状态

| 策略 | 当前实现 |
| --- | --- |
| E 新品榜发现 | 采集美国、德国新品榜 ASIN，再按 ASIN 补充卖家精灵数据；未明确策略时默认使用 |
| J 近期 FBM 机会 | 卖家精灵独立筛查近 60 天上架、FBM 且满足销量条件的商品；逐项检查资格并标注热销原因证据 |
| H 历史季节性 | 卖家精灵回看去年同期当月及随后 2／3 个月的销量飙升记录；提供采集与分析路径，依赖有效账号 |
| I 店铺上新跟踪 | 导入前后两次店铺快照，第一次用于建立基线 |
| C 搜索热词机会 | 导入搜索词、搜索量、周期及关联 ASIN |
| K 排名跃升发现 | 导入此前排名、当前排名及统计窗口 |
| A 同类中国卖家现货 | 导入真实候选资料分析 |
| B 近期需求、D 评论痛点、F 组合比较 | 保留策略定义，尚不可执行 |

策略状态唯一来源为 [runtime-rules.json](skills/chenyu-xuanpin/references/runtime-rules.json)。输入字段和历史窗口见 [六种策略](skills/chenyu-xuanpin/references/six-strategies.md)；自定义类目见 [类目说明](skills/chenyu-xuanpin/references/custom-categories.md)。

## 处理流程

`run.py` 解析要求 → 策略路由 → 候选采集／导入 → 卖家精灵补数 → 去重与证据检查 → 评分 → Excel。

- 浏览器由 Python/Playwright 驱动，不依赖 Browser MCP。依赖见 [requirements-browser.txt](requirements-browser.txt)，使用前需安装 Chromium。
- 凭据由执行环境提供，不写进源码或任务文件。登录未确认、补数不足或页面不可访问时保留原因，不生成冒充完成的结果。
- 缓存和续跑支持复用同一运行目录，也可显式刷新补数。
- 可只读消费独立采集器的 `new_releases.db`，分析最新日、历史出现和排名信号；见 [历史数据库说明](skills/chenyu-xuanpin/references/new-releases-db.md)。不修改采集器数据库。
- E 与 J 的候选来源和分析路径不同；当前不支持将它们混成多策略并行自动采集。
- 图片嵌入 Excel。评分表示调研优先级，不能视为已验证的销量预测或开发承诺。

## 开发文档

每个产品文件保留参考产品调研、产品确认和产品详情三张工作表，图片嵌入，多个变体留在同一文件；结构由 [格式合同](skills/chenyu-kaifawendang/references/format-contract.md) 和 `validate_development_workbooks.py` 校验。

报价、成本和采购数量只整理用户已有事实，不执行供应商比较、议价、利润核算、下单、试销、Listing 或广告。

## 当前限制与输出

I/C/K 尚无专用实时采集器。采集覆盖依赖站点和账号；站外流量、创新原因及未提供的评论事实不能自动推定。类目来源、评分阈值和字段证据仍需按实际业务核对。

选品与开发文档分别保存到 `product-discovery` 和 `product-development`，见 [输出目录规范](references/output-paths.md)。业务输出不进入插件源码。测试入口见仓库根 README。
