# 内部 Playwright 采集

本 Skill 使用 `scripts/playwright_collector.py`，不依赖 Browser/Playwright MCP。

## E 策略

1. 从 Amazon US/DE 新品榜读取站点、ASIN、榜单名次、节点、采集时间和来源。
2. Amazon 结果进入补数时只保留上述身份字段。
3. 使用卖家精灵“查竞品”按站点和 ASIN 补充标题、上架时间、Review、售价、BSR、预估月销量、品类、商品链接和图片。
4. 卖家精灵缺字段时保持空值，并在最终理由中明确说明。

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

每个站点分别保存 Amazon ASIN和卖家精灵补数结果。重复运行同一个 `run_dir` 时复用已有 Amazon 文件；传入 `refresh=true` 才重新采集。

采集状态不是 `complete` 时仍保留已经完成的记录，并在运行清单中写入警告。
