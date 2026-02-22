# Upgraded Prompts — Canonical Source

This folder contains the v2 prompt templates for the foundational research pipeline.

---

## Folder Structure

```
Upgraded Prompts/
  clean_prompts/          ← Canonical research pipeline prompts (copy/paste ready)
    01_competitor_research_v2.md
    03_deep_research_meta_prompt_v2.md
    04_deep_research_execution_v2.md
    06_avatar_brief_v2.md

  downstream/             ← Strategy prompts (NOT part of the research pipeline)
    07_offer_brief_v2.md
    08_belief_architecture_v2.md

  pipeline/               ← Pipeline documentation
    00_pipeline_overview.md

  reference/              ← Supporting materials (not canonical)
    annotated_prompts/    ← Original v2 drafts with design commentary
    docs/                 ← Testing reports, comparisons
    test_outputs/         ← Captured test run outputs

  Word Documents/         ← Auto-generated .docx versions of all prompts
  generate_docx.py        ← Script to regenerate Word documents
```

---

## Pipeline Flow

```
[Seed Input] → [01 Competitor Research] → [03 Meta-Prompt] → [04 Deep Research] → [06 Avatar Brief]
  5 fields              ↓                        ↓                    ↓                    ↓
                   STEP1_SUMMARY            STEP4_PROMPT        STEP4_SUMMARY         STEP6_SUMMARY
                   STEP1_CONTENT                                STEP4_CONTENT         STEP6_CONTENT
```

**Seed input:** Product name, description, price, competitor URLs, product_customizable flag

**Output:** Competitor landscape, VOC corpus with structured quote banks, 3-5 buyer segments with psychological profiles, primary segment identification, market bottleneck

See `pipeline/00_pipeline_overview.md` for the complete workflow reference with Honest Herbalist worked examples.

---

## What Each File Does

| File | Role | Agent Type | Key Output |
|---|---|---|---|
| `01_competitor_research_v2.md` | Discover, validate, and score competitors. Map positioning gaps. | Research agent (web access) | Traction-scored competitor table, positioning gap matrix, market maturity |
| `03_deep_research_meta_prompt_v2.md` | Write a niche-tailored deep research prompt | Prompt engineer agent (no web) | A complete research prompt customized for this specific product/niche |
| `04_deep_research_execution_v2.md` | Reference template for what the meta-prompt generates | Research agent (web access) | 9-category VOC corpus with tagged quote banks, signal assessment, bottleneck |
| `06_avatar_brief_v2.md` | Synthesize VOC data into distinct buyer segments | Strategist agent (no web) | 3-5 segment profiles, cross-segment matrix, primary segment, safety audit |

**Downstream (not in research pipeline):**

| File | Role |
|---|---|
| `07_offer_brief_v2.md` | Strategic offer positioning (depends on angle selection) |
| `08_belief_architecture_v2.md` | Belief mapping for conversion copy (depends on offer architecture) |

---

## The Two-Step Deep Research Pattern

Steps 03 and 04 form a two-step system:

1. **03 (Meta-Prompt)** receives business context + competitor research and WRITES a tailored research prompt. It does not do research itself. It customizes search terms, community priorities, category emphasis, and source suggestions for the specific niche.

2. **04 (Execution)** is the reference template showing the structure that the meta-prompt must generate against. The actual prompt executed by the Research Agent is the output of Step 03 — emitted in `<STEP4_PROMPT>` tags.

This separation ensures research prompts are always niche-specific rather than generic.

---

## v2 Thesis (What Changed from v1)

All v2 prompts share these structural upgrades:

- **Dual output format:** Every prompt produces `<SUMMARY>` (bounded, ~500 words) + `<CONTENT>` (full output). Summaries feed downstream; full content available for deep reference.
- **Tool-called scoring:** All quantitative evaluation uses code interpreter, not mental estimation. Prevents LLM biases (central tendency, anchoring, recency).
- **Signal-to-Noise assessment:** Every finding graded HIGH (5+ sources) / MODERATE (2-4) / LOW (1 source).
- **Bayesian confidence ratings:** Per-category confidence with evidence cited.
- **Structured quote banks:** Every VOC quote tagged with 6 metadata fields (SOURCE, CATEGORY, EMOTION, INTENSITY, BUYER_STAGE, SEGMENT_HINT).
- **Multi-segment architecture:** 3-5 distinct buyer segments with differentiation test, not monolithic avatars.
- **Research/strategy separation:** This pipeline produces intelligence only. No positioning, angles, funnels, or copy decisions.
- **Bottleneck identification:** Every research step identifies the #1 unmet need in the market.
- **Safety factor audits:** Explicit checks for weak evidence, faulty assumptions, and contradictory data.

---

## How to Use

1. Fill in the 5 seed fields (product name, description, price, competitor URLs, product_customizable)
2. Run `01_competitor_research_v2.md` — produces `{{STEP1_SUMMARY}}` and `{{STEP1_CONTENT}}`
3. Run `03_deep_research_meta_prompt_v2.md` — produces `{{STEP4_PROMPT}}`
4. Run the generated `{{STEP4_PROMPT}}` with a web-access agent — produces `{{STEP4_SUMMARY}}` and `{{STEP4_CONTENT}}`
5. Run `06_avatar_brief_v2.md` — produces `{{STEP6_SUMMARY}}` and `{{STEP6_CONTENT}}`
6. Review research output. Choose your angle. Proceed to downstream pipelines.

---

## Regenerating Word Documents

```bash
python3 generate_docx.py
```

Requires `python-docx`: `pip install python-docx`

---

## Archive

The `precanon_research/` folder (sibling to this one) contains the original v1 prompt templates. It is preserved as a reference archive and is not part of the active pipeline.
