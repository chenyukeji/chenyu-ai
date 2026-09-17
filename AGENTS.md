# Chenyu Amazon AI OS

This repository packages role-based Amazon workflows as portable plugins for company employees.

## Route requests

- Full Amazon image-set production belongs to `plugins/chenyu-meigong/skills/chenyu-zuotu`.
- Precise local image retouching belongs to `plugins/chenyu-meigong/skills/chenyu-jingxiu`.
- Mixed creative requests enter `plugins/chenyu-meigong/skills/chenyu-meigong`.
- Operations requests enter `plugins/chenyu-yunying/skills/chenyu-yunying`.
- Listing writing belongs to `plugins/chenyu-yunying/skills/chenyu-listing`.
- Image brief planning belongs to `plugins/chenyu-yunying/skills/chenyu-zuotuyaoqiu`.
- Advertising skill chenyu-guanggao is planned, not implemented.
- Market opportunity, product design, profitability, and product-development decisions belong to `plugins/chenyu-kaifa/skills/chenyu-kaifa`.
- Supplier comparison, procurement planning, and supply tracking belong to `plugins/chenyu-caigou/skills/chenyu-caigou`.
- Scheduled Amazon New Releases collection, browser navigation, snapshot ingestion, or database maintenance belongs only to the sibling `../amazon-new-release-collector` project.

## Packaging

- Each directory directly under `plugins/` is an independent employee-facing plugin.
- Each plugin root contains `plugin.json` and `skills/`.
- Add MCP servers, apps, or standalone agents only to the plugin that owns them and only when there is a real implementation.
- Do not package repository prototypes, examples, caches, or unrelated departments into an employee ZIP.

## Boundaries

Do not treat example files as live research. Do not bypass Amazon access controls, modify stores or advertising, contact suppliers, purchase goods, make payments, or publish to Amazon without explicit user authorization.
