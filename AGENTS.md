# Amazon Product OS

This repository exposes three independent business skills. Route only the user's current task; never invoke the next skill automatically. A human may pass an artifact to another role after review, but that handoff is optional.

## Route requests

- Scheduled Amazon New Releases collection, browser navigation, snapshot ingestion, or database maintenance belongs only to the sibling `../amazon-new-release-collector` project, never to this repository or a skill. Do not recreate collection or database-write code here.
- SellerSprite-style historical `.xlsx`, `.csv`, or `.tsv`, or product selection from the sibling collector's 30-day database: use `$amazon-new-release-trends`. It is analysis-only, opens the database read-only, and must produce a reviewable selection workbook with concrete product directions and reference ASINs.
- Product idea, ASIN, candidate evaluation, competitor analysis, product design, 1688 search, profit, compliance, or GO/WATCH/NO_GO: use `$amazon-product-decision`. It may start independently without a prior trend run.
- Product copy, Product Master, localization, image brief, upload workbook, or pre-launch review: use `$amazon-listing-launch`. It may start from an operations-approved Product Master without a Product Decision Card.

## Human ownership

- Research/selection owner reviews discovery results and chooses whether any candidate should be investigated.
- Product development owner reviews the development recommendation and owns the product specification, sourcing assumptions, profit, and compliance decision.
- Operations owner reviews Product Master, Listing content, images, compliance evidence, and upload data. Package generation never means approval to publish.

`schemas/candidate.schema.json`, a Product Decision Card, and `schemas/product_master.schema.json` are reusable evidence formats, not a mandatory state machine. Every skill stops after its own deliverable and reports who must review it.

Do not treat example files as live research. Do not bypass Amazon access controls, purchase from suppliers, or publish to Amazon without explicit user authorization.
