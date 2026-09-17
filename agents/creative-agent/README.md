# AI Creative Agent（美工 Agent）

## 定位

Creative Agent 是晨玙科技 Amazon AI OS 中第一个落地的 AI 员工。

第一阶段目标不是开发完整 AI 美工系统，而是先把美工能力封装成 GPT/Codex Skill，让美工可以直接使用。

未来再逐步扩展为低代码 AI 美工工作台。

---

# 第一阶段架构

```
美工
 |
 | 上传产品资料、图片、需求
 ↓
Amazon Creative Designer Skill
 ↓
GPT图片能力
 ↓
输出Amazon商品图片
```

---

# 核心 Skill

## Amazon Creative Designer Skill

这是美工 AI 员工的统一入口。

整合：

- 商品图片策划
- 商品图片生成
- 商品图片精修
- 图片质量检查

美工不需要理解：

- Agent
- MCP
- Workflow
- Prompt

只需要描述任务。

---

# 使用方式

## 新品图片制作

输入：

```
产品资料
产品图片
竞品参考
Listing信息
卖点要求
图片数量
视觉风格
```

例如：

```
制作美国站Amazon 7张商品图
产品：宠物饮水机
卖点：静音、过滤、大容量
风格：高端科技
```

处理流程：

```
产品理解
 ↓
视觉方案规划
 ↓
图片生成
 ↓
图片优化
```

输出：

```
main.jpg
feature_01.jpg
feature_02.jpg
scene.jpg
size.jpg
```

---

## 图片精修

输入：

```
原始图片
修改要求
```

例如：

```
去除产品边缘白线
保持产品结构不变
```

输出：

```
修复后的图片
```

原则：

- 保留真实性
- 不改变产品结构
- 最小修改

---

# Skill 输入输出规范

## Input

统一接收：

```json
{
 "product_info": {},
 "images": [],
 "selling_points": [],
 "competitor_reference": [],
 "task": "create_or_edit"
}
```

---

## Output

统一输出：

```json
{
 "image_plan": [],
 "generated_images": [],
 "optimization_result": {},
 "status": "completed"
}
```

---

# MCP规划

第一阶段：不开发独立MCP。

直接使用 GPT 内置能力。

后续根据实际需求增加：

## Image MCP

负责：

- 图片生成
- 图片编辑
- 图片处理

## File MCP

负责：

- 读取产品文件
- 保存图片素材
- 管理文件

## Amazon MCP（后续）

负责：

- 获取竞品图片
- 获取Listing数据
- 获取市场信息

---

# 后续产品化路线

## 阶段1：Skill

```
GPT/Codex
 ↓
Amazon Creative Designer Skill
 ↓
美工使用
```


## 阶段2：Workflow

```
任务表单
 ↓
自动调用Skill
 ↓
生成图片
```


## 阶段3：AI美工工作台

```
Web系统
 ↓
Creative Agent
 ↓
Skill
 ↓
MCP
 ↓
图片模型
```

---

# 目标

先让晨玙科技美工每天真实使用 AI，提高图片生产效率。

在使用过程中沉淀流程、数据和最佳实践，再逐步系统化。