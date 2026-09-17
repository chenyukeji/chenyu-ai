# chenyu-ai

# 晨玙科技 Amazon AI Operating System

`chenyu-ai` 是晨玙科技面向 Amazon 跨境电商打造的 AI 自动化运营系统。

## Amazon 美工插件

仓库内的 `chenyu-amazon-creative` 是一个仅包含 Skills 的可安装插件：

- `chenyu-zuotu`：根据作图要求、产品实拍和参考素材生成整套 Amazon 商品图片。
- `chenyu-jingxiu`：根据完整原图、细节图和修改描述执行精准局部精修。

插件源码位于 `plugins/chenyu-amazon-creative`，仓库市场清单位于 `.agents/plugins/marketplace.json`。

### 在 ChatGPT 工作区安装

1. 工作区管理员进入“管理 → 插件 → 添加 → 导入市场”。
2. 来源填写 `https://github.com/chenyukeji/chenyu-ai`，路径留空，分支填写 `main`。
3. 导入并同步后，在插件目录找到“晨玙 Amazon 美工”，点击加号安装。
4. 安装后新建对话，直接描述作图或精修任务，也可以明确选择插件内的 Skill。

### 在 Codex 本地安装

在 Codex CLI 中添加 GitHub 仓库市场并安装插件：

```powershell
codex plugin marketplace add chenyukeji/chenyu-ai --ref main
codex plugin add chenyu-amazon-creative@personal
```

本地开发时，也可以把第一条命令的仓库地址替换为本地 `chenyu-ai` 目录绝对路径。

安装完成后开启新会话，使 Codex 加载插件中的 Skills。若要让所有 ChatGPT 用户直接从公共插件目录安装，还需要完成插件提交与审核流程。

目标：

> 用 AI Agent 模拟一个完整的亚马逊电商团队。

系统不是拆成大量小机器人，而是按照真实公司部门设计：

- AI开发 Agent（产品负责人）
- AI采购 Agent（供应链负责人）
- AI运营 Agent（店铺负责人）
- AI美工 Agent（视觉负责人）
- AI ERP Agent（企业数据负责人）

每个 Agent 内部包含多个 Skill，用于完成具体工作流程。

---

# 一、整体架构

```
                    Amazon AI OS

                         |

                 Agent 协作层

                         |

 ------------------------------------------------
 |              |              |        |        |
开发Agent    采购Agent     运营Agent 美工Agent ERP Agent

                         |

                    MCP工具层

 ------------------------------------------------
 Amazon MCP
 ERP MCP
 浏览器 MCP
 数据 MCP
 文件 MCP
```

---

# 二、AI Agent设计

## 1. AI开发 Agent（Product Development Agent）

定位：产品负责人。

负责：

- 市场机会分析
- 产品设计
- 产品开发决策
- 利润模型

## Skills

### 产品机会分析 Skill

输入：

```
关键词
ASIN
竞品数据
销量数据
Review
市场数据
```

输出：

```
市场机会报告
竞争分析
用户需求
产品方向
```

---

### 产品方案设计 Skill

输入：

```
市场机会
竞品信息
供应链资料
```

输出：

```
Product Master
产品定位
功能设计
差异化方案
包装方案
```

---

### 开发决策 Skill

输入：

```
成本
售价
物流
FBA费用
广告预算
```

输出：

```
开发决策
目标成本
利润模型
风险分析
```

---

# 2. AI采购 Agent（Procurement Agent）

定位：供应链负责人。

负责：

- 供应商管理
- 采购计划
- 供应链跟踪

## Skills

### 供应商分析 Skill

输入：

```
产品需求
供应商资料
报价
```

输出：

```
供应商列表
价格比较
MOQ
交期
风险
```

---

### 采购执行 Skill

输入：

```
产品需求
销售预测
库存状态
```

输出：

```
采购计划
采购数量
采购时间
成本
```

---

### 供应链跟踪 Skill

输入：

```
采购订单
物流状态
质量记录
```

输出：

```
供应链报告
异常提醒
风险预警
```

---

# 3. AI运营 Agent（Operation Agent）

定位：Amazon店铺负责人。

负责：

- Listing优化
- 广告优化
- 销售分析
- 日常运营决策

## Skills

### 店铺分析 Skill

输入：

```
订单
销售数据
排名
库存
Review
```

输出：

```
经营报告
问题诊断
优化方向
```

---

### Listing优化 Skill

输入：

```
产品资料
关键词
竞品Listing
转化数据
```

输出：

```
标题
五点
关键词
描述
优化方案
```

---

### 广告优化 Skill

输入：

```
广告报表
关键词
销售数据
```

输出：

```
广告调整方案
Bid建议
预算建议
关键词策略
```

---

### 运营决策 Skill

输入：

```
全部业务数据
```

输出：

```
每日任务列表
优先级
执行建议
```

---

# 4. AI美工 Agent（Creative Agent）

定位：视觉设计负责人。

负责：

- 商品视觉策略
- 图片生产规划
- 视频内容

## Skills

### 视觉策略 Skill

输入：

```
产品定位
用户画像
竞品图片
```

输出：

```
视觉方向
图片结构
卖点表达
```

---

### 图片生产 Skill

输入：

```
产品资料
视觉方案
```

输出：

```
主图方案
7图规划
AI绘图Prompt
```

---

### 视频内容 Skill

输入：

```
产品卖点
使用场景
用户需求
```

输出：

```
视频脚本
广告素材方案
```

---

# 5. AI ERP Agent（ERP Agent）

定位：企业数据负责人。

负责连接：

- ERP系统
- Amazon数据
- 财务数据
- 库存数据

## Skills

### 数据同步 Skill

输入：

```
ERP
Amazon
广告
财务
```

输出：

```
统一业务数据模型
```

---

### 库存管理 Skill

输入：

```
销量
库存
采购周期
```

输出：

```
库存状态
补货建议
断货预警
```

---

### 经营分析 Skill

输入：

```
销售
成本
广告
库存
```

输出：

```
利润分析
经营看板
业务报告
```

---

# 三、仓库结构

```
chenyu-ai/

├── agents/
│   ├── development-agent
│   ├── procurement-agent
│   ├── operation-agent
│   ├── creative-agent
│   └── erp-agent
│
├── mcp/
│   ├── amazon-mcp
│   ├── erp-mcp
│   └── browser-mcp
│
├── skills/
├── workflows/
├── prompts/
├── docs/
└── configs/
```

---

# 四、设计原则

## Agent不是工具，而是AI员工

```
Agent = 岗位负责人
Skill = 工作能力
MCP = 工具和系统连接
```

## 输入输出标准化

所有能力遵循：

```
Input
 ↓
AI Processing
 ↓
Output
```

## 本地优先

```
Codex
 ↓
Agent
 ↓
Skill
 ↓
MCP
 ↓
Amazon / ERP / 工具
```

---

晨玙科技 Amazon AI OS

让AI成为跨境电商公司的数字员工。
