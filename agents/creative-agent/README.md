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

负责决定：

- 做什么图片
- 每张图片表达什么卖点
- 图片顺序如何安排
- 如何提高点击和转化

它是 AI 美工主管，而不是图片生成工具。

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

## Output

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

负责根据视觉策略生成 Amazon 商品图片。

## Input

```
图片Brief
产品原图
生成要求
参考图片
视觉风格
```

## Output

```
Amazon Images

main.jpg
feature_01.jpg
feature_02.jpg
scene.jpg
```

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

负责已有图片的问题修复。

原则：

- 不重新设计产品
- 保留真实性
- 最小修改

## Input

```
原始图片
修改要求
保留规则
```

## Output

```
product_fixed.jpg
```

## MCP依赖

### Image MCP

负责图片编辑和局部修复。

### File MCP

负责图片读取和文件保存。

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
     Skills
       |
      MCP
       |
 ----------------
 Amazon
 图片模型
 文件系统
```

---

# 美工使用方式（低代码模式）

普通美工不需要理解 Agent、Skill、MCP，只需要通过任务工作台完成操作。

用户入口：

```
AI商品图片工作台
```

---

# 功能入口1：新品图片制作

用户点击：

```
创建新品图片任务
```

填写：

```
产品名称
销售市场
产品类别
核心卖点
目标用户
```

上传：

```
产品图片
产品资料
竞品图片
Listing文案
```

选择：

```
图片数量
图片风格
视觉方向
```

点击：

```
开始生成
```

后台自动执行：

```
Visual Strategy Skill
        ↓
Image Production Skill
        ↓
Image Optimization Skill
```

输出：

```
Amazon图片包

主图
卖点图
场景图
尺寸图
```

---

# 功能入口2：图片精修

用户上传：

```
原图片
```

选择问题：

```
产品边缘问题
背景问题
AI生成痕迹
阴影问题
其他修改
```

填写：

```
修改要求
```

输出：

```
修复后的商品图片
```

---

# 功能入口3：竞品视觉分析

输入：

```
竞品ASIN
竞品图片
产品资料
```

输出：

```
竞品视觉分析

推荐图片结构
7张图规划
生成建议
```

---

# 产品化架构

前端使用者看到：

```
AI美工工作台

[新品图片制作]

[图片精修]

[竞品分析]
```

后台：

```
Web UI
  ↓
Creative Agent
  ↓
Workflow
  ↓
Skills
  ↓
MCP
  ↓
图片模型 / 文件系统 / Amazon数据
```

---

# 第一阶段最小实现

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
- AI设计工作台
