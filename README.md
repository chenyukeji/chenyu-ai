# chenyu-ai

晨玙科技（Chenyu Technology）Amazon AI 运营基础设施仓库。

## 项目定位

本仓库用于建设晨玙科技面向亚马逊跨境电商业务的 AI 运营系统，包括：

- Amazon AI 运营 Agent
- MCP 工具链
- 本地自动化浏览器能力
- 商品分析 Agent
- Listing 优化 Agent
- 广告分析 Agent
- 客服 Agent
- 运营工作流自动化

## 架构理念

采用本地 Agent + MCP 架构：

```
运营人员
    ↓
AI Skill
    ↓
Agent
    ↓
本地 MCP Server
    ↓
Browser Automation
    ↓
Amazon / Seller Tools
    ↓
结果输出
```

核心原则：

- 输入任务，AI执行，输出结果
- 不强制保存运营过程数据
- 每个运营人员拥有独立运行环境
- 浏览器登录状态本地隔离
- 工具能力模块化

## 项目结构

```
chenyu-ai/
├── agents/          # AI运营Agent
├── mcp/             # MCP服务
├── skills/          # Codex/Claude Skill
├── crawlers/        # 数据采集工具
├── workflows/       # 自动化流程
├── prompts/         # Prompt资产
├── docs/            # 技术文档
└── configs/         # 配置模板
```

## Roadmap

- [x] 初始化项目架构
- [ ] Amazon MCP Server
- [ ] AI选品Agent
- [ ] Listing优化Agent
- [ ] Ads运营Agent
- [ ] 运营知识体系

## Vision

打造晨玙科技 Amazon AI Operating System，让 AI 成为跨境电商运营基础设施。
