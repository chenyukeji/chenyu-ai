---
name: amazon-listing-launch
description: 根据运营负责人已审核的产品事实，独立生成亚马逊商品详情页草稿、本地化内容、七图方案、上传工作簿、合规资料包和上架前检查。可以选择附带此前的产品决策卡；不得用本技能决定是否开发产品，也不得在未经明确授权时发布。
---

# Amazon Listing & Launch

Create a consistent Amazon Upload Package for an operations owner to review. Package generation does not publish anything and does not depend on another skill having run.

## Input and source of truth

1. Require product facts that the operations owner has reviewed. They may arrive as `product_master.json`, a product specification, or a completed information sheet. A Product Decision Card may be supplied as supporting evidence but is not required.
2. Create and validate `product_master.json` against `schemas/product_master.schema.json`. Resolve quantity, color, material, dimensions, weight, packaging, target audience, functions, SKU, EAN, brand, manufacturer, responsible person, price, inventory, and compliance facts before marking the package complete. Missing facts may remain only in a draft clearly labelled `NOT_READY`.
3. Treat Product Master as the content source of truth. If a fact changes, update it first and regenerate dependent artifacts.

## Content and package

1. Research current marketplace keywords where needed. Write each locale natively rather than translating sentence by sentence. Keep title, five bullets, description, search terms, and attributes consistent with Product Master.
2. Do not invent certifications, test results, performance, compatibility, included quantities, or accessories. Avoid prohibited or unverifiable claims.
3. Create seven image briefs: main image, primary benefit, in-use, dimensions, function detail, scenario, and multi-scenario. Each brief needs composition, purpose, copy, and an AI prompt; the prompt must preserve exact product facts.
4. Save localized content in one JSON object matching `examples/listings.json`, then run:

   `python -m amazon_product_os launch --product-master <master.json> --listings <listings.json> --output-dir <folder>`

   Add `--decision <decision.json>` only when the operations owner wants that earlier record included for traceability.

5. Inspect `pre_launch_check.json` and the rendered/upload workbook. `READY_FOR_OPERATIONS_REVIEW` means the package passed automated checks; it is not permission to publish.

## Boundary

Finish with `等待运营负责人审核`. Do not invoke another skill, upload, publish, change live inventory, or spend advertising budget without explicit authorization from the user responsible for that action.
