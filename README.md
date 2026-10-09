# 晨玙 AI 岗位插件

`chenyu-ai` 保存岗位 Skill、业务规则、模板、采集与文件生成脚本。当前共有 **5 个插件、15 个 Skill**。网站页面、账号权限、任务队列、微调版本和产品任务由独立的 `chenyu-ai-web` 仓库维护。

## 当前功能

| 岗位 | 插件与说明 | Skill | 交付 |
| --- | --- | --- | --- |
| AI 开发 | [chenyu-kaifa](plugins/chenyu-kaifa/README.md) | 自动选择、选品分析、供应商采集、开发文档 | 开品结果 Excel、1688供应商事实包、每产品独立的开发 Excel |
| AI 运营 | [chenyu-yunying](plugins/chenyu-yunying/README.md) | 自动选择、竞品研究、Listing、作图要求、订单商业发票 | 竞品研究包、独立运营 Excel、订单 PDF |
| AI 美工 | [chenyu-meigong](plugins/chenyu-meigong/README.md) | 自动选择、整套作图、主图优化、局部精修 | 完整商品图片 |
| AI 仓库 | [chenyu-cangku](plugins/chenyu-cangku/README.md) | 领星产品录用 | 产品录用表与按 MSKU 配对表 |
| AI 物流 | [chenyu-wuliu](plugins/chenyu-wuliu/README.md) | 箱唛发货发票 | 联航或驿路达原格式 `.xls` |

版本以各插件的 `plugin.json` 和 `.codex-plugin/plugin.json` 为准，两份清单的版本必须一致。

## 使用边界

- 开发选品：E 新品榜、J 近期 FBM、H 历史季节性有采集流程；A/I/C/K 支持导入证据分析；B/D/F 保留策略定义，尚不可执行。采集依赖站点访问和有效账号，数据不足时保留阻塞状态。
- 运营的竞品研究是可复用 Skill，网站不单独列为任务类型。Listing、作图要求分别交付；订单商业发票属于运营。
- 美工实际出图依赖图像生成或编辑工具；文件检查不能替代视觉审核。
- 仓库生成导入文件，不自动上传领星或修改库存。
- 物流箱唛发票依赖 Windows＋WPS。网站已有物流表单，正式生成等待执行环境接入；不要把它与运营订单 PDF 混用。
- 广告、采购、自动发布商品，以及独立 MCP/App、岗位 Agent 服务均未在本仓库实现。

## 目录

```text
chenyu-ai/
├── .agents/plugins/marketplace.json   # 五个插件的市场登记
├── plugins/
│   ├── chenyu-kaifa/
│   ├── chenyu-yunying/
│   ├── chenyu-meigong/
│   ├── chenyu-cangku/
│   └── chenyu-wuliu/
├── scripts/sync_remote_plugins.py    # GitHub 与安装缓存同步
├── deploy/                           # 定时更新服务
├── tests/                            # 跨插件及公共回归测试
├── pyproject.toml                    # pytest 测试发现配置
└── AGENTS.md                         # 协作、职责与发布约定
```

插件内部：

| 路径 | 职责 |
| --- | --- |
| `plugin.json`、`.codex-plugin/plugin.json` | 插件身份、版本和能力登记 |
| `skills/<名称>/SKILL.md` | 触发条件、执行步骤、交付与停止条件 |
| `skills/<名称>/agents/openai.yaml` | 界面名称及默认提示，不是后台任务服务 |
| `assets/` | 空白模板和必要素材 |
| `references/` | 业务合同、字段映射、评分与交付规则 |
| `scripts/` | 实际采集、解析、生成和校验实现 |

README 用作能力和使用入口；业务规则以所属 `SKILL.md` 及其引用文件为准，避免在多处复制后产生冲突。各岗位总入口由当前助手读取专业 Skill 协调，不提供独立后台调度或跨会话记忆。

## 安装

有仓库访问权限的员工添加 GitHub marketplace 后，按岗位安装：

```bash
codex plugin marketplace add chenyukeji/chenyu-ai
codex plugin marketplace upgrade chenyu-ai
codex plugin add chenyu-kaifa@chenyu-ai
codex plugin add chenyu-yunying@chenyu-ai
codex plugin add chenyu-meigong@chenyu-ai
codex plugin add chenyu-cangku@chenyu-ai
codex plugin add chenyu-wuliu@chenyu-ai
```

升级后新建对话加载新版本。服务器使用已配置的 `personal` marketplace 同步缓存，详见 [自动更新部署](deploy/README.md)。

## 运行依赖

- 开发浏览器采集：Python、Playwright、Chromium、Pillow、openpyxl；见 [依赖文件](plugins/chenyu-kaifa/requirements-browser.txt)。
- 1688供应商采集：Node.js、Playwright、Chrome及已授权领星会话；见 [采集接口](plugins/chenyu-kaifa/skills/chenyu-gongyingshang/references/collector.md)。
- 仓库 Excel：Python 与 openpyxl。
- 运营订单 PDF：Python 与 PyMuPDF；见 [依赖文件](plugins/chenyu-yunying/skills/chenyu-invoice/scripts/requirements.txt)。
- 运营工作簿拆分：Node.js 与执行环境提供的 `@oai/artifact-tool`。
- 美工：图像生成/编辑工具；材料提取和文件检查脚本按各自 Skill 执行。
- 物流：Windows PowerShell 与 WPS 表格，且能访问经授权的领星商品资料。

这是插件集合，按相应脚本和 Skill 执行，不提供仓库级 Python 应用或统一 CLI。

## 输出与隐私

独立使用时，默认成果保存到：

```text
outputs/<插件名>/<交付部分>/<YYYY-MM-DD_任务简称>/
```

同名新任务追加序号，不覆盖旧成果。网站任务以执行器指定的任务目录为准；具体默认目录见各插件说明。真实订单、产品资料、结果文件、登录状态、密码和令牌不进入源码或插件分发包。

## 验证与发布

在已安装 pytest、openpyxl、Pillow 等对应依赖的测试环境中，从仓库根目录运行：

```bash
python -m pytest
# PDF 生成回归另需 PyMuPDF
python plugins/chenyu-yunying/skills/chenyu-invoice/scripts/test_invoice.py
```

pytest 默认覆盖根目录测试及选品 Skill 内测试。采集测试主要使用模拟页面和样例数据，通过测试不代表线上登录或外部页面始终可用。物流 WPS 生成需在对应 Windows 环境验收。

修改插件后同步递增两份清单的纯语义版本，验证 Skill、插件和相关测试，提交并推送后再更新缓存。自动同步只接受干净 `main` 的快进更新，并校验安装文件与源码一致；详细协作约定见 [AGENTS.md](AGENTS.md)。
