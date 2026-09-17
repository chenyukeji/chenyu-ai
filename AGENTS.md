# Amazon Creative OS

This repository currently focuses on Amazon creative workflows.

## Route requests

- Amazon image generation and full image-set production belong to `plugins/chenyu-amazon-creative/skills/chenyu-zuotu`.
- Precise local image retouching belongs to `plugins/chenyu-amazon-creative/skills/chenyu-jingxiu`.
- Product positioning, competitive analysis, and image strategy are upstream inputs and are not handled by the creative plugin.
- Product selection, product-development decisions, sourcing, profitability, compliance decisions, and Listing launch are later-stage work and are not currently exposed as skills.
- Scheduled Amazon New Releases collection, browser navigation, snapshot ingestion, or database maintenance belongs only to the sibling `../amazon-new-release-collector` project.

## Boundaries

Do not treat example files as live research. Do not bypass Amazon access controls, purchase from suppliers, or publish to Amazon without explicit user authorization.
