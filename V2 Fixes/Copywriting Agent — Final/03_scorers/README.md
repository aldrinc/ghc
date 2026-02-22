# 03_scorers — Evaluation Tools

## What This Contains
All Python-based deterministic and LLM-powered scoring tools.

## Core Scorers (Headline Level)

### headline_scorer_v2.py
**Primary deterministic headline scorer.** Zero LLM dependency.
- 29 tests across 4 dimensions (44 points total)
- Dimensions: Intrigue & Attention (IA), Promise & Trust (PT), Craft & Structure (CS), Brand Compliance (BC)
- Hard gates: BC1 (banned words), BC2 (disease claims), BC3 (prohibited phrases)
- Tier system: S (38+) / A (33-37) / B (28-32) / C (22-27) / D (15-21) / DISQUALIFIED (<15 or hard gate fail)
- **Usage:** `python3 headline_scorer_v2.py "Your headline here"`

### headline_body_congruency.py
**Promise Contract enforcement scorer.** Validates headline-body alignment.
- 13 tests, 19 points
- PC1-PC4: Promise Contract tests (7 pts) — PC2 is a HARD GATE (3 pts)
- HP1-HP5: Headline→Body promise payment (7 pts)
- BH1-BH4: Body→Headline setup verification (5 pts)
- **Usage:** `python3 headline_body_congruency.py <body_file.md> [promise_contract.json]`
- Pass threshold: 75% (14.25/19)

### headline_qa_loop.py
**LLM-powered auto-fix pipeline.** Takes failing headlines and attempts repair.
- Max 3 iterations per headline
- Re-scores after each fix attempt
- Hard gates must pass on final iteration
- **Usage:** Called programmatically, not standalone

## Page-Level Scorers (page_scorers/)

### score_listicle.py
Presale listicle page scorer. Tests section structure, proof stacking, mobile rendering.

### upgrade_test_scorer.py
Post-purchase upsell/upgrade page scorer. Tests re-engagement hooks, price anchoring.

### layer2_scorer.py
Full-system integration scorer. Tests presale→sales promise delivery, message match, multi-section coherence.

## Dependencies
- Python 3.10+
- No external packages required (all scorers use stdlib only)
- headline_qa_loop.py requires an LLM API connection

## Scoring Philosophy
All scorers are **deterministic first** — no LLM judgment in the scoring itself. The LLM is only used in the QA loop for rewriting, never for scoring. This ensures reproducible, auditable results.
