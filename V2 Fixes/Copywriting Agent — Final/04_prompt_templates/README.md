# 04_prompt_templates — Reusable Execution Patterns

## What This Contains
Standalone prompt templates that define the step-by-step procedure for each core workflow. These are designed to be loaded by an AI agent OR followed by a human copywriter.

Each template specifies:
- **When to use** — trigger conditions
- **Required inputs** — what must be gathered before starting
- **Context loading** — which documents to load and in what order
- **Execution steps** — the actual procedure
- **Scoring/verification** — how to validate the output

## Templates

### headline_generation.md
Full headline generation workflow (Steps 1-4.5). Context loading → archetype selection → formula application → scoring → Promise Contract extraction.

### advertorial_writing.md
Presell advertorial (editorial-style page). Builds beliefs B1-B4. 6-section structure, 800-1,200 words. Includes section-level CHECK gates.

### sales_page_writing.md
Sales page writing (post-presell). Builds beliefs B5-B8. Three architecture options (copy-first, data-first, merged). Research-backed calibration for warm traffic.

### promise_contract_extraction.md
Step 4.5 isolation — extracting the 4-field Promise Contract from a scored headline. The bridge between headline generation and body copy writing.

### awareness_angle_matrix.md
Generating per-angle, per-awareness-level framing matrices. Defines how each angle looks at each of the 5 awareness levels.

## Execution Order (Typical Funnel)

```
1. awareness_angle_matrix.md     → Define angle framing (once per angle)
2. headline_generation.md        → Generate + score headlines
3. promise_contract_extraction.md → Extract contract from winner (Step 4.5)
4. advertorial_writing.md        → Write presell (B1-B4)
5. sales_page_writing.md         → Write sales page (B5-B8)
```

## Customization
These templates are brand-agnostic. They reference parameterized documents in `01_governance/shared_context/`. Fill in `audience-product.md` with your brand's specifics before using any template.
