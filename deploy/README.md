# 插件自动更新

## 部署

将本目录的 `chenyu-plugin-sync.service` 和 `chenyu-plugin-sync.timer` 安装到 `/etc/systemd/system/`，执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chenyu-plugin-sync.timer
```

定时器每天按服务器本地时间 00:00 运行。管理员也可执行 `sudo systemctl start chenyu-plugin-sync.service` 立即检查。

## 更新行为

`scripts/sync_remote_plugins.py` 维护五个插件：开发、运营、美工、仓库、物流。

1. 获取 GitHub `main` 最新版本。
2. 仅对干净的本地 `main` 执行快进更新；有未提交改动或分支分歧时保留现场并报告状态。
3. 验证各插件名称、两份清单的纯语义版本和 Skill 入口。
4. 从已配置的 `personal` marketplace 更新安装缓存，比较源码与安装文件哈希。
5. 全部校验成功后清理这五个插件的旧缓存版本，不改写市场登记或处理其他插件。

服务器的 `~/plugins/<插件名>` 应指向对应 Git 源目录，personal marketplace 应已登记这些插件。源码必须先提交并推送，再刷新安装缓存。

## 状态与网站

- 状态文件：`/home/ubuntu/chenyu/chenyu-runtime/plugin-sync-status.json`。
- 日志：`journalctl -u chenyu-plugin-sync.service`。
- 网站后端读取同一份插件源码；管理员页面在 00:10 Asia/Shanghai 调用相同同步流程，当天已成功则复用结果。
- 页面“更新插件”可手动触发；普通页面每天刷新能力信息。

更新失败不会被标为成功，后续定时检查会再次尝试。插件同步不负责网站代码部署，也不安装 Windows＋WPS 等业务执行环境。
