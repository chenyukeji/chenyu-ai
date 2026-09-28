# 1688 供应商采集

本 Skill 使用 `scripts/collector_1688.py` 和本机 Playwright Chromium。采集目标是按已经筛出的采购关键词读取少量候选供应商，不做全站爬取。

## 安全运行方式

- 每个任务只启动一个持久浏览器 Context，默认使用可见窗口和一个页面。
- Profile 默认保存在 `CHENYU_BROWSER_DATA_DIR/1688`；未配置时使用当前工作目录下已被 Git 忽略的 `.chenyu-browser-profiles/1688`。Cookie、localStorage 和登录态会在后续任务中复用。
- 每个关键词默认只读首屏前 20 条，最多 30 条；默认只进入前 5 个详情页。
- 搜索与详情页之间默认随机等待 2.5～5.5 秒；网络错误采用有限次数指数退避，不并发刷新。
- 不自动识别、破解或绕过验证码。检测到验证码或登录页时，检查点状态改为 `CAPTCHA_DETECTED` 或 `LOGIN_REQUIRED`。

可见浏览器中默认等待人工处理 300 秒。人工完成后，采集器检测到验证页消失会自动恢复；超时、无头模式或窗口被关闭时保存当前位置并返回。之后使用同一个 `run_dir` 执行 `resume_1688_suppliers`，程序复用同一 Profile，并从检查点中的关键词、阶段和详情序号继续。

## 首次采集

```json
{
  "skill_action": "collect_1688_suppliers",
  "queries": ["新生儿出生公告木牌", "婴儿出生信息木牌"],
  "max_results_per_query": 20,
  "detail_limit": 5,
  "headless": false,
  "manual_timeout_seconds": 300
}
```

如需指定稳定 Profile，可传入 `profile_dir`，或在插件进程外设置 `CHENYU_BROWSER_DATA_DIR`。不要把账号密码写入任务 JSON、提示词、源码或日志；登录只在可见浏览器中由员工完成。

## 验证后续跑

```json
{
  "skill_action": "resume_1688_suppliers",
  "run_dir": "C:/path/to/outputs/chenyu-caigou/supplier-comparison/2026-09-28_product",
  "headless": false,
  "manual_timeout_seconds": 300
}
```

任务目录保存：

- `1688-checkpoint.json`：任务状态、游标、已完成记录和错误；每个阶段原子更新。
- `1688-results.json`：可供后续供应商比较读取的扁平记录。

`CAPTCHA_DETECTED` 和 `LOGIN_REQUIRED` 是人工节点，不是采集失败。不要通过循环刷新、频繁切换 IP、并发浏览器或伪造验证结果继续运行。
