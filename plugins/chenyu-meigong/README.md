# 晨玙 Amazon 美工插件

`chenyu-meigong` 接收作图单、产品实拍、参考素材与修改要求，交付实际商品图片。当前版本见 [plugin.json](plugin.json)。

## 能力与路由

| Skill | 适用需求 | 成果 |
| --- | --- | --- |
| [美工总入口](skills/chenyu-meigong/SKILL.md) | 综合图片需求、需要自动选择处理方式 | 协调对应专业能力 |
| [整套作图](skills/chenyu-zuotu/SKILL.md) | 从作图单、实拍和参考素材制作整套图片 | 按图号交付独立完整图片 |
| [主图优化](skills/chenyu-zhutu-youhua/SKILL.md) | 已有主图，希望主动改善构图、主体比例、层次、留白和光影 | 优化后的完整主图 |
| [局部精修](skills/chenyu-jingxiu/SKILL.md) | 明确指定白边、伪影、局部颜色、形状、材质或边缘问题 | 累积修改后的完整图片 |

已有主图的审美优化与保持构图的局部精修分别走专业 Skill；从素材重新制作使用整套作图。需要先设计作图要求时，使用运营插件的作图要求 Skill。

## 输入和执行

1. 区分产品实拍、产品规格、作图要求与视觉参考。
2. 核对图号、SKU、变体、数量、颜色、尺寸和素材对应关系。
3. 读取作图单、工作表及嵌入图片，形成任务记录。
4. 使用实际可用的图像工具生成或编辑，再按原资料检查并返修。
5. 交付真实存在的完整图片，不能用 Prompt、计划或局部裁图代替成品。

产品外观与售卖事实必须有自有资料或确认信息支持；参考图中的配件、品牌和场景道具不能自动变成商品内容。主图背景、尺寸标注、人物场景、文字和返修规则集中在下列文件。

## 规则与工具

| 文件 | 用途 |
| --- | --- |
| [输入与任务记录](skills/chenyu-zuotu/references/input-and-tasks.md) | Excel、素材角色与图号任务结构 |
| [制作与返修](skills/chenyu-zuotu/references/production-and-review.md) | 图像制作、真实性、主图背景、尺寸和视觉检查规则 |
| `skills/chenyu-zuotu/scripts/extract_brief.py` | 提取作图单及嵌入素材 |
| `skills/chenyu-zuotu/scripts/check_outputs.py` | 检查文件、尺寸、格式和重复内容 |

文件检查不等于视觉审核或平台审核。生成和编辑依赖图像工具，不由这些辅助 Python 脚本独立完成。

## 输出与边界

整套出图、精修和主图优化分别保存到 `image-production`、`retouch` 和 `main-image-optimization`，见 [输出目录规范](references/output-paths.md)。

不自动上传或替换 Amazon 店铺图片。具体执行以专业 Skill 和引用规则为准；安装、测试与发布见仓库根 README。
