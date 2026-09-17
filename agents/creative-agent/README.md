# AI Creative Agent（美工 Agent）

## 定位

Creative Agent 是晨玙科技 Amazon AI OS 中的视觉负责人，负责 Amazon 商品视觉资产的规划、生产、优化和管理。

它不是简单的 AI 作图工具，而是一个完整的 AI 美工部门。

核心流程：

```
产品资料
   ↓
视觉策略
   ↓
图片生产
   ↓
图片精修
   ↓
质量审核
   ↓
Amazon视觉资产
```

---

# Agent 输入

Creative Agent 接收来自其他 Agent 的业务信息：

## 来自开发 Agent

```
Product Master
产品定位
用户画像
核心卖点
产品规格
差异化方案
```

## 来自运营 Agent

```
Listing内容
关键词
竞品图片
转化问题
Review痛点
```

## 人工输入

```
作图需求
参考图片
修改要求
品牌规范
```

---

# Skill 架构

## 1. Visual Strategy Skill（视觉策略 Skill）

### 作用

负责决定：

- 做什么图片
- 每张图片表达什么卖点
- 图片顺序如何安排
- 如何提高点击和转化

它是 AI 美工主管，而不是图片生成工具。

---

## Input

```json
{
  "product": "产品信息",
  "selling_points": ["卖点"],
  "target_customer": "目标用户",
  "competitor_images": [],
  "listing": {},
  "amazon_rules": {}
}
```

---

## Output

生成图片规划：

```json
{
  "image_plan": [
    {
      "number": 1,
      "type": "main",
      "goal": "提升点击"
    },
    {
      "number": 2,
      "type": "feature",
      "goal": "展示核心卖点"
    }
  ],
  "production_requirements": []
}
```

---

## MCP依赖

### Amazon MCP

获取：

- 竞品图片
- Listing信息
- 市场视觉趋势

### File MCP

读取：

- 产品资料
- Excel作图需求
- 图片文件

---

# 2. Image Production Skill（图片生产 Skill）

对应：

`chenyu-zuotu`

## 作用

根据视觉策略生成 Amazon 商品图片。

---

## Input

```
图片Brief
产品原图
生成要求
参考图片
视觉风格
```

示例：

```json
{
 "type":"feature",
 "selling_point":"静音",
 "style":"premium",
 "reference":"product.jpg"
}
```

---

## Output

生成：

```
Amazon Images

main.jpg
feature_01.jpg
feature_02.jpg
scene.jpg
```

返回：

```json
{
 "status":"completed",
 "images":[]
}
```

---

## MCP依赖

### Image MCP

负责连接：

- AI图片生成模型
- 图片编辑模型

能力：

```
generate_image()
edit_image()
```

### File MCP

负责：

- 读取产品图片
- 保存生成结果

---

# 3. Image Optimization Skill（图片精修 Skill）

对应：

`chenyu-jingxiu`

## 作用

负责已有图片的问题修复。

原则：

- 不重新设计产品
- 保留真实性
- 最小修改

---

## Input

```
原始图片
修改要求
保留规则
```

示例：

```json
{
 "image":"product.jpg",
 "instruction":"修复边缘白线",
 "preserve":[
   "shape",
   "logo",
   "material"
 ]
}
```

---

## Output

```
product_fixed.jpg
```

```json
{
 "status":"completed",
 "changes":["remove artifact"]
}
```

---

## MCP依赖

### Image MCP

负责：

- 图片编辑
- 局部修复

### File MCP

负责：

- 图片读取
- 文件保存

---

# MCP 与 Skill 分工

## Skill

负责：

- 业务逻辑
- 判断方案
- 生成任务
- 专业流程

## MCP

负责：

- 连接外部系统
- 获取数据
- 调用工具
- 返回结果

架构：

```
Creative Agent
       |
       |
     Skills
       |
       |
      MCP
       |
 ----------------
 Amazon
 图片模型
 文件系统
```

---

# 第一阶段最小实现

推荐：

```
1 Creative Agent

3 Skills

2 MCP

```

Skills:

```
Visual Strategy
Image Production
Image Optimization
```

MCP:

```
Image MCP
File MCP
```

先完成商品图片生产闭环，再扩展：

- Creative QA
- 视频生产
- 素材管理
