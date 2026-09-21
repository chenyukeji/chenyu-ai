# 内部 Playwright 采集

本 Skill 使用 `scripts/playwright_collector.py`，不依赖 Browser/Playwright MCP。

## E 策略

1. 从 Amazon US/DE 新品榜读取站点、ASIN、榜单名次、节点、采集时间和来源。
2. Amazon 结果进入补数时只保留上述身份字段。
3. 使用卖家精灵“查竞品”按站点和 ASIN 补充标题、上架时间、Review、售价、BSR、预估月销量、品类、商品链接和图片。每个站点开始查询前必须切换站点，并回读控件确认实际值为“美国站”或“德国站”；回读不一致时停止该站点查询，不得把无结果当成 ASIN 缺失。
4. 卖家精灵缺字段时保持空值，并在最终理由中明确说明。

单个 ASIN 的默认查询兜底超时为 8 秒。采集器每 200ms 检查一次结果；匹配到 ASIN、查询按钮完成一次忙碌状态或竞品表明确显示“暂无数据/无结果”时立即结束本条查询，不等待完整超时。登录、安全验证和首次页面加载使用独立超时，不受该 8 秒限制。每条结果的 `elapsed_ms` 与 `stop_reason` 用于分析实际耗时；需要适配较慢网络时可传入 `query_timeout_ms` 覆盖默认值。

## 登录

本地凭据默认读取仓库根目录 `.chenyu-secrets/sellersprite.json`。文件结构：

```json
{
  "username": "账号",
  "password": "密码"
}
```

凭据只用于本地 Playwright 登录，不写入运行结果。出现验证码或滑块时停止自动采集，并使用可见浏览器完成验证。

## 输出与续跑

每个站点分别保存 Amazon ASIN 和卖家精灵补数结果。卖家精灵原始结果中的 `query_metadata` 保存请求站点和控件实际选中值，便于核对。重复运行同一个 `run_dir` 时复用已有 Amazon 文件和卖家精灵查询结果；已返回 `not_found_or_unavailable` 的 ASIN 也会作为负结果缓存，避免每次续跑都等待超时。传入 `refresh=true` 或 `refresh_sellersprite=true` 时才强制重新查询。

采集状态不是 `complete` 时仍保留已经完成的记录，并在运行清单中写入警告。
