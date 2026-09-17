# Chenyu Amazon AI OS

This repository packages role-based Amazon workflows as portable plugins for company employees.

## Route requests

- Full Amazon image-set production belongs to `plugins/chenyu-amazon-creative/skills/chenyu-zuotu`.
- Precise local image retouching belongs to `plugins/chenyu-amazon-creative/skills/chenyu-jingxiu`.
- Listing, advertising, sales analysis, and store operations belong to `plugins/chenyu-amazon-operation/skills/chenyu-yunying`.
- Market opportunity, product design, profitability, and product-development decisions belong to `plugins/chenyu-amazon-development/skills/chenyu-kaifa`.
- Supplier comparison, procurement planning, and supply tracking belong to `plugins/chenyu-amazon-procurement/skills/chenyu-caigou`.
- Scheduled Amazon New Releases collection, browser navigation, snapshot ingestion, or database maintenance belongs only to the sibling `../amazon-new-release-collector` project.

## Packaging

- Each directory directly under `plugins/` is an independent employee-facing plugin.
- Each plugin root contains `plugin.json` and `skills/`.
- Add MCP servers, apps, or standalone agents only to the plugin that owns them and only when there is a real implementation.
- Do not package repository prototypes, examples, caches, or unrelated departments into an employee ZIP.

## Boundaries

Do not treat example files as live research. Do not bypass Amazon access controls, modify stores or advertising, contact suppliers, purchase goods, make payments, or publish to Amazon without explicit user authorization.
