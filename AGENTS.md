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

