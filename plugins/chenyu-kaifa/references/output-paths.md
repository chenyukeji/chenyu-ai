# 输出目录规范

除非用户明确指定其他保存位置，所有开发任务文件统一写入当前工作空间中的 `chenyu-ai` 仓库：

```text
<chenyu-ai>/outputs/chenyu-kaifa/product-discovery/<YYYY-MM-DD_产品简称>/
<chenyu-ai>/outputs/chenyu-kaifa/product-development/<YYYY-MM-DD_批次简称>/
<chenyu-ai>/outputs/chenyu-kaifa/supplier-data/<YYYY-MM-DD_产品简称>/
```

先定位包含 `plugins/chenyu-kaifa` 的 `chenyu-ai` 仓库根目录；若当前目录不是仓库，可检查当前工作空间下唯一的 `chenyu-ai` 子目录。无法唯一定位时要求调用方传入 `run_dir`，不得退回插件源码目录、安装缓存或任意当前目录。

任务文件夹使用执行当天的本地日期和简短品类、产品或批次名，例如 `2026-09-20_party-supplies`。清理 Windows 不允许的路径字符，无法确定时使用稳定的任务简称。同名文件夹已经存在且本次是新运行时，依次使用 `_02`、`_03`；只有用户明确要求续跑时才复用原目录并传入其 `run_dir`。

`product-discovery` 保存原始请求、采集结果、补数、候选池、评分明细和最终 `开品结果.xlsx`。

`supplier-data` 保存1688供应商事实包、规格、匹配结果及图片；与开发文档连续运行时复用日期任务名。专用领星会话保存在 `outputs/chenyu-kaifa/_sessions/lingxing` 或执行器指定受保护目录，登录状态不交付或提交。

`product-development` 保存产品开发文档。一次任务含多个产品时，共用一个日期批次目录，但每个产品必须是独立的 `.xlsx` 文件；同一产品的多个变体放在该产品工作簿的第三张详情表中，不能按变体拆成多个文件，也不能把多个产品合成一个工作簿。

只查看状态或解释策略时不创建空目录。原始输入不覆盖，任务成果不进入插件包或 Git。

用户明确指定的输出目录优先于本规范。
