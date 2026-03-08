# Prompt Template: Sales Page Writing

## When to Use
When writing a sales page (the page that receives traffic from a presell advertorial and converts to purchase). Builds beliefs B5-B8.

## Strategy V2 Runtime Contract Override (Mandatory)
When this prompt is executed by `strategy_v2.run_copy_pipeline`, follow this output contract and ignore any alternate architecture format:

- Return exactly one JSON object with keys `markdown` and `template_payload_json`.
- `template_payload_json` must be a JSON-serialized object string (no markdown code fences).
- `template_payload_json` top-level keys must be exactly: `hero`, `problem`, `mechanism`, `social_proof`, `whats_inside`, `bonus`, `guarantee`, `faq`, `faq_pills`, `marquee_items`, `urgency_message`, `cta_close`.
- Do not emit alternative schema keys such as: `schema`, `template_id`, `product_name`, `product_subtitle`, `problem_recap`, `cta_primary`, `pricing`, `legal_disclaimer`.

## Required Inputs

| Input | Source | Required? |
|-------|--------|-----------|
| Winning headline | Headline engine output (scored B+ tier) | YES |
| Promise Contract JSON | Step 4.5 extraction | YES |
| Awareness level | Solution-Aware (arriving from presell) | YES |
| Page type | "Sales Page" | YES |
| Angle | Same angle as presell advertorial | YES |
| Target beliefs | B5-B8 (sales page belief chain) | YES |
| Product details | Price, format, bonuses, guarantee | YES |
| Traffic temperature | Warm (from presell) | YES |

## Context Loading

```
1. 01_governance/shared_context/audience-product.md
2. 01_governance/shared_context/brand-voice.md
3. 01_governance/shared_context/compliance.md
4. 01_governance/sections/Section 2 - Page-Type Templates.md
   → Sales page template (12-section structure)
5. 01_governance/sections/Section 9 - Section-Level Job Definitions.md
6. 01_governance/sections/Subsection A - Structural Principles.md
   → B5-B8 belief chain for sales pages
7. 01_governance/sections/Subsection B - Sentence-Level Craft Rules.md
8. 02_engines/promise_contract/PROMISE_CONTRACT_SYSTEM.md
9. 02_engines/page_templates/   → Page constraints and purpose docs
10. Promise Contract JSON for the winning headline
```

## Architecture Options

Three proven architectures exist. Choose based on your output needs:

### Option A: Section 2 Copy-First (Recommended for copy review)
12-section belief-chain structure. Pure copy, no UI components.
Best for: Editing, approval workflows, copy audits.

### Option B: PDP Schema Data-First (Recommended for frontend)
JSON structure conforming to `05_schemas/sales_pdp.schema.json`.
Best for: Direct frontend rendering (JSON → React components).

### Option C: Merged Optimal (Recommended for production)
16-module architecture combining Section 2 belief chain + PDP UI components.
Best for: Maximum conversion — belief sequencing + UI richness.

See `06_examples/honest_herbalist/sales_pages/Sales_Page_Comparison.docx` for a detailed comparison.

## Sales Page Blueprint (Section 2 Structure)

| Section | Belief Job | Word Target | CTA? |
|---------|------------|-------------|------|
| 1. Hero Stack | B5 seed | 40-60w | Yes (first CTA) |
| 2. Problem Recap | B1-B4 recap | 80-150w | No |
| 3. Mechanism + Comparison | B5 (UMS) | 250-400w | No |
| 4. Identity Bridge | B6 | 100-150w | No |
| 5. Social Proof | B5-B6 reinforcement | 200-350w | No |
| 6. CTA #1 | B7+B8 | 40-60w | YES (~38% of page) |
| 7. What's Inside | B5 reinforcement | 200-300w | No |
| 8. Bonus Stack + Value | B7 | 150-200w | No |
| 9. Guarantee | B8 | 80-120w | No |
| 10. CTA #2 | B7+B8 | 40-60w | YES |
| 11. FAQ | B5-B8 | 150-250w | No |
| 12. CTA #3 + P.S. | B8 | 60-100w | YES |

## Key Calibration (Warm Presell Traffic)

Research-backed adjustments for traffic arriving from a presell advertorial:

- **Word count:** 1,800-2,800 words (warm traffic needs ~40% less than cold)
- **Reading grade:** 5th-7th grade (converts 56% higher than professional-level)
- **First CTA:** By 40% of page length
- **Max CTAs:** 3 primary
- **Problem Recap:** Compressed (80-150w vs 150-200w for cold) — presell already built B1-B4
- **Mechanism:** Compressed (250-400w vs 400-600w for cold) — presell already introduced the category

## Promise Contract Integration
- The headline's Promise Contract governs the ENTIRE page structure
- `delivery_test` must be satisfied — typically by Section 3 (Mechanism)
- `minimum_delivery` specifies where delivery begins and resolves
- The P.S. (Section 12) should echo the promise as a final recency-effect close

## Scoring

```bash
python3 03_scorers/headline_body_congruency.py sales_page.md promise_contract.json
```

**Target:** 75%+ (14.25/19). PC2 hard gate must PASS.

## Output Formats
- **Markdown (.md)** — for copy review and scorer input
- **Word doc (.docx)** — for Google Drive review (use python-docx)
- **JSON (.json)** — if using PDP schema architecture (Option B)

## Purchase-Module Bullet Style
For the 4 checkmark bullets under the purchase title:

- Write exactly 4 bullets.
- Make each bullet outcome-based, one-bite, and action-focused.
- Keep each bullet to 2-6 words.
- Emphasize the result, ease, or friction removed, not the internal asset name.
- Do not end bullets on feature labels such as workflow, guide, reference, checklist, worksheet, pages, notes, prompts, or scripts.
- Do not use parentheses, arrows, colons, or explanatory clauses.
- Preferred style: `Ask Better Questions`, `Spot Red Flags Fast`, `Check Interactions First`, `Feel Safer Starting`.
