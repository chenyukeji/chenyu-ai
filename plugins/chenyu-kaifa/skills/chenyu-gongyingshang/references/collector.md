# 采集接口

## 环境和会话

Node.js 20+、Playwright及Google Chrome。当前已用Playwright 1.62.1运行。优先使用执行环境已有依赖；未提供时经安装权限在本Skill的scripts目录执行npm install，依赖见scripts/package.json，不把node_modules纳入发布源码。

从chenyu-ai仓库根运行，或传 --workspace <仓库根>。无仓库时，调用方必须同时传 --output <新任务目录> 和 --profile <受保护专用会话目录>，不能退回插件源码/安装缓存。

默认专用Chrome会话位于 outputs/chenyu-kaifa/_sessions/lingxing，含敏感登录状态，不交付、不共享、不提交。首次出现可见登录窗口，用户手动完成领星登录和二次验证，脚本最多等待900秒；可用 --login-timeout 修改。不同领星账户使用不同 --profile，不接普通Chrome默认profile，不并发打开同一profile。

如果已有本任务明确授权的专用Chrome，通过本机CDP访问，可显式传 --endpoint http://127.0.0.1:<端口>。只允许loopback，不向公网开放；连接失败就报告，不悄悄换另一个窗口/账户。无端点时启动专用浏览器，用完关闭并保留登录会话。

## 命令

助手将用户自然语言属性转成脚本参数，用户不必自己编写JSON。PowerShell字符串用单引号包裹：

    node <Skill目录>/scripts/collect-lingxing-1688.cjs 'https://detail.1688.com/offer/712371130191.html' --attributes '黑色蝶舞面具' --download-images
    node <Skill目录>/scripts/collect-lingxing-1688.cjs '<1688链接>' --attributes '{"颜色":"黑色","尺寸":"M"}' --download-images
    node <Skill目录>/scripts/collect-lingxing-1688.cjs '<1688链接>' --attributes '["完整规格一","完整规格二"]'

不传属性读取全部规格；此时加下载选项会下载全部规格图及商品主图。传属性时只下载已精确命中的规格图及主图。按URL去重，最多两张并发，校验HTTPS阿里CDN、重定向、图片类型和12MiB大小；不携带领星认证信息下载。

默认输出 outputs/chenyu-kaifa/supplier-data/<上海日期_商品编号>/，同名新运行追加 _02 等。显式 --output 必须不存在。与开发文档连续运行时，助手通过该参数让两个交付目录共用日期任务名。

## 文件和下游状态

- supplier-data.json：下游事实包，含schemaVersion、商品身份、来源、时间、公司名称、主图、起订量及selection。selection.selectedVariants只含唯一精确命中的SKU；selection.requests含每项匹配状态与候选。
- product.json：商品标题、供应商、属性选项、全部SKU、主图、起订量、单位、参考价、阶梯价及价格区间。每个SKU分别保留price、consignPrice、retailPrice、库存和规格图。
- raw-product.json：仅目标商品返回字段，不含账户请求头或Token。
- image-urls.json：主图和SKU图分开。report.html展示全部规格，图片需要网络；不表示全部规格已选定。
- images/ 与事实包assets：加下载参数才产生。每图含role、SKU映射、源URL、相对file、bytes及保存/失败状态；失败保留原因。
- lingxing-parsed.png：可选本地解析证据，截图失败不代替或推翻已校验响应。

success:true仅表示商品采集成功，还需检查selectionStatus、imageFailures及warnings。MATCHED是精确匹配；ALL是待选全规格；NEEDS_CONFIRMATION是至少一项未找到或歧义。不能将部分结果说成指定变体资料全部完成。

missingFields列出当前采集器尚未映射的重量、尺寸、材质、交期和议价字段；这些不能从竞品编成自有事实。内部解析路径来自实际UI响应，不是公开稳定API承诺；页面变化应修复适配器并重新验证。
