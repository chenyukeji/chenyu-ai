# 晨玙 Amazon 运营插件

面向 Amazon 运营岗位的内容生产插件，用于从产品开发文档和产品素材中统一产品事实，并生成 Listing、逐图作图要求或两者。

## 包含能力

- `chenyu-yunying`：运营任务总入口，识别目标并协调专业 Skill。
- `chenyu-jingpin`：集中抓取和整理竞品标题、五点、普通/A+描述、产品图册及视觉证据，供下游复用。
- `chenyu-listing`：根据自有产品事实和竞品研究包，为 DE/FR/IT/ES/UK 指定站点生成无品牌标题、五点、四段式描述、搜索词和变体文案。
- `chenyu-zuotuyaoqiu`：生成可直接交给美工执行的逐图作图单。

## 常见输入

- 产品开发 Excel
- 自有产品规格和变体资料
- 产品实拍、供应商图和参考素材
- 目标站点、语言、关键词及运营要求

## 交付与边界

开发表由运营入口解析一次，竞品链接由 `chenyu-jingpin` 抓取一次；同一 `competitor-research.json` 同时交给 Listing 和作图要求，避免重复请求和证据不一致。Listing 描述统一为“概述、3—5条特征、产品参数、包装内容”，默认纯文本。竞品 Listing 和图片只作为研究输入，不能替代最终成果或自有素材。附带 Python 3.10+ 标准库脚本用于提取 XLSX 证据、抓取竞品、校验最终 Listing 包及检查关键词/文案；没有后台任务或自动发布服务。

示例请求：“根据这份开发表里的竞品链接，生成德国和法国站 Listing，不加品牌。”

插件会核对产品名称、材质、尺寸、件数、变体和卖点的一致性。当前版本不执行广告投放，不登录或修改 Amazon 店铺，也不自动发布 Listing；广告分析能力仍在规划中。

插件根目录下的 `references/kaifawendang.md` 是各运营 Skill 共用的开发文档读取规范，打包时必须保留。

## 目录说明

```text
chenyu-yunying/
├── plugin.json
├── references/
│   └── kaifawendang.md
└── skills/
    ├── chenyu-yunying/
    ├── chenyu-jingpin/
    ├── chenyu-listing/
    └── chenyu-zuotuyaoqiu/
```

打包分发时，ZIP 根层应直接包含 `plugin.json`、`skills/` 和 `references/`。详细的仓库约定与安装说明见项目根目录的 [README](../../README.md)。
