# 晨玙 Amazon 美工插件

面向 Amazon 美工岗位的图片生产插件，用于根据作图要求、产品实拍和参考素材制作商品图，或对已有图片进行精准局部精修。

## 包含能力

- `chenyu-meigong`：美工任务总入口，判断任务属于整套作图、改版还是局部精修。
- `chenyu-zuotu`：读取作图单并制作或修改整套 Amazon 商品图片。
- `chenyu-jingxiu`：在保护原图主体、背景和构图的前提下执行局部精修。

## 常见输入

- Excel 作图单或自然语言作图要求
- 产品实拍图
- 版式、场景或风格参考图
- 已有成品图及具体修改说明

## 交付与边界

插件交付最终完整图片，并检查 SKU、变体、图号和素材对应关系。它不会自动上传或发布 Amazon 商品图，也不会把参考产品的商标、规格或结构当作自有产品事实。

## 目录说明

```text
chenyu-meigong/
├── plugin.json
└── skills/
    ├── chenyu-meigong/
    ├── chenyu-zuotu/
    └── chenyu-jingxiu/
```

打包分发时，ZIP 根层应直接包含 `plugin.json` 和 `skills/`。详细的仓库约定与安装说明见项目根目录的 [README](../../README.md)。
