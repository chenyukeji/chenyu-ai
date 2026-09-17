---
name: amazon-product-decision
description: 独立评估亚马逊产品创意、ASIN 或候选方向，覆盖需求、竞争、产品设计、1688 供应链、利润与合规，并输出继续开发、持续观察或停止开发的建议及具体开发规格；不用于趋势监控或商品详情页撰写。
---

# Amazon Product Development & Decision

Produce one auditable Product Decision Card for a product development owner. The calculated GO/WATCH/NO_GO result is a recommendation pending that person's review, not an automatic trigger for Listing work.

## Starting input

Accept any one of the following: a product idea, an Amazon ASIN/listing, a SellerSprite row or shortlist, or a `Candidate` matching `schemas/candidate.schema.json`. If no Candidate file exists, create a minimal `source: Manual` candidate record inside the case so the evidence remains auditable. Do not require the trends skill to have run first.

## Analysis lanes

1. Validate market demand, relevant Top ASINs, review barrier, price band, new-product success, brand concentration, and marketplace-specific supply. Record dated source URLs for externally researched claims.
2. Compare competitor quantity, color, size, material, structure, packaging, functions, images, common review complaints, and unsupported or saturated claims.
3. Define a concrete development plan: exact sellable quantity, materials, dimensions/weight target, packaging, core functions, and one defensible differentiation. Do not leave contradictions for the Listing stage.
4. Generate specific Chinese 1688 search terms. Compare candidate suppliers and quotes when data is available, but never place an order or contact a supplier without the user's explicit authorization. Mark unverified quotes as unverified.
5. Put unit-economics assumptions in JSON and run `python -m amazon_product_os profit <input.json>`. Use current VAT, Amazon fee, FBA, exchange-rate, freight, advertising, and return assumptions; never invent an unknown fee silently.
6. Classify the product profile and run `python -m amazon_product_os compliance <profile.json> --marketplace <code>`. Treat the result as a screening gate, not legal advice. Confirm current regulated-product requirements before inventory commitment.
7. Populate a development case shaped like `schemas/development_case.schema.json`, then run `python -m amazon_product_os decision <case.json> --output <decision.json>`.

## Decision rules

- `GO`: score at least 75 with no hard gate.
- `WATCH`: score 55-74 with no hard gate; state exactly which evidence could change the decision.
- `NO_GO`: score below 55 or any hard gate, including unresolved high compliance risk, weak conservative margin, or no defined differentiation.
- Do not massage scores to reach a preferred outcome. Separate observed facts, assumptions, and recommendations.

Finish with the Product Decision Card and `等待开发负责人审核`. State which inputs are observed facts and which still need confirmation. Do not invoke the Listing skill, contact suppliers, or treat a calculated `GO` as human approval.
