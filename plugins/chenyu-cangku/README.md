# 晨玙 Amazon 仓库插件

`chenyu-cangku` 使用 [领星产品录用 Skill](skills/chenyu-lingxing-luru/SKILL.md)，将一份公司“新品补录”Excel 转换为两份领星导入文件。当前版本见 [plugin.json](plugin.json)。

## 输入与交付

| 文件 | 用途 |
| --- | --- |
| 新品补录 Excel | 输入产品、MSKU、账号、尺寸重量和采购相关已知字段 |
| 领星产品录用表 | 使用 `Product-V392.xlsx` 官方模板整理产品档案 |
| 按 MSKU 配对表 | 使用按 MSKU 导入模板整理店铺商品配对 |

生成器清洗 MSKU、检查重复值和必填项、应用已确认的店铺映射、处理尺寸重量及费用字段，并保留官方模板中的示例、字典、格式与下拉选项。未知店铺映射、重复 MSKU 或非空非法数值会停止并指出问题。

## 执行

唯一生成实现为 `skills/chenyu-lingxing-luru/scripts/generate_lingxing_imports.py`，依赖 Python 和 openpyxl。网站 Worker 和本地 Skill 均调用此实现。

```bash
python skills/chenyu-lingxing-luru/scripts/generate_lingxing_imports.py \
  --input /path/to/新品补录.xlsx \
  --product-output /path/to/output/领星产品录用-V392.xlsx \
  --pairing-output /path/to/output/领星产品配对-按MSKU.xlsx
```

默认读取 Skill 内两份官方模板。字段映射和校验要求见 [字段规则](skills/chenyu-lingxing-luru/references/field-mapping.md)，模板不应重建或擅自升级。

## 输出与职责

两份文件放在同一个 `lingxing-product-import/<日期_任务简称>/` 目录，见 [输出规范](references/output-paths.md)。结果需人工导入领星；不登录、上传或修改库存。

箱唛照片生成承运商发货发票归 [AI 物流](../chenyu-wuliu/README.md)，买家订单商业发票归 [AI 运营](../chenyu-yunying/README.md)。安装、测试与发布见仓库根 README。
