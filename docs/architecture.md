# Chenyu Amazon AI Architecture

## 总体架构

```
User
 ↓
AI Assistant
 ↓
Agent Layer
 ↓
MCP Tool Layer
 ↓
Local Automation
 ↓
Amazon Platform
```

## Agent 模块

### Product Agent

负责：
- 市场分析
- 竞品分析
- 产品机会发现

### Listing Agent

负责：
- 标题优化
- 五点描述
- Search Term优化

### Ads Agent

负责：
- 广告数据分析
- 关键词优化
- 投放建议

### Customer Agent

负责：
- 客服回复
- Review分析
- 用户反馈整理

## MCP设计

MCP负责连接AI与外部工具：

- Amazon工具
- 浏览器工具
- 数据查询工具
- 运营辅助工具

## 部署原则

每个运营人员本地运行自己的Agent环境，避免共享浏览器和账号状态冲突。
