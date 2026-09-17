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
    "source": {"file": "brief.xlsx", "sheet": "Sheet1", "cells": ["D2"]},
    "raw_requirement": "完整原文",
    "normalizations": [{"from": "不要AI", "to": "自然真实的摄影风格", "reason": "用户选择AI制作；只处理制作指令"}],
    "inputs": [{"id": "photo-01", "path": "absolute path", "role": "product_photo", "reason": "用户标记实拍"}],
    "requirements": [{"id": "r1", "text": "左侧展示两件粉色钻贴", "source": "D2", "check": "count and visual location", "status": "unchecked", "evidence": null}],
    "exact_text": [],
    "output": {"width": 1600, "height": 1600, "format": "JPEG"},
    "status": "planned",
    "versions": [],
    "final_path": null,
    "display_reference": null,
    "issues": []
  }]
}
```

任务状态：planned、ready、generating、reviewing、passed、needs_review、blocked。要求状态：unchecked、pass、fail、unknown。生成前为planned，核实素材和要求后ready；有真实图像结果后才能reviewing；全部要求pass且相关文件检查通过才可passed。若像素规格无法核验则对应要求unknown，任务needs_review。

versions记录真实结果引用/路径、轮次、使用的原始素材、变更范围和检查结果。final_path仅用于真实存在文件；不能填预期文件名冒充交付。所有引用相对本次运行目录或使用绝对路径，源文件不得覆盖。

## 尺寸与文案

尺寸绑定具体部位和测量方向，并执行SKILL.md的“尺寸标注与缺失信息补全”。未注明轴名的两数尺寸默认依次为长、宽；明确轴名优先，结合匹配素材确定具体测量部位。每个方向分别标注cm / in，英寸按1 inch=2.54cm换算并保留两位小数，禁止乘法式组合尺寸。缺失尺寸、数量或文案时，从匹配当前产品的参考图补全并记录来源；仅布局参考或不匹配的竞品图不能作为产品事实，实拍与明确规格优先。

准确文案单独保存，不把“右下角加标题”等制作指令印到图上。保留要求的大小写、拼写及标点；明显错词在非逐字场景可修正并记录，不能静默改产品性质。中文括号释义通常是给制作者看的，结合指定语言判断是否上图。

“不要AI”转换必须语义判断：仅当它是制作方法或风格指令且用户已要求AI制作。若它出现在产品印刷文字、引用内容，或用户最新要求真实来源，不应用该转换。不设计全局字符串删除器。
