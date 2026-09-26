# Automatic plugin updates

Install `chenyu-plugin-sync.service` and `chenyu-plugin-sync.timer` into
`/etc/systemd/system/`, then run `systemctl daemon-reload` and
`systemctl enable --now chenyu-plugin-sync.timer`.

The timer checks GitHub `main` every day at 00:00 server local time. The script only fast-forwards
a clean local `main`, validates all four plugin manifests, refreshes Codex's
installed copies, compares every installed file with the checkout, and removes
old cache versions after all four pass. A dirty or divergent checkout is left
untouched. Failed checks are retried on the next timer run.

`/home/ubuntu/chenyu/chenyu-runtime/plugin-sync-status.json` records the latest
check and revision. `journalctl -u chenyu-plugin-sync.service` has detailed
output. Run `systemctl start chenyu-plugin-sync.service` to check immediately.

The website backend reads the same Git checkout on every workspace request.
At 00:10 Asia/Shanghai, an open admin page calls the same server sync workflow and reuses the midnight result if it already succeeded. Other pages refresh displayed capabilities once daily. Admins can also run the workflow on demand from the AI workspace.
