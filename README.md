# Amazon Product OS

这是一个可运行的 Amazon 业务工具箱：**3 个相互独立的项目级 Codex Skill + Python 共享模块**。每个 Skill 对应一个岗位任务，完成自己的交付物后停止，由负责人审核；不会自动调用下一个 Skill。

顶层按用途划分，环境与业务代码分开：

```text
Amazon_ai/
  skills/               # 3 个可见 Skill；各自只保留必要资源
  amazon_product_os/    # 唯一一份共享 Python 算法
  env/                  # 依赖、运行时说明、初始化脚本
  schemas/              # 可选的标准化交接格式
  examples/             # 可直接运行的示例输入
  tests/                # 标准库测试
  outputs/              # 运行结果
  .agents/skills/       # Codex 自动发现层
```

```text
独立采集器 ../amazon-new-release-collector ──> 外部SQLite（采集器拥有并维护）
历史Excel ───────────────────────────────┐
                                        ├─> 选品分析 Skill ─> 选品Excel ─> 等待选品负责人审核
外部SQLite最近30天（只读）───────────────┘
开品 Skill      ──> 产品开发决策卡           ──> 等待开发负责人审核
Listing Skill   ──> Listing 草稿与上传包      ──> 等待运营负责人审核
```

三个 Skill 可以分别从用户提供的资料开始。前一步的 JSON 可以作为后一步的参考，但不是强制输入，也不会自动流转。

示例文件只用于演示和测试，不代表实时市场、费用或合规结论。

## 已实现

- `.agents/skills/amazon-new-release-trends`（选品岗）：只分析历史 SellerSprite Excel 或独立采集器的 SQLite 最近30天数据，生成四表选品工作簿；不抓网页、不建库、不写数据库。
- `.agents/skills/amazon-product-decision`（开发岗）：可从产品想法、ASIN 或候选文件独立开始，完成竞品、产品方案、1688 关键词、利润、合规和决策卡。
- `.agents/skills/amazon-listing-launch`（运营岗）：从运营已审核的产品事实独立生成 Product Master、多站点 Listing、7 张图片 Brief、上传表和上架前检查。
- SellerSprite `.xlsx/.csv/.tsv` 分析器：列名中英文映射、ASIN/月去重、低价与小尺寸硬筛选，以及面向短期机会的销量、增长广度、低评论成功评分。
- 只读 SQLite 访问层：默认读取相邻的 `../amazon-new-release-collector/data/trends.db`，没有写库或建库方法。
- `Candidate`、`Development Case`、`Product Master` JSON Schema。

Codex 会从项目的 `.agents/skills` 自动发现这些 Skill；日常查看和运行入口集中在顶层 `skills/`。这是官方文档说明的仓库级发现位置：[Build skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。

## 快速开始

首次使用在项目根目录执行，虚拟环境会统一创建到 `env/.venv`：

```powershell
.\env\setup.ps1
```

```powershell
$py = ".\env\.venv\Scripts\python.exe"
& $py -m unittest discover -s tests -v
& $py -m amazon_product_os --help
```

### 1. 外部新品榜数据库

采集程序已经完全拆分到桌面同级目录 `../amazon-new-release-collector`。安装、运行、数据源和风控停止规则见该项目的 `README.md`。本项目不会打开浏览器，也没有快照导入、数据库写入或30天清理代码。

### 2. 选品分析（两种输入）

选品 Skill 不访问网页，只接受：

1. SellerSprite 风格的历史 Excel/CSV/TSV；或
2. 已存在的 SQLite 新品榜数据库。

数据库只读分析命令：

```powershell
& $py -m amazon_product_os trend report `
  --marketplace DE `
  --limit 10 `
  --output outputs/trend_candidates.json
```

历史 Excel 至少需要 `ASIN`、`商品标题` 和可用的产品分组字段。当前参考格式为 SellerSprite 的 65 列导出，程序能识别 Excel 小数百分比、价格、上架天数、包装重量和包装尺寸。历史模式面向“去年同期短期飙升机会”，默认只保留售价不高于 30、包装不超过 45×35×25 cm、重量不超过 1 kg 且尺寸重量完整的商品；利润和长期稳定性不计分。阈值可通过历史命令参数覆盖：

```powershell
& $py -m amazon_product_os historical input.xlsx `
  --marketplace ES `
  --max-price 30 `
  --max-package-weight-g 1000 `
  --output outputs/historical_candidates.json
```

使用时只需附上主文件并说“使用 `$amazon-new-release-trends` 执行【历史 Excel 选品模式】，生成可审核的选品 Excel”，或者直接说“使用 `$amazon-new-release-trends` 执行【数据库近30天选品模式】，生成可审核的选品 Excel”。Skill 会自动推断其余参数，最终统一生成：`选品结论`、`候选评分`、`ASIN证据`、`规则与来源` 四个工作表。

### 3. 开品（开发岗）

可以直接提供产品想法或 ASIN；命令行模式参考 `examples/development_case.json` 填入事实和假设。没有前序 Candidate 文件时，使用 `source: Manual` 记录来源：

```powershell
& $py skills\amazon-product-decision\scripts\run.py decision `
  examples/development_case.json `
  --output outputs/product_decision_card.json
```

决策规则：`GO >= 75`，`WATCH = 55–74`，`NO_GO < 55`；高合规风险、保守净利率低于 Gate 或没有核心差异化会强制 `NO_GO`。该结果是给开发负责人的建议，不会自动触发 Listing。

也可以单独运行：

```powershell
& $py skills\amazon-product-decision\scripts\run.py profit examples\profit_input.json
& $py skills\amazon-product-decision\scripts\run.py compliance compliance_profile.json --marketplace DE
```

### 4. Listing（运营岗）

运营先审核 Product Master 和各站点内容，再独立生成包；不要求前面运行过开品 Skill：

```powershell
& $py skills\amazon-listing-launch\scripts\run.py `
  --product-master examples/product_master.json `
  --listings examples/listings.json `
  --output-dir outputs/launch-package
```

如需保留开发记录供追溯，可选加上：

```powershell
  --decision outputs/product_decision_card.json
```

输出包括：

```text
amazon_upload.xlsx
amazon_upload.csv
listing/DE.txt, FR.txt, ...
images/manifest.json
compliance/requirements.json
product_master.json
product_decision_card.json  # 仅在提供 --decision 时生成
pre_launch_check.json
```

工作簿由 `@oai/artifact-tool` 生成。在 Codex 桌面环境中使用工作区加载器提供的 Node 运行时；普通终端必须确保 Node 可以解析该包。如果 XLSX 未生成，CSV 仍会保留，但状态会是 `NOT_READY`。

`READY_FOR_OPERATIONS_REVIEW` 只表示自动检查通过，仍需运营负责人审核。程序不会自动采购、联系供应商、上传 Amazon、修改库存或花费广告预算。

## 代码结构

```text
amazon_product_os/
  trend_db.py            # 外部SQLite只读访问
  trend_analyzer.py      # 新品产品类型信号
  sellersprite.py        # 历史榜 Excel/CSV 分析
  profit.py              # 正常/保守利润
  compliance.py          # 合规筛查 Gate
  decision.py            # 加权决策卡
  listing.py             # 上架包与一致性检查
  orchestrator.py        # 独立命令的轻量入口，不自动串联
  cli.py                 # 命令行入口

skills/
  amazon-new-release-trends/SKILL.md
  amazon-product-decision/scripts/run.py
  amazon-listing-launch/scripts/run.py
  amazon-listing-launch/scripts/build_amazon_upload.mjs
```

基线阈值记录在 `config/defaults.json`；最小同类 ASIN 数可通过 CLI 覆盖，最低保守净利率可在 Development Case 中覆盖。合规模块只是初筛，正式投产前仍需核对当期法规、Amazon 站点要求和专业意见。
