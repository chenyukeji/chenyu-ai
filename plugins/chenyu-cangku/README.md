# 晨玙 Amazon 仓库插件

`chenyu-cangku` 面向仓库岗位处理新品建档和系统导入文件。当前把晨玙“新品补录”Excel 自动转换为两份可导入领星的官方模板，同时保留模板中的示例、字典、下拉选项、格式和其他工作表。

## 包含能力

- `chenyu-lingxing-luru`：输入一份新品补录表，生成领星产品录用表与按 MSKU 配对表。
- 清洗 MSKU 中的换行、尾部空格和尾部竖线，检查重复值和必填字段。
- 按账号映射法国站店铺，拆分包装尺寸，并生成重量、采购备注和头程费用字段。
- 生成后核对数据行数、公式错误和可视化渲染结果。

## 适用边界

插件只生成导入文件，不登录领星、不上传文件、不新增或修改系统产品。账号没有已确认店铺映射、非空尺寸无法解析、MSKU 重复或必填字段缺失时停止并指出具体行，不猜测业务值。

用户的新品补录表和生成结果属于业务文件，不提交到 GitHub；仓库只保留空白领星模板、字段规则和生成脚本。

默认输出位于 `outputs/chenyu-cangku/lingxing-product-import/<YYYY-MM-DD_任务简称>/`。详细规则见 [输出目录规范](references/output-paths.md)。

## 目录说明

```text
chenyu-cangku/
├── .codex-plugin/plugin.json
├── plugin.json
├── references/output-paths.md
└── skills/
    └── chenyu-lingxing-luru/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── assets/
        ├── references/field-mapping.md
        └── scripts/generate_lingxing_imports.mjs
```
