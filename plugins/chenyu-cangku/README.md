# 晨玙 Amazon 仓库插件

`chenyu-cangku` 面向仓库岗位处理新品建档、系统导入文件和承运商发货发票。可把晨玙“新品补录”Excel 自动转换为两份可导入领星的官方模板，也可从箱唛照片提取每箱信息、核对领星商品资料，生成联航或驿路达格式的发货发票。

## 包含能力

- `chenyu-lingxing-luru`：输入一份新品补录表，生成领星产品录用表与按 MSKU 配对表。
- `chenyu-xiangmai-fapiao`：箱唛照片输入，领星核对商品材质、图片和销售链接后，生成所选承运商的发货发票。
- 清洗 MSKU 中的换行、尾部空格和尾部竖线，检查重复值和必填字段。
- 按账号映射法国站店铺，拆分包装尺寸，并生成重量、采购备注和头程费用字段。
- 生成后核对数据行数、公式错误和可视化渲染结果。

## 适用边界

领星产品录用 Skill 只生成导入文件，不登录领星、不上传文件、不新增或修改系统产品。账号没有已确认店铺映射、非空尺寸无法解析、MSKU 重复或必填字段缺失时停止并指出具体行，不猜测业务值。

箱唛发票 Skill 可在用户已登录的领星中只读核对商品资料，不修改领星或向承运商提交。照片缺少渠道/FBA 箱号、商品匹配不唯一或申报字段未确认时，先向用户询问；使用由用户最新原版 `.xls` 清空旧货件内容后的模板资产，保留原有地址公式、下拉规则、工作表和格式，不把历史货件作为新数据。该能力需要本机 WPS 表格；Microsoft Excel 保存这两份旧 `.xls` 会丢失原有下拉规则。

用户的新品补录表、照片和生成结果属于业务文件，不提交到 GitHub；仓库只保留空白模板、字段规则和生成脚本。

默认输出位于 `outputs/chenyu-cangku/lingxing-product-import/<YYYY-MM-DD_任务简称>/`。详细规则见 [输出目录规范](references/output-paths.md)。
发货发票默认输出位于 `outputs/chenyu-cangku/shipping-invoice/<YYYY-MM-DD_任务简称>/`。

## 目录说明

```text
chenyu-cangku/
├── .codex-plugin/plugin.json
├── plugin.json
├── references/output-paths.md
└── skills/
    ├── chenyu-lingxing-luru/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   ├── assets/
    │   ├── references/field-mapping.md
    │   ├── scripts/generate_lingxing_imports.py
    │   └── scripts/generate_lingxing_imports.mjs
    └── chenyu-xiangmai-fapiao/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── assets/lianhang-template.xls
        ├── assets/yiluda-template.xls
        ├── references/field-rules.md
        └── scripts/generate_shipping_invoice.ps1
```
