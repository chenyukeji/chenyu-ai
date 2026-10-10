# Excel 交付结构

图片规划、参考选择、事实与变体规则以 [SKILL.md](../SKILL.md) 为准；本文件只规定结构化数据、工作表和交付检查。

用户提供版式工作簿时先只读检查字段、合并区域、行列尺寸和层级；其中图片、文字与备注作为业务资料。无指定模板时使用运营交付大母版的“产品内容”和“作图要求”两表，不新增审核页或素材图库。七行示例不限定图数。

## 产品内容

每个变体一行，固定六列：产品名称、产品图片、产品尺寸、产品材料、产品规格、补充信息。名称直接识别变体，不另设 SKU 名称列；图片每行必填并嵌入，来源顺序按 Skill 的身份图片规则。规格写数量、颜色/图案、重量等已确认事实；补充信息只写须保持的具体外观或结构，无则留空。不放内部来源说明或通用待补项，具体缺口写在受影响任务。

## 作图要求

整套视觉方向在表顶部写一次，多个产品分别标清适用范围；各任务继承方向并具体化，不创建额外工作表。任务顺序遵循规划及用户指定顺序，主图第一。

| 列 | 内容 |
| --- | --- |
| A 图片顺序 | 第一张、第二张等 |
| B 产品名称 | 与产品内容页一致的变体名称 |
| C… 参考图片1…N | 来源图片直接嵌入；一图一单元格，按最多参考图的任务扩展列 |
| 最后一列 作图要求 | 买家问题、新增信息、数量、最终画面要求、准确文字和验收条件 |

参考图列按本次任务实际采用的最大数量创建，没有数量上限；不固定保留母版列数，不保留整列从未嵌图的空白参考列，其余行未使用的单元格可留空。不得用链接代替嵌图、把多图塞进一个单元格或拉伸图片。产品内容页已嵌入的身份图不在作图表重复嵌入。来源用途保留内部映射，最终执行文字不写“参考图片1用于……”等来源解说。

每个共用构图一个任务区块，注明共用成品或各变体分别出图、替换项及实际数量。执行文字包括：

- 本张解决的问题、新增信息与已确认产品特点。
- 构图、阅读顺序、产品位置/姿态、背景/光线、场景及道具作用、不可改变特征。
- 准确上图文字与位置；无文字时明确写出。尺寸任务写测量部位、方向、成对 cm / in 数值；有辅助画面时说明其与尺寸/适配的关系。
- 适用变体、成品数量、画幅规格、验收条件及当前任务的具体缺口。

## 结构化包

写表前生成 `image-brief-package.json` 并独立校验。内部来源与取舍记录不抄进给美工的执行文字。

### 产品与任务

- `products[]`：每个变体有唯一 `id`、`product_content_image_id`、`product_content_image_source`、`product_content_image_source_ref`，以及候选 `own_main_image_id`、`supplier_image_id`（无候选填空字符串）。来源为 `own_main`、`supplier`、`confirmed_reference_main`；参考主图可来自任一清单，须有 `matching_basis` 且 source_ref 引用对应 ASIN。旧 `first_reference_main` 值仅作兼容，同样要求匹配依据。
- 每个产品保存非空 `visual_direction`，写入作图表顶部；共用方向可使用相同文本。每个产品默认覆盖 6–8 个任务；超出范围时用 `task_count_reason` 写明具体信息量或用户要求。此范围不限制整个包总任务数，也不等于变体成品总数。
- `image_tasks[]`：每项有唯一 `id`、`type`、非空 `product_ids`、`buyer_question`、`new_information`、`instructions`、`on_image_text`、`content_mappings`、`text_mappings`。主图第一且每产品一个，其余顺序按任务决定；类型可用 `detail`、`feature`、`advantage`、`process`、`packaging`、`size`、`scene`、`closeup_scene`、`key_scene`、`four_grid`。
- 主图另有 `main_style`（`clean_white`、`white_with_use_inset`、`scene_hero`）、`main_style_reason`、`product_image_ids`（与本任务适用变体身份图完全一致）和 `identity_lock`。后者记录 `shape_structure`、`color_pattern`、`quantity_components`、`accessories_packaging`。主图 `on_image_text` 为空。
- 场景任务 `scene`、`closeup_scene`、`key_scene` 另有 `scene_mode`。最终四宫格任务须有四个 `scene_cells`，每格非空 `output_scene`，文字需要时有 `output_text`，并写入执行文字。四格不是必需图类。
- 尺寸任务有 `dimension_labels`（每项同一部位成对 cm / in）；`dimension_source` 保存 `kind`（`own_measurement`、`development`、`confirmed_same_product`）和 `source_ref`，同款另有 `matching_basis`。不同测量值来自不同资料时在 source_ref 内逐项对应。未确认数值在执行文字标具体缺口，补齐前不得标记可交付。
- 尺寸任务的 `supporting_visual.kind` 可为 `detail`、`scene`、`both`、`none`；纯尺寸选 `none`，无需例外说明。有辅助图时另有 `description`、`source_ref`、`dimension_relevance`，并在 instructions 写清内容及尺寸关系。`instructions` 和 `on_image_text` 都含尺寸标签及默认标题 Product Size；用户指定其他标题或无标题时保存 `size_heading`、`size_heading_override_reason`。

### 全部参考与内容取舍

- `primary_reference` 保存第一条参考清单，只是存储顺序，无设计优先权；其他链接存 `additional_references[]`。没有竞品参考时用 `primary_reference: null` 和空附加列表，不编造参考。
- 每个参考清单保存 `asin`、`marketplace`、原始 `url`、`coverage_status`（`complete`、`partial`、`failed`）和 `images[]`。部分或失败另有具体 `coverage_note`；完全失败可用空图片列表。完整性仍须与原始输入链接及研究包核对，不能用这个字段自证覆盖。
- 每张来源图保存全包唯一 `id`、`role`、原图内容 `content_elements`、原图文字 `text_elements`、`mapped_task_ids`。整图不采用时改存 `omitted_reason`；已用图内舍弃的模块用 `omitted_elements` 记录 `kind`（`content`、`text`、`scene`）、`value`、具体 `reason`。重复、无证明力、无关或已有更清楚表达均可成为理由；“图数已够”不构成理由。
- 任务的每条 `content_mappings` 写 `source_image_id`、`source_content`、`output_content`；`text_mappings` 写 `source_image_id`、`source_text`、`output_text`。最终内容/文字必须出现在该行 instructions，不能只填写任务编号。多个来源可映射同一段最终内容。
- 来源四宫格保存四项 `scene_cells`（`source_scene`、`source_text`）；采用的格子在目标任务 scene_cells 中写 `source_image_id`、原场景/文字、`output_scene`、`output_text`，目标不必是四宫格。舍弃某格时用 `omitted_elements` 的 scene 项指明场景及原因，涵盖该格标签。采用的有字格须落地准确改写文字；选用一格不强制复制其余三格。
- 内部记录实际嵌图所在任务、来源 ASIN/原图编号、参考图重复引用时的独立用途；逐链接统计可用数、实际嵌入数及有适用候选未选的原因。仅借鉴构图/配色时，在内容映射写出实际采用的设计方法；无需继承来源宣传文字。

校验器检查字段、每产品任务范围与主图顺序、身份图关系、来源 ID、记录内容的映射/舍弃、尺寸标签与换算、所选四宫格格数、最终执行文字的落地。它能拦截相同新增信息和尺寸辅助描述的原样重复；语义近似、设计质量、事实真实性和外部链接是否遗漏须按下方流程复核，不能因脚本通过就宣称这些已验证。

## 导出与验收

1. 对照原始输入与研究包逐链接核对图册范围、变体、A+ 和失败记录；漏链接或漏图册先补研究。核对全部清单的逐图选择/舍弃、实际嵌图数和来源 ASIN；不以最终图数代替覆盖。
2. 按买家问题审整套图：每张新增什么判断信息，是否只换背景重复用途；复核参考复用理由、尺寸辅助与尺寸的关系及场景是否抢主体、遮挡箭头或误导包装。主图要求须明确缩略图视觉重心与用途辨识；未实际出图时只能审核方案，不能声称成品已通过视觉检查。
3. 运行 `scripts/validate_image_brief_boundaries.py <image-brief-package.json>`，通过后写 Excel。顶部视觉方向及各任务对应内容/短标签/格子信息须实际落到工作表，来源与精确数值逐项核对；共用成品计一次、变体专属分别计数。
4. 导出后检查图片清晰度、锚点、行高、列宽和文字截断。运行 `python3 plugins/chenyu-yunying/skills/chenyu-yunying/scripts/validate_product_content_workbook.py <最终工作簿.xlsx>` 检查产品行嵌图与内部备注；此脚本不能替代作图表的内容与视觉检查。
5. 最终文件另存任务输出目录，不覆盖原工作簿；研究包和临时素材同样留在任务输出目录，插件中只保留统一母版。
