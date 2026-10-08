# 晨玙 Amazon 运营插件

`chenyu-yunying` 从产品资料和订单资料生成运营交付文件。当前版本见 [plugin.json](plugin.json)。

## 能力

| Skill | 职责 | 交付 |
| --- | --- | --- |
| [运营总入口](skills/chenyu-yunying/SKILL.md) | 根据需求协调专业能力，统一产品事实和变体 | Listing、作图要求或订单商业发票 |
| [竞品研究](skills/chenyu-jingpin/SKILL.md) | 按站点／ASIN 获取标题、五点、普通／A+描述与图片证据 | 共用研究包；网站不单列任务入口 |
| [Listing](skills/chenyu-listing/SKILL.md) | 结合确认的自有事实与竞品证据写本地化内容 | 默认 DE／FR／IT／ES 四站 Listing，UK 按需加入 |
| [作图要求](skills/chenyu-zuotuyaoqiu/SKILL.md) | 明确图号、变体、画面、准确文案、参考图和验收条件 | 含嵌入参考图片的作图 Excel |
| [订单商业发票](skills/chenyu-invoice/SKILL.md) | 核对 Amazon.fr EUR 订单并填入固定 PDF 母版 | 按订单编号命名的商业发票 PDF |

## 业务流程

开发 Excel／素材 → 提取产品事实 → 获取一次竞品研究包 → 分别生成 Listing 与作图要求 → 检查事实、变体、语言和交付一致性。

- 竞品提供研究证据，不能直接变成自有产品事实。是否可以补充同款信息，按专业 Skill 的同款确认与来源要求执行。
- Listing 与作图要求默认分别交付独立 Excel，共享产品事实，不共用成品文案；网站按独立文件验收。
- 作图要求负责规划和交接，实际出图由美工插件完成。
- 买家订单 PDF 属于运营；箱唛照片生成承运商 `.xls` 属于 [物流插件](../chenyu-wuliu/README.md)。

## 规则入口

| 文件 | 内容 |
| --- | --- |
| [LISTING_RULES.md](LISTING_RULES.md) | Listing 写作与校验规则 |
| [开发资料说明](references/kaifawendang.md) | 自有产品输入和事实边界 |
| [交付边界](references/deliverable-boundaries.md) | Listing 与作图要求的职责划分 |
| [交付母版](references/delivery-master.md) | Excel 母版与工作表组织 |
| [Listing 分析合同](skills/chenyu-listing/references/analysis-contract.md) | 工作包、证据和验证字段 |
| [作图 Excel 交付](skills/chenyu-zuotuyaoqiu/references/excel-delivery.md) | 图片规划、参考图和输出结构 |
| [PDF 发票字段](skills/chenyu-invoice/references/order-fields.md) | 订单字段与生成前验证 |

README 不重复写具体字符数、文案规则或模板字段；执行时读取相应 Skill 和以上规则，避免多份标准漂移。

## 脚本

以下路径相对 `skills/`：

| 脚本 | 用途 |
| --- | --- |
| `chenyu-yunying/scripts/extract_development_brief.py` | 提取开发 Excel 的文字、链接、图片与附件清单 |
| `chenyu-jingpin/scripts/fetch_competitor_listings.py` | 抓取受支持的 Amazon 公开商品页面与图片；失败保留状态 |
| `chenyu-listing/scripts/analyze_listing.py` | 分析关键词、字段长度和重复片段 |
| `chenyu-listing/scripts/validate_listing_package.py` | 核对 Listing 工作包与产品事实、证据和交付合同 |
| `chenyu-zuotuyaoqiu/scripts/validate_image_brief_boundaries.py` | 校验作图要求边界与必要证据 |
| `chenyu-yunying/scripts/split_delivery_workbooks.mjs` | 使用 Node.js／artifact-tool 拆分已填充运营母版 |
| `chenyu-invoice/scripts/generate_invoice.py` | 使用 PyMuPDF 填写商业发票 PDF |

PDF 依赖见 [requirements.txt](skills/chenyu-invoice/scripts/requirements.txt)。网页访问受限或字段缺失时记录原因，不用搜索摘要补造商品事实。

## 输出与边界

见 [输出目录规范](references/output-paths.md)，分别保存研究资料、Listing、作图要求和订单 PDF。真实业务资料不进入源码或分发包。

不自动发布 Listing、不修改店铺、不执行广告投放。安装、测试与发布使用仓库根 README 的统一流程。
