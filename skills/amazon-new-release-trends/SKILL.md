---
name: amazon-new-release-trends
description: Generate an auditable Amazon product-selection workbook from one SellerSprite-style historical file or the existing read-only 30-day New Releases database. Use for historical Excel selection or database trend selection; never browse Amazon, collect pages, write databases, make final development decisions, or create Listings.
---

# Amazon Product Selection

Analyze one existing data source and generate one reviewable product-selection `.xlsx`. The user only needs one of these requests:

- Attach or mention the main file, then say: `使用 $amazon-new-release-trends 执行【历史 Excel 选品模式】，生成可审核的选品 Excel。`
- Say: `使用 $amazon-new-release-trends 执行【数据库近30天选品模式】，生成可审核的选品 Excel。`

Infer the source path, marketplace, observation period, top-10 default, and output filename when they are available from the file, database, project configuration, or conversation. Ask only when multiple possible inputs make the choice genuinely ambiguous.

## Historical Excel mode

Use the attached or explicitly mentioned `.xlsx`, `.csv`, or `.tsv` as last year's same-period sales-spike source. This mode seeks short-term opportunities; a brief trend or seasonal item is acceptable. Do not score long-term durability or profit.

1. Run the deterministic analyzer before creating the workbook:

   `python -m amazon_product_os historical <input> --marketplace <code> --output <candidate-json>`

2. Keep the default eligibility gates unless the user gives other limits: selling price at most 30 in the source currency, package weight at most 1,000 g, package dimensions at most 45 × 35 × 25 cm, and complete size/weight data. The CLI exposes `--max-price`, weight and three dimension flags. Do not silently relax missing-size exclusion; `--allow-missing-size` requires user direction.
3. Use the Python score unchanged as the base ranking. It scores demand 30, momentum 30, growth breadth 15, low-review/recent-listing entry opportunity 20, and data confidence 5. Price and compact size are gates and tie-breakers, not profit proxies. Missing or zero reviews never count as low-review success.
4. Use the latest row for each ASIN, normalize percentages, derive growth from sequential months when needed, and require at least two eligible ASINs per product direction. A single breakout can be discussed as a lead but does not become a scored direction without a second eligible reference.
5. Return the top 10 concrete directions by default with two to five representative ASINs. Preserve the filter counts and score components. Explain evidence and risks, but never silently replace or recalculate the Python score.

Recognize SellerSprite fields such as `ASIN`, `商品标题`, `小类目`, monthly sales, month-over-month growth, reviews, price, listing days, converted package dimensions, and converted package weight. Older data is evidence for this year's timing, not proof of current demand.

## Database 30-day mode

Use the sibling collector database `../amazon-new-release-collector/data/trends.db` unless the user names another database. Open it read-only and analyze the latest snapshot plus the previous 29 calendar days. If it is missing or empty, stop and report that. Never copy it into this repository merely to analyze it.

- Use new-ASIN count, Top-30 presence, low-review count, rank improvement, product-type count changes, persistence, price band, source URL, and snapshot dates.
- Never infer sales, revenue, profit, or stock from rank. Fewer than two snapshot dates is a baseline, not a trend.
- The read-only command is:

  `python -m amazon_product_os --db <database> trend report --marketplace <code> --limit 10 --output <candidate-json>`

## Output

Create one `.xlsx` under `outputs/selection/` with four sheets: `选品结论`, `候选评分`, `ASIN证据`, and `规则与来源`. Keep scoring components, hard-filter thresholds and exclusion counts, source locations, assumptions, limitations, actual product directions, representative ASINs, evidence, risk, and next-review actions visible and auditable. State explicitly that profit was not scored. Use the standard spreadsheet authoring and visual verification workflow.

Finish with `等待选品负责人审核`. Do not invoke the product-development or Listing skill automatically.

## Boundaries

- Collection and database maintenance belong to the separate `../amazon-new-release-collector` project. Never launch its collector, Playwright, or any browser from this skill, and never add collection or database-write code back into `Amazon_ai`.
- Finish at candidate discovery. Do not research 1688, calculate final economics, decide GO/NO_GO, write Listing copy, or create images.
- Preserve the exact source file or database path, worksheet or stored URL, and observation period for audit.
