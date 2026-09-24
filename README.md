# chenyu-ai

晨玙科技 Amazon AI 工作插件仓库。仓库按公司岗位维护四个相互独立、可单独分发的插件：美工、运营、开发和采购。

## 当前插件

| 插件 | 面向岗位 | 当前 Skills |
| --- | --- | --- |
| `chenyu-meigong` | Amazon 美工 | `chenyu-meigong` 总入口、`chenyu-zuotu`、`chenyu-jingxiu` |
| `chenyu-yunying` | Amazon 运营 | `chenyu-yunying` 总入口、`chenyu-jingpin`、`chenyu-listing`、`chenyu-zuotuyaoqiu` |
| `chenyu-kaifa` | Amazon 产品开发 | `chenyu-kaifa` |
| `chenyu-caigou` | Amazon 采购 | `chenyu-caigou` |

## 统一目录规范

```text
plugins/
├── chenyu-meigong/
│   ├── plugin.json
│   └── skills/
│       ├── chenyu-meigong/
│       ├── chenyu-zuotu/
│       │   ├── SKILL.md
│       │   ├── agents/
│       │   ├── assets/
│       │   ├── references/
│       │   └── scripts/
│       └── chenyu-jingxiu/
│           ├── SKILL.md
│           ├── agents/
│           └── assets/
├── chenyu-yunying/
│   ├── plugin.json
│   ├── references/kaifawendang.md
│   └── skills/
│       ├── chenyu-yunying/
│       ├── chenyu-jingpin/
│       ├── chenyu-listing/
│       └── chenyu-zuotuyaoqiu/
├── chenyu-kaifa/
│   ├── plugin.json
│   └── skills/chenyu-kaifa/
└── chenyu-caigou/
    ├── plugin.json
    └── skills/chenyu-caigou/
```

每个插件遵循以下规则：

- 根目录使用 `plugin.json` 描述插件，`skills/` 保存该岗位的实际能力。
- 每个 Skill 都有 `SKILL.md`；`agents/openai.yaml` 只描述该 Skill 在界面中的名称和默认提示。
- `assets/`、`references/`、`scripts/` 仅在有真实内容时建立，不保留空目录。
- 后续需要 MCP、App 或独立 Agent 时，只在对应插件中增加，四个插件仍可分别安装和升级。

## 统一输出目录

未指定其他保存位置时，四个插件的业务成果统一写入：

```text
outputs/<插件名>/<交付部分>/<YYYY-MM-DD_产品简称>/
```

例如运营 Listing 使用 `outputs/chenyu-yunying/listing/2026-09-20_tree-skirt-120cm/`，美工整套出图使用 `outputs/chenyu-meigong/image-production/2026-09-20_tree-skirt-120cm/`。同一综合任务在不同交付部分下复用相同任务名；新运行遇到同名目录时追加 `_02`、`_03`，不得覆盖旧成果。只查看、解释或诊断时不创建空目录。各插件的具体交付部分见其 `references/output-paths.md`。

## 员工安装

日常由 `chenyu-yunying` 或 `chenyu-meigong` 总入口接收需求，也可直接选择专业 Skill。运营将开发文档整理为 Listing 和作图要求，美工接收作图要求与产品素材制作或精修图片。总入口通过当前助手读取专业 Skill 协调工作，不提供后台调度或跨会话记忆。

`chenyu-guanggao`（广告）仅为后续计划，当前未实现。目录和 Skill 标识统一使用拼音，Listing 保留通用名称；标准文件名不翻译。插件更名后，安装新名称的包并停用旧包，避免同名专业 Skill 重复出现。运营包包含共用 `references/`，分发时保留。

仓库已在 `.agents/plugins/marketplace.json` 注册四个岗位插件。拥有仓库访问权限的员工可添加并刷新 GitHub marketplace：

```bash
codex plugin marketplace add chenyukeji/chenyu-ai
codex plugin marketplace upgrade chenyu-ai
```

然后按岗位安装，例如：

```bash
codex plugin add chenyu-yunying@chenyu-ai
codex plugin add chenyu-meigong@chenyu-ai
codex plugin add chenyu-kaifa@chenyu-ai
codex plugin add chenyu-caigou@chenyu-ai
```

安装或升级后新建对话，确保 Codex 加载新版本。GitHub `main` 是插件源码、规则、测试、清单和 marketplace 的唯一基线；本地插件只能从已经提交并推送的同一源码刷新，不能保留领先或落后的私人副本。

ZIP 仍作为备用分发方式：管理员或维护者分别打包 `plugins/` 下的四个目录，ZIP 根层必须直接看到 `plugin.json` 和 `skills/`，再由员工在 ChatGPT 工作区插件管理页面上传。四个部门插件互不依赖；`dist/` 中的 ZIP 是派生发布物，不进入源码提交，需要分发时应从已提交版本重新生成并作为 GitHub Release 附件发布。

## 后续架构计划

当前版本先把各岗位最核心的 Skills 做成可安装插件。后续扩展分为三层：

```text
Agent（岗位负责人：理解目标、选择能力、控制权限）
  ↓
Workflow（业务流程：规定步骤、输入输出、检查点和交接）
  ↓
Skill + MCP（专业能力 + 外部系统和实时数据）
```

- **Skill**：完成一个边界明确、可重复使用的专业任务。
- **Workflow**：把多个 Skills 和人工确认点组合成端到端业务流程。
- **MCP**：连接 Amazon、ERP、素材库、供应商和内部数据库，提供结构化工具与数据。
- **Agent**：代表一个岗位负责接收目标、选择 Workflow、调用 Skills/MCP、汇总结果和控制高风险操作。

Agent 与 Workflow 是本仓库的业务编排规范；Skills 与 MCP 是插件可直接打包的能力。只有真实实现完成后才创建对应目录，不建立空占位目录。

设计依据参考 OpenAI 官方的 [Skills 与 Plugins 说明](https://learn.chatgpt.com/zh-Hans/docs/skills-and-plugins) 和 [创建 Plugins 指南](https://learn.chatgpt.com/zh-Hans/docs/build-plugins)。

### Agent 计划

| Agent | 定位 | 主要调度内容 | 权限原则 |
| --- | --- | --- | --- |
| `meigong-agent` | Amazon 视觉负责人 | 作图、精修、视觉检查、素材交付 | 可生成文件，不自动发布商品图 |
| `yunying-agent` | Amazon 店铺负责人 | Listing、广告、销售、库存和日常任务 | 默认只读，修改店铺必须人工确认 |
| `kaifa-agent` | Amazon 产品负责人 | 市场机会、产品方案、利润模型和开发决策 | 输出建议，不自动立项或采购 |
| `caigou-agent` | 供应链负责人 | 供应商比较、采购计划、交期和质量风险 | 不自动询价、签约、下单或付款 |

岗位 Agent 首先只在自己的插件内部调度。等四个岗位稳定后，再评估增加独立的 `guanli-agent`，用于跨部门查看进度和发起流程，但不取代各岗位的专业判断。

### MCP 计划

MCP 按数据域建设，不按单个 Prompt 建设。第一阶段全部使用只读工具；涉及写入、发布、预算、下单或付款的工具必须单独授权，并保留确认步骤和操作记录。

| MCP | 计划连接 | 主要使用方 | 第一阶段能力 |
| --- | --- | --- | --- |
| `amazon-mcp` | Amazon 店铺、Listing、广告、订单和库存 | 运营、开发 | 查询与报表读取 |
| `erp-mcp` | 产品、成本、库存、采购单和物流 | 开发、采购、运营 | 查询与数据汇总 |
| `sucai-mcp` | 产品实拍、参考图、成品图和版本记录 | 美工、运营 | 素材检索与读取 |
| `gongyingshang-mcp` | 供应商档案、报价、MOQ、交期和质检记录 | 采购、开发 | 查询与供应商比较 |
| `caiji-mcp` | Amazon New Releases 采集结果 | 开发、运营 | 只读查询采集快照 |


### Workflow 计划

#### 美工 Workflow

- `zuotu-zhizuo`：解析作图单 → 匹配素材 → 逐图生成 → 质量检查 → 局部返修 → 交付。
- `jingxiu-jiancha`：接收原图与修改点 → 累积局部精修 → 对照检查 → 返回最终完整图。
- `meigong-yunying-jiaojie`：整理成品、版本、卖点和使用位置，交给运营确认上线。

#### 运营 Workflow

- `yunying-richang-zhenduan`：汇总销售、广告、排名、库存和 Review → 识别异常 → 生成当日任务。
- `listing-youhua`：产品资料与关键词 → Listing 草稿 → 合规检查 → 人工确认 → 发布准备。
- `guanggao-youhua`：广告报表 → 搜索词与投放分析 → 预算/竞价建议 → 人工确认。
- `yunying-zhoubao`：周度数据汇总 → 目标差异 → 原因分析 → 下周行动计划。

#### 开发 Workflow

- `shichang-chanpin-fangan`：市场机会 → 用户需求 → 竞品差距 → 差异化产品方案。
- `chanpin-lirun-cesuan`：产品规格 → 供应链成本 → 平台与物流费用 → 利润模型。
- `kaifa-pingshen`：市场、产品、利润、合规和供应风险 → 开发/验证/暂缓/放弃决策。

#### 采购 Workflow

- `gongyingshang-pinggu`：产品需求 → 报价标准化 → 供应商评分 → 推荐与备选方案。
- `buhuo-jihua`：销售预测、库存和供应周期 → 采购数量 → 下单与到货窗口。
- `caigou-genjin`：采购节点 → 交期、质量和物流偏差 → 风险升级与处置建议。

#### 跨部门 Workflow

- `xinpin-shangjia`：开发立项 → 采购打样与备货 → 美工生产素材 → 运营准备 Listing 与广告 → 人工批准上线。
- `chanpin-gaijin`：运营收集 Review 与退货问题 → 开发形成改款方案 → 采购验证成本和供应 → 美工更新视觉表达。
- `kucun-fengxian-chuli`：运营发现库存风险 → 采购评估补货 → 开发/运营评估利润与促销 → 人工确认执行。

### 规划目录规范

以下是单个插件未来完成 Agent、Workflow 和 MCP 后的目标结构；未实现的目录不会提前加入仓库或员工 ZIP：

```text
chenyu-yunying/
├── plugin.json
├── skills/
│   └── chenyu-yunying/
├── agents/                 # 岗位级调度配置与职责说明
│   └── yunying-agent/
├── workflows/              # 可复用流程定义、检查点与交接格式
│   ├── yunying-richang-zhenduan/
│   └── yunying-zhoubao/
├── mcp/                    # 属于本插件的数据连接实现
│   └── amazon-yunying-mcp/
└── .mcp.json               # MCP 注册与连接配置（接入 MCP 后才创建）
```

跨部门 Workflow 不复制到四个插件中，统一放在仓库级 `workflows/`，并明确每一步由哪个岗位插件负责。员工日常仍只安装自己岗位的插件；需要完整跨部门自动化时，再由管理端组合调用。

### 实施顺序

1. **完善 Skills**：用真实业务样本稳定输入、输出、模板和异常处理。
2. **落地单部门 Workflow**：先完成不依赖外部系统的文件型流程和人工交接。
3. **接入只读 MCP**：优先打通 Amazon、ERP、素材与供应商数据查询。
4. **启用岗位 Agent**：让每个 Agent 在明确权限内选择 Workflow、Skill 和工具。
5. **建设跨部门 Workflow**：打通新品开发、上架、改款和库存风险流程。
6. **开放受控写入**：在审计、授权、幂等和回滚机制具备后，再逐项开放发布、调价、广告、采购等操作。

每个阶段都必须保持四个岗位插件可独立安装、独立升级、独立回退。

