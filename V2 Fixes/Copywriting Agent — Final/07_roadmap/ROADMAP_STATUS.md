# System Roadmap — Build Status

## FULLY BUILT & TESTED

| System | Status | Location |
|--------|--------|----------|
| Headline Engine | LIVE | 02_engines/headline_engine/ |
| Headline Scorer v2 | LIVE | 03_scorers/headline_scorer_v2.py |
| Promise Contract System | LIVE | 02_engines/promise_contract/ |
| Congruency Scorer | LIVE | 03_scorers/headline_body_congruency.py |
| QA Auto-Fix Loop | LIVE | 03_scorers/headline_qa_loop.py |
| Headline I/O Schemas | LIVE | 05_schemas/headline_input.json, headline_output.json |
| Foundational Docs (S2-S11, SA-SE) | LIVE | 01_governance/sections/ |
| Shared Context Layer | LIVE | 01_governance/shared_context/ |
| Prompt Templates | LIVE | 04_prompt_templates/ |

## SCHEMAS DEFINED (Templates Ready, Agent Implementation Pending)

| System | Status | Location |
|--------|--------|----------|
| Presale Listicle Template | SCHEMA DEFINED | 05_schemas/presales_listicle.schema.json |
| Sales PDP Template | SCHEMA DEFINED | 05_schemas/sales_pdp.schema.json |
| Page Constraints & Purposes | DOCUMENTED | 02_engines/page_templates/ |
| Listicle Scorer | BUILT (needs integration) | 03_scorers/page_scorers/score_listicle.py |
| Upgrade Scorer | BUILT (needs integration) | 03_scorers/page_scorers/upgrade_test_scorer.py |
| Layer 2 Scorer | BUILT (needs integration) | 03_scorers/page_scorers/layer2_scorer.py |

## SPECIFICATIONS WRITTEN (Not Yet Implemented)

| System | Status | Location |
|--------|--------|----------|
| VOCC Taxonomy Agent | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 1 |
| VOCC Emotional Charge Scoring | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 2 |
| VOCC Content Discovery | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 3 |
| VOCC Quality Pipeline | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 4 |
| VOCC Language Pattern Extraction | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 5 |
| VOCC Performance Feedback Loop | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 6 |
| VOCC Platform Normalization | SPEC ONLY | 07_roadmap/VOCC_enhancement/Workflow 7 |
| Auto-Generate Craft Rules | SPEC ONLY | 07_roadmap/auto_craft_rules/ |

## CONCEPTUAL (Not Yet Specified)

| System | Notes |
|--------|-------|
| Awareness-Angle Matrix Generator | Referenced in shared_context but not yet built as workflow. Prompt template exists in 04_prompt_templates/. |
| Email Sequence Workflow | Page-type template defined in S2 but no dedicated workflow spec. |
| Thank You / Upsell / Downsell Workflows | Page-type templates defined in S2 but no dedicated workflow specs. |
| Multi-variant A/B Test Runner | Framework defined in S8 but no automated runner. |

## Implementation Priority (Recommended)
1. Presale Listicle Workflow Agent — Schema + scorer already exist. Highest ROI.
2. Sales Page Workflow Agent — Schema + scorer + 3 worked examples exist.
3. VOCC Enhancement Pipeline — 7 detailed specs ready for implementation.
4. Awareness-Angle Matrix Generator — Prompt template ready, needs workflow wrapper.
5. Email Sequence Workflow — Extend S2 email template into full workflow.
