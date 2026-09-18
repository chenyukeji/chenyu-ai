# 晨玙 Amazon 运营插件

`chenyu-yunying` 是面向 Amazon 运营岗位的独立插件。它从产品开发文档、自有产品事实、产品素材和竞品链接出发，完成竞品研究、欧洲五站 Listing 和逐图作图要求。当前版本为 `0.8.2`。

插件不登录或修改 Amazon 店铺，不自动发布 Listing，不执行广告投放，也不会把真实开发表、竞品快照、图片或任务输出写入插件源码和分发包。

## 当前包含什么

| Skill | 适合什么需求 | 主要输入 | 主要交付 | 不负责 |
| --- | --- | --- | --- | --- |
| `chenyu-yunying` | 不确定该用哪个能力，或同时需要 Listing 和作图要求 | 开发表、素材、目标站点、自然语言要求 | 统一产品事实并协调下面三个专业 Skill | 后台自动调度、广告投放、商品发布 |
| `chenyu-jingpin` | 抓取和整理竞品资料 | 开发表中的链接或单独提供的 Amazon 商品链接 | 标题、五点、普通/A+描述、主图/图册/A+图片及 `competitor-research.json` | 生成自有 Listing、复制竞品图片、抓品牌故事 |
| `chenyu-listing` | 生成欧洲站自有产品 Listing | 自有产品事实、目标站点、竞品研究包 | DE/FR/IT/ES/UK 无品牌标题、五点、四段式详情、关键词和 Search Terms | 抓取网页、发布商品 |
| `chenyu-zuotuyaoqiu` | 生成交接美工的逐图方案 | 自有事实、产品素材、可选 Listing 与竞品视觉证据 | 每张图的目的、构图、文案、素材对应和验收条件 | 实际生成或精修图片 |

其中：

- Listing 标题统一为“3 个核心关键词＋主要场景”。三个词必须以原词或已确认的相似表达融入五点。
- 五点统一为“Emoji＋【本地语言小标题】＋2—3 句正文”。
- 详情统一为“产品概括、3—5 条特征、产品参数、包装内容”，默认纯文本。
- 同一任务中的竞品链接只抓取一次，Listing 和作图要求复用同一个研究包。

## 工作流程

```text
开发表、产品素材、目标站点
            ↓
解析工作表、超链接、图片锚点和附件
            ↓
建立自有产品事实与变体记录
            ↓
chenyu-jingpin 抓取一次竞品 Listing 与图片
            ↓
competitor-research.json
       ┌────┴────┐
       ↓         ↓
chenyu-listing  chenyu-zuotuyaoqiu
       ↓         ↓
自有 Listing    逐图作图要求
       └────┬────┘
            ↓
事实、变体、语言和卖点一致性检查
```

## 怎么使用

### 推荐：使用运营总入口

上传开发 Excel 和可用的自有产品素材，然后说明目标站点和需要的成果。例如：

```text
使用 chenyu-yunying，读取这份开发表里的产品信息和竞品链接，
为德国、法国站生成自有产品 Listing，并生成交给美工的逐图作图要求，不加品牌。
```

总入口会：

1. 只读解析开发文档，区分自有事实、变体、竞品链接和素材。
2. 有竞品链接时调用 `chenyu-jingpin`，只抓取一次。
3. 将同一个事实记录和研究包交给 Listing 与作图要求。
4. 核对名称、材质、尺寸、数量、变体和卖点的一致性。

### 直接使用专业 Skill

需求边界明确时可以直接指定：

```text
使用 chenyu-jingpin，抓取表格中的 Amazon 竞品 Listing、普通/A+描述和完整图片。
```

```text
使用 chenyu-listing，基于这份自有产品事实和竞品研究包生成德国站 Listing，不加品牌。
```

```text
使用 chenyu-zuotuyaoqiu，根据产品素材和已完成的 Listing 生成逐张作图要求。
```

### 建议提供的信息

- 产品开发 Excel 或已整理的自有产品事实。
- 明确的目标站点：DE、FR、IT、ES、UK 中的一个或多个。
- 产品名称、材质、尺寸及测量部位、颜色/图案、结构和包装内容。
- 每个变体是否在目标站点销售。
- 产品实拍、供应商图、版式参考及它们分别对应哪个产品或变体。
- 需要 Listing、作图要求、竞品研究，还是它们的组合。

必要事实缺失时，Skill 会列出具体待确认项；不会用竞品规格填补自有产品信息。

## 主要任务文件

任务文件应放在插件目录以外的独立输出目录，不进入 Git 或分发包。

| 文件/目录 | 作用 |
| --- | --- |
| `brief/manifest.json` | 开发表的工作表、单元格、链接、图片锚点、附件和警告 |
| `competitors/competitor-research.json` | 去重后的竞品 Listing、图片证据、抓取状态和来源 |
| `listing-package.json` | 自有事实、关键词映射、站点/变体 Listing 和引用关系 |
| `package-review.json` | Listing 完整性、格式、事实引用和站点/变体覆盖检查 |
| `content-review.json` | 关键词覆盖、长度、原词/别名位置和竞品长片段复核 |
| 作图要求文件 | 每张图的变体、目的、构图、文案、素材和验收条件 |

## 内置脚本

脚本使用 Python 3.10+ 标准库。以下路径均相对相应 Skill 目录，真实任务应使用插件外的输出目录。

```bash
# 解析开发 Excel
python skills/chenyu-yunying/scripts/extract_development_brief.py "input.xlsx" --out "task/brief"

# 抓取竞品 Listing 和图片
python skills/chenyu-jingpin/scripts/fetch_competitor_listings.py "task/brief/manifest.json" --out "task/competitors"

# 校验自有 Listing 包
python skills/chenyu-listing/scripts/validate_listing_package.py "task/listing-package.json" --out "task/package-review.json"

# 分析关键词覆盖、长度和重复片段
python skills/chenyu-listing/scripts/analyze_listing.py "task/listing-package.json" --out "task/content-review.json"
```

爬虫只访问任务提供的受支持 Amazon 商品页；遇到验证码、访问限制或字段缺失时记录 `partial/failed`，不会绕过限制或用搜索摘要补写内容。

## 目录结构

```text
chenyu-yunying/
├── plugin.json                       # 插件清单、版本和界面信息
├── README.md                         # 本说明
├── references/
│   └── kaifawendang.md               # 所有运营 Skill 共用的开发文档读取规范
└── skills/
    ├── chenyu-yunying/               # 运营总入口与 Excel 提取器
    ├── chenyu-jingpin/               # 竞品研究、爬虫和研究规范
    ├── chenyu-listing/               # Listing 写作、五站本地化和校验脚本
    └── chenyu-zuotuyaoqiu/           # 逐图作图要求
```

每个 Skill 至少包含 `SKILL.md`。按实际需要增加：

- `agents/openai.yaml`：界面名称、简短说明、默认调用示例。
- `references/`：只在该 Skill 工作时需要读取的详细业务规范或数据契约。
- `scripts/`：需要重复、确定性执行的解析、抓取或校验程序。
- `assets/`：Skill 自带并会在输出中使用的模板、图标等静态资源。

不要建立空目录，也不要把真实业务样本放进 Skill。

## 如何新增一个 Skill

### 1. 先判断是否应该建 Skill

| 需求类型 | 应放在哪里 |
| --- | --- |
| 一个边界清楚、用户可单独请求、会产生独立成果的能力 | 新建 Skill |
| 只是某个 Skill 反复使用的确定性处理步骤 | 放进该 Skill 的 `scripts/` |
| 只是详细规则、字段说明或语言规范 | 放进该 Skill 的 `references/` |
| 需要读取 Amazon、ERP、素材库等外部实时系统 | 实现 MCP，并单独设计读取/写入权限 |
| 把多个 Skills 和人工确认点串成固定业务流程 | Workflow；实现前不要建空目录 |
| 代表一个岗位选择 Workflow、Skill 和工具 | Agent；等岗位流程与权限稳定后再实现 |

### 2. 创建目录和入口文件

在 `skills/` 下使用小写连字符名称，例如：

```text
skills/chenyu-guanggao/
├── SKILL.md
└── agents/openai.yaml
```

`SKILL.md` 最小结构：

```markdown
---
name: chenyu-guanggao
description: 清楚说明该能力处理什么请求、何时使用，以及不负责什么。
---

# Skill 名称

说明输入、处理规则、完成条件、交付格式和权限边界。
```

只有真正实现后才把新 Skill 加入插件；规划中的名称不能伪装成可用能力。

### 3. 接入运营总入口

新增专业 Skill 后同时更新：

1. `skills/chenyu-yunying/SKILL.md` 的任务分配表和共享工作流。
2. 本 README 的能力表、使用示例和目录结构。
3. `plugin.json` 的版本、说明和 `capabilities`（能力确实变化时）。
4. `AGENTS.md` 的仓库路由说明（如果仓库级路由发生变化）。

共享开发文档规则放在插件根目录 `references/`；仅属于新 Skill 的规则放在它自己的 `references/`，避免重复维护。

### 4. 验证

在仓库根目录运行：

```powershell
$env:PYTHONUTF8='1'
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" "plugins\chenyu-yunying\skills\新-skill"
python -m unittest discover -s tests -v
```

至少检查：名称和目录一致、YAML frontmatter 有效、引用路径存在、脚本实际可运行、没有占位内容、没有真实产品数据、没有把尚未实现的 MCP/Agent/Workflow 写成可用能力。

## 更新现有 Skill

1. 先确认修改属于哪个专业 Skill，不把所有逻辑都堆进总入口。
2. 业务规则写入 `SKILL.md` 或对应 `references/`；可重复机械检查写入脚本。
3. 为新增的确定性行为补充测试。
4. 更新插件补丁或次版本号，并同步本 README。
5. 验证全部 Skills 和测试后再提交、推送、打包。

## 打包与安装

分发 ZIP 的根层必须直接包含：

```text
plugin.json
README.md
references/
skills/
```

不要在 ZIP 根层再套一层 `chenyu-yunying/`，也不要包含 `__pycache__`、`.pyc`、测试缓存、真实开发表、竞品图片或任务输出。

从仓库根目录用已提交版本打包：

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
git archive --format=zip --output="outputs/chenyu-yunying-0.8.2.zip" HEAD:plugins/chenyu-yunying
```

员工在支持插件上传的管理页面选择该 ZIP，安装或更新后新建对话使用。更新包时只需要重新分发 `chenyu-yunying`，不会影响美工、开发或采购插件。

## 当前边界

- 支持 DE、FR、IT、ES、UK 的 Listing；默认不加品牌。
- 只生成文案和作图要求，不自动制作商品图；实际作图交给美工插件。
- `chenyu-guanggao` 仍是规划能力，当前未实现。
- 没有后台任务、跨会话数据库或自动发布服务。
- 平台和类目限制需要发布级确认时，应核实当前官方规则；未知限制不会标记为已通过。

仓库总体结构和其他岗位插件见项目根目录的 [README](../../README.md)。
