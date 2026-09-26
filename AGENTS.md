# Chenyu Amazon AI OS

This repository packages role-based Amazon workflows as portable plugins for company employees.

## Route requests

- Full Amazon image-set production belongs to `plugins/chenyu-meigong/skills/chenyu-zuotu`.
- Precise local image retouching belongs to `plugins/chenyu-meigong/skills/chenyu-jingxiu`.
- Mixed creative requests enter `plugins/chenyu-meigong/skills/chenyu-meigong`.
- Operations requests enter `plugins/chenyu-yunying/skills/chenyu-yunying`.
- Competitor Listing and image research belongs to `plugins/chenyu-yunying/skills/chenyu-jingpin`.
- Listing writing belongs to `plugins/chenyu-yunying/skills/chenyu-listing`.
- Image brief planning belongs to `plugins/chenyu-yunying/skills/chenyu-zuotuyaoqiu`.
- Advertising skill chenyu-guanggao is planned, not implemented.
- Amazon product-discovery requests enter `plugins/chenyu-kaifa/skills/chenyu-xuanpin`.
- Supplier comparison, procurement planning, and supply tracking belong to `plugins/chenyu-caigou/skills/chenyu-caigou`.

## Packaging

- Each directory directly under `plugins/` is an independent employee-facing plugin.
- Each plugin root contains `plugin.json` and `skills/`.
- Add MCP servers, apps, or standalone agents only to the plugin that owns them and only when there is a real implementation.

## GitHub synchronization

- The user has authorized automatic commits and pushes for completed repository changes. After validation, commit the task-related changes and push them without waiting for a separate reminder; leave unrelated edits and generated business files out of the commit.
- Treat the GitHub `main` branch as the single source of truth for plugin source, rules, tests, manifests, and the repository marketplace.
- Before changing a plugin, fetch the current remote branch and reconcile it with the local checkout without discarding unrelated work.
- After changing a plugin, update its Codex cachebuster in `.codex-plugin/plugin.json`, validate the affected Skill and plugin, run relevant tests, commit the source change, and push it to GitHub before considering the work complete.
- Reinstall or refresh local plugin caches only from the same committed source that was pushed to GitHub. Do not leave an installed plugin ahead of or behind the repository source.
- After verifying the new installation, completely remove obsolete installed cache versions and old copied plugin or Skill backups. Keep only the current installed version and the Git-tracked source; do not reuse an old copy for later updates.
- Verify after pushing that local `HEAD`, its upstream branch, and the remote branch resolve to the same commit. If pushing or verification fails, report the repository as unsynchronized instead of claiming completion.
- Generated business outputs remain under `outputs/`. Distribution archives under `dist/` are derived release artifacts, not source files; regenerate them from a tagged or committed source and publish them as GitHub release assets when they need to be distributed.

## Output storage

- Generated business artifacts belong under `<chenyu-ai>/outputs/<plugin-name>/<deliverable-part>/<YYYY-MM-DD_product-short-name>/` unless the user explicitly chooses another destination.
- Reuse the same dated task-folder name across deliverable parts of one request. If that folder already exists for a new run, append `_02`, `_03`, and so on instead of overwriting it.
- Do not create empty output folders for read-only work, and never write task outputs into plugin source, installed plugin caches, or distribution ZIP files.

