# 输入与任务记录

## Excel读取后的语义核对

同时查看单元格内容、合并范围、图片锚点与实际视觉内容。提取脚本保留所有drawing图片（同一图片不同摆放也保留），并把未锚定media列为unplaced_media。未锚定不等于未使用，不可删去。截屏、产品拼图和套装清单可能也是产品证据，但不是自动可用的高清抠图素材。

Excel可能包含ZIP附件图标和OLE嵌入对象，实际高清素材藏在附件中。检查manifest的embedded_objects和recovered_images：脚本自动恢复ZIP兼容附件中的图像，包括部分OLE包装的ZIP；不保证解析所有OLE格式。在宣告缺少原图之前，查看恢复的全部图片；仍有告警时使用可用只读归档/OLE工具核查。不执行附件程序、宏或脚本，不盲目extractall到任意路径。无法解析时明确“嵌入附件尚未读出”，不要说“用户没提供实拍”。图标本身不是产品素材。检查嵌入素材与实际售卖款式是否一致，不能因它在附件中就自动认定为实拍。

把每张素材分为product_photo（用户指定的实拍）、product_reference（其他产品证据）、layout_reference、scene_reference、detail_reference或unknown。不要把参考照片自动标成实拍。一个素材可以支持多个任务；一个任务可以有多个例图。依据原文、标签和视觉内容作匹配，并写明原因。判断不确定必须保留unknown，不按“最近行”强行归属。

本用户常见作图单可有A列图序、B/C列例图、D列要求、F列产品内容，但该布局只是读取线索，不是解析硬编码。第七张可能明确有两张例图；尺寸例图可能跨两个行块。变体仅做部分图片时依原文生成那些图片，不复制整套作为新增任务。

## 任务文件

生成本次运行的tasks.json，遵循以下字段约定。该文件由执行agent在读图后编写，提取脚本不替代判断。

```json
{
  "source_files": ["absolute path"],
  "products": [{
    "id": "sku-variant",
    "facts": [{"key": "pack_quantity", "value": 2, "source": "Sheet1!F2/image-001", "status": "confirmed"}],
    "photo_ids": ["photo-01"],
    "uncertainties": []
  }],
  "tasks": [{
    "id": "sku-variant-01",
    "product_id": "sku-variant",
    "image_type": "main_image",
    "production_mode": "verified_render",
    "product_confirmation": "confirmed",
    "source": {"file": "brief.xlsx", "sheet": "Sheet1", "cells": ["D2"]},
    "raw_requirement": "完整原文",
    "normalizations": [{"from": "不要AI", "to": "自然真实的摄影风格", "reason": "用户选择AI制作；只处理制作指令"}],
    "inputs": [{"id": "photo-01", "path": "absolute path", "role": "product_photo", "reason": "用户标记实拍"}],
    "requirements": [{"id": "r1", "text": "左侧展示两件粉色钻贴", "source": "D2"}],
    "exact_text": [],
    "output": {"width": 1254, "height": 1254, "format": "JPEG"},
    "versions": [],
    "final_path": null,
    "display_reference": null,
    "issues": []
  }]
}
```

`image_type`必须为`main_image`、`infographic_detail`或`lifestyle_scene`。表头、分区标题或原文出现“主图”时记录为`main_image`；不要根据行号猜测。`main_image`另记`main_style`（`clean_white`、`white_with_use_inset`或`scene_hero`）和选择依据。前两种形式的requirements须包含以纯白`#FFFFFF`为生成目标的底色及无可见色偏/渐变/纹理/未经要求的场景；`scene_hero`须记录真实使用关系、主体层级与产品外观约束。这些内容用于生图前输入，不要求生成后视觉复核或白底像素复查。

参考制作或原创概念按主 Skill 记录 production_mode 和 product_confirmation；待确认实物信息不能写成已确认。

任务包记录整套共同视觉方向，包括主题、配色、光线及元素风格；各任务记下自主补足的构图和主题装饰，区分原文明确要求与模型设计，并带入逐张生成输入。任务记录保存每张图片的原始要求、所用素材、输出规格、实际成品路径或展示引用，以及需要说明的具体缺口；不建立逐项 pass/fail 状态流程。生成成功后只做轻量文件与交付数量检查，不建立视觉复核、通过状态或自动返修记录；不能据此声称画面已核对。

versions记录真实结果引用/路径及使用的原始素材。final_path仅用于真实存在文件；不能填预期文件名冒充交付。所有引用相对本次运行目录或使用绝对路径，源文件不得覆盖。

## 共同风格与逐图设计记录

在 `products[]` 对应产品的 `visual_direction` 保存共同方向。已有作图包同名字段时复用，字符串或结构化描述均可；它属于设计资料，不是产品事实证据。各任务可用 `design_decisions` 记录自主补足内容，原始要求仍保留在 `raw_requirement`。以下为字段示例，按实际任务填写，不要求复制示例配色：

```json
{
  "visual_direction": {
    "theme": "秋季家居",
    "palette": ["暖米色背景", "金黄色叶片", "深棕色小面积强调"],
    "light": "柔和暖阳",
    "element_style": "写实叶片与织物，自然材质",
    "typography": "统一简洁标题与尺寸标签层级"
  },
  "design_decisions": {
    "composition_basis": "主要参考的自然近景，按本张目的调整取景",
    "elements": "后景安排虚化黄色叶片，前景保留产品纹理",
    "placement": "主体近景居中，文字放在可读的背景区域"
  }
}
```

场景参考主图在任务设计中记录纯白外框宽度。四宫格任务按左上、右上、左下、右下记录每格 `scene`、`title`、`title_placement`，四个标题加入任务 `exact_text`。这些记录直接用于生成输入，不作为生成后逐图复核清单。

## 尺寸与文案

尺寸绑定具体部位和测量方向，并执行SKILL.md的“尺寸标注与缺失信息补全”。未注明轴名的两数尺寸默认依次为长、宽；明确轴名优先，结合匹配素材确定具体测量部位。每个方向分别标注cm / in，英寸按1 inch=2.54cm换算并保留两位小数，禁止乘法式组合尺寸。缺失尺寸、数量或文案时，从匹配当前产品的参考图补全并记录来源；仅布局参考或不匹配的竞品图不能作为产品事实，实拍与明确规格优先。

准确文案单独保存，不把“右下角加标题”等制作指令印到图上。保留要求的大小写、拼写及标点；明显错词在非逐字场景可修正并记录，不能静默改产品性质。中文括号释义通常是给制作者看的，结合指定语言判断是否上图。

“不要AI”转换必须语义判断：仅当它是制作方法或风格指令且用户已要求AI制作。若它出现在产品印刷文字、引用内容，或用户最新要求真实来源，不应用该转换。不设计全局字符串删除器。

网站任务完成状态按实际成品是否交齐判断；仍有具体问题时作为交付注释说明。
