# 晨玙 Amazon 开发插件

`chenyu-kaifa` 包含一个总入口和三个专业 Skill。当前版本见 [plugin.json](plugin.json)。

## 能力

| Skill | 输入 | 交付 |
| --- | --- | --- |
| [开发总入口](skills/chenyu-kaifa/SKILL.md) | 自然语言需求、已确认产品、1688链接和选品资料 | 自动选择选品、供应商采集、开发文档或组合，复用已有证据 |
| [选品分析](skills/chenyu-xuanpin/SKILL.md) | 类目、商品链接、店铺链接、条件或真实候选数据 | 商品机会、关键词趋势、季节性和来源覆盖 Excel |
| [开发文档](skills/chenyu-kaifawendang/SKILL.md) | 已确认的产品、竞品、供应商、变体和图片 | 每个产品一个三表工作簿，同产品变体保留在详情表 |
| [供应商采集](skills/chenyu-gongyingshang/SKILL.md) | 1688链接＋目标属性、已授权领星会话 | 供应商名称、匹配规格/图片/报价/库存、主图及开发事实包 |

## 单一选品入口

选品只需 `chenyu-xuanpin`。自然语言、商品链接和店铺链接使用 [统一选品流程](skills/chenyu-xuanpin/references/unified-selection.md)：

输入解析 → 站点及目录核实 → 多来源采集 → 商品池与关键词需求分别整理 → 相关性和证据审阅 → 含图片的五表 Excel。

- 商品链接自动读取目录，并尝试从同站新品榜首页发现大类、打开同节点榜单验证；找不到时记录缺项。
- 店铺链接读取实际可见商品，区分卖家目录和品牌展示页；样本不冒充完整店铺快照。
- 类目查询结合 Amazon 新品榜、卖家精灵研发新品榜、当前及去年同期后2～3个月飙升榜、关键词历史和数据库。
- 卖家精灵产品筛选使用词组匹配；仍需模型审阅用途。关键词按完整月计算环比/同比，历史销量与当前销量分开。
- 数据库只按实际覆盖的类目或 ASIN 查询；父类覆盖不能视为细类已收录。
- 提问示例见 [统一流程中的提问格式](skills/chenyu-xuanpin/references/unified-selection.md#提问格式)。

## 独立策略和状态

以下注册表用于明确调用旧的 `run_discovery_flow`；综合任务使用上面的统一入口。

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

## 独立策略处理流程

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

供应商采集可以独立使用或衔接开发文档。首次由用户完成领星登录与二次验证，之后复用受保护本机会话；只解析、不保存配对或新增供应商。模糊属性返回候选待确认，不猜规格。依赖Node.js、Playwright和Chrome；命令及字段见 [采集接口](skills/chenyu-gongyingshang/references/collector.md)。服务器/网站执行器需接入可交互浏览器及已授权会话，不承诺无人值守登录。

## 当前限制与输出

独立 I/C/K 策略仍使用导入接口；统一入口已支持店铺可见样本和关键词实时查询，尚未实现自动定期全店跟踪及 K 实时排名跃升采集。采集覆盖依赖站点和账号；站外流量、创新原因及未提供的评论事实不能自动推定。类目来源、评分阈值和字段证据仍需按实际业务核对。

选品、开发文档与供应商资料分别保存到 `product-discovery`、`product-development` 和 `supplier-data`，见 [输出目录规范](references/output-paths.md)。业务输出不进入源码。供应商测试执行 `node --test tests/test_supplier_collector.cjs`，其余测试见仓库根 README。
