# Funnel Remediation Execution Plan (Refined per 2026-03-05 Feedback)

Date: 2026-03-05  
Owner: Codex implementation plan draft for approval

## 1) Locked Decisions (Applied from your feedback)

These are now treated as fixed requirements for implementation:

- Pre-sales CTA label standard: `Learn more` (replace transactional phrasing).
- Pre-sales section removal: remove the testimonial carousel section between listicle reasons and marquee (`PreSalesReviews`).
- Sales hero title rule: `product name only` for now.
- Remove selector micro-copy `Click to see why` for now.
- Sales urgency rows/count concept remains; issue to fix is **styling contrast + readability**, not the count model.
- Reviews payload is acceptable for this phase; remove from “misaligned” and no SP11-style change in phase 1.
- Footer scope: apply policy links + payment icons across **all funnel pages** (pre-sales + sales).
- Use Shopify policy pages as source-of-truth for footer policy links.
- Any testimonial presentation-priority changes move to Phase 2.

## 2) Baseline Reviewed

Live output reviewed from current funnel slug:
`ang-a02-herbdrug-interaction-non-answer-fix-l1-funnel-herb-drug-interaction-non-answer-fix-herb-drug-interaction-non-answer-fix-interaction-triage-workflow`

Data used:
- `mos/backend/artifact-downloads/strategy_v2_template_payload_success_2026-03-04_run_f9e71aad.md`
- `mos/backend/artifact-downloads/strategy_v2_end_to_end_completion_2026-03-04_run_f9e71aad.md`
- `/tmp/presales_latest.json`
- `/tmp/sales_latest.json`

Current page IDs:
- Pre-sales: `2d06f91e-c0be-4663-86ce-789fa8b1b510`
- Sales: `453a0371-68bf-4845-9d5f-75d969b72abd`

## 3) Updated Misalignment Summary

Still misaligned:
- Pre-sales top copy density is too high (hero/pitch/reasons/marquee verbosity).
- Pre-sales mobile stack order and top density still hurt fold quality.
- Pre-sales includes the testimonial carousel block (`PreSalesReviews`) that you now want removed.
- Sales urgency block visual treatment has weak contrast and drifts from strong core-template readability.
- Sales problem/mechanism/guarantee copy is too verbose.
- Sales footer and pre-sales footer do not yet include Shopify policy links + payment icon strip.

No longer considered misaligned for this phase:
- Reviews payload itself.

## 4) Asset-Type Legend

- `Template Asset (Reusable)`: template JSON, frontend template components, CSS tokens, shared types.
- `Generator / Agent System`: template bridge, prompt constraints, copy-contract validators.
- `Generated Instance`: one-off patch for current funnel instance.
- `Data Input / Platform Integration`: Shopify/compliance profile data and workflow context hydration.

## 5) Phase 1 (First Round of Edits)

Phase 1 includes page structure/copy/contrast/footer fixes and excludes testimonial/media-system expansion work.

## 5A) Pre-sales / Listicle (Phase 1)

| ID | Requirement | Asset scope | Where | Exact implementation |
|---|---|---|---|---|
| PS-01 | Pre-sales CTA wording standardized to `Learn more` | Generator + Template | `mos/backend/app/strategy_v2/template_bridge.py`, `mos/backend/app/templates/funnels/pre_sales_listicle.json` | Hard-map pre-sales CTA labels (`pitch.cta.label`, floating CTA if used for pre-sell intent) to `Learn more` unless explicitly overridden by future config flag. Remove `shop`/transactional CTA variants from pre-sales defaults. |
| PS-02 | Remove pre-sales testimonial section between reasons and marquee | Template + Generator | `mos/frontend/src/funnels/templates/preSalesListicle/PreSalesTemplate.tsx`, `mos/backend/app/templates/funnels/pre_sales_listicle.json`, `mos/backend/app/strategy_v2/template_bridge.py` | Remove `PreSalesReviews` from template composition order and template seed JSON for phase-1 funnel mode. Update template-bridge patch op generation so `reviews` payload is not required for pre-sales phase-1 output. |
| PS-03 | Mobile image-first hero order | Template | `mos/frontend/src/funnels/templates/preSalesListicle/components/Hero/Hero.module.css` | On mobile breakpoint, force media block first and text second; reduce hero media min-height to keep more content above fold. |
| PS-04 | Preserve 3-item top layout intent on mobile | Template | `mos/frontend/src/funnels/templates/preSalesListicle/components/BadgeRow/BadgeRow.module.css` | Replace vertical column collapse with either 3-up compact row or horizontal-scroll chips; keep all three visible as a single strip behavior. |
| PS-05 | Tighten top-section density | Generator + Template | `template_bridge.py` + pre-sales CSS tokens | Apply explicit cap profile (see Section 7) and reduce vertical paddings so shortened copy preserves intended rhythm. |
| PS-06 | More specific copy tightening (requested) | Generator | `mos/backend/app/strategy_v2/template_bridge.py` | Enforce exact Phase-1 caps (error on violation, no silent fallback): hero subtitle <= 140 chars and <= 2 sentences; pitch title <= 78 chars; pitch bullets exactly 4 bullets, each <= 90 chars; marquee items 1-3 words and <= 24 chars; reasons body <= 360 chars and <= 3 sentences. |
| PS-07 | PS08 detail expansion: logo + section consistency | Template + Generator | `pre_sales_listicle.json`, `preSalesListicle/types.ts`, `components/Footer/Footer.tsx`, `Footer.module.css`, `template_bridge.py` | Extend pre-sales footer schema to include: `links[]`, `paymentIcons[]`, `copyright`. Keep logo locked to single visual treatment (height token + max-width). Add deterministic ordering for footer links and enforce consistent spacing stack: previous section -> copyright -> links -> payment icons. |

## 5B) Sales / PDP (Phase 1)

(Per your instruction: remove prior SP04 stop-count proposal, remove SP11, remove SP12.)

| ID | Requirement | Asset scope | Where | Exact implementation |
|---|---|---|---|---|
| SP-01 | Product-name-only hero title | Generator + Template | `template_bridge.py`, `SalesPdpTemplate.tsx` | Map `purchase.title` from canonical product name field only for phase-1 mode (no tagline concat). Add validator to reject multiline sales headline-style title in PDP hero. |
| SP-02 | Remove selector micro-copy `Click to see why` | Generator + Template | `template_bridge.py`, `SalesPdpTemplate.tsx`, `sales_pdp.json` | Set `purchase.offer.seeWhyLabel` to empty/hidden and remove render branch when empty. |
| SP-03 | Keep urgency model, fix urgency visual contrast + readability | Template + Design-System lock | `mos/frontend/src/funnels/templates/salesPdp/salesPdpTemplate.module.css`, `pdpPage.module.css`, `SalesPdpTemplate.tsx` | Strengthen urgency token set and lock it from brand drift. Proposed token updates: higher-contrast bg/border/text for container, row-muted, row-highlight, icon contrast. Keep month rows + counts, but increase contrast ratio and visual hierarchy. |
| SP-04 | Reduce verbosity in problem/mechanism/guarantee | Generator | `template_bridge.py` | Enforce phase-1 caps (see Section 7): problem paragraphs max 2, each <= 320 chars; mechanism bullets exactly 5, title <= 56 chars, body <= 160 chars; guarantee paragraphs max 1 <= 260 chars; whyBody <= 220 chars; closingLine <= 140 chars. |
| SP-05 | Footer links + payment icons + copyright format | Template + Platform Integration + Generator | Frontend: `salesPdp/types.ts`, `SalesPdpTemplate.tsx`, `pdpPage.module.css`; Backend: `template_bridge.py`, `strategy_v2_activities.py` | Add footer model: `links[]`, `paymentIcons[]`, `copyright`. Render payment strip with your provided icon set (Amex, Apple Pay, Google Pay, Maestro, Mastercard, PayPal, Visa). Copyright format: `© {CURRENT_YEAR} {BRAND_NAME}`. |
| SP-06 | Policy links sourced from Shopify policies for all funnel pages | Platform Integration + Generator | Backend: `mos/backend/app/db/repositories/client_compliance_profiles.py`, `mos/backend/app/temporal/activities/strategy_v2_activities.py`, `template_bridge.py` | Resolve policy URLs from compliance profile fields (privacy, terms, returns/refunds, shipping, subscription if available), inject into footer links for pre-sales + sales page payloads. If required policy URLs are missing, return clean blocking error with missing keys list. |

## 5C) Cross-page / Shared System (Phase 1)

| ID | Requirement | Asset scope | Where | Exact implementation |
|---|---|---|---|---|
| XS-01 | Global copy caps integrated robustly (not brittle) | Generator | `template_bridge.py` + tests | Introduce versioned cap profile (`COPY_CAPS_PROFILE_V1`) keyed by stable semantic slots, not raw prose. Each slot has: `max_chars`, `max_sentences`, optional `exact_item_count`, optional `max_words_per_item`. Validation is deterministic and fail-fast with field-path error reporting. |
| XS-02 | Keep template geometry while allowing brand skinning | Template | `PreSalesTemplate.tsx`, `SalesPdpTemplate.tsx` | Expand locked CSS var allowlist to include urgency/readability-critical vars so design system cannot degrade contrast in high-risk modules. |
| XS-03 | Standardize section spacing + line-height across both pages | Template | pre-sales and sales CSS token files | Normalize top-level section spacing tokens and heading line-height tokens to a shared baseline profile for both templates. |
| XS-04 | Footer implementation shared for all funnel pages | Template + Generator | both template type files/components + bridge mappings | Introduce common footer data contract and apply to both page templates; eliminate per-page drift. |

## 5D) Prompt / Agent System (Phase 1)

(Per your instruction: AG2 moved to Phase 2, AG04 removed.)

| ID | Requirement | Asset scope | Where | Exact implementation |
|---|---|---|---|---|
| AG-01 | Section-specific copy discipline in generation | Generator | prompt templates + `template_bridge.py` validators | Prompt instructions will mirror cap profile, but source-of-truth remains validator. Prompt asks for compact output by slot; validator enforces hard limits. |
| AG-03 | VOC mapping into compact FAQ/selector blurbs | Generator | VOC mapping stage + bridge | Keep mapping deterministic and short-form for phase-1 slots only (FAQ/selector blurbs), without testimonial-priority changes. |

## 6) Phase 2 (Deferred by design)

Phase 2 intentionally excludes first-round launch criteria.

## 6A) 4C Media/Testimonial/Image System Work (Moved to Phase 2)

- Carousel/media mix tuning (UGC vs benefit-card ratios).
- Prompt relevance hardening for image generation edge cases.
- Additional testimonial presentation work (if needed later).

## 6B) AG2 and AG5 (Moved to Phase 2)

| ID | Requirement | Asset scope | Where | Exact implementation |
|---|---|---|---|---|
| AG-02 | Offer-agent onboarding for complete pricing/variant/savings data | Data/Input + Generator | strategy launch activities/workflows | Add explicit completeness checkpoint before generation and HITL resolution for missing pricing/variant metadata. |
| AG-05 | Brand prompt/design variability hardening with section-level locks | Generator + Template | design token bridge + template-level lock lists | Define section-critical style locks (urgency, comparison, FAQ, selector cards) while allowing non-critical aesthetic variation. Add invariant checks preventing low-contrast combinations in these locked modules. |

## 7) Copy Cap Profile (Detailed, Requested)

These are the concrete Phase-1 limits to be enforced by validator.

## 7A) Pre-sales cap profile

- `PreSalesHero.hero.title`: <= 90 chars
- `PreSalesHero.hero.subtitle`: <= 140 chars, <= 2 sentences
- `PreSalesHero.badges[].value`: <= 24 chars
- `PreSalesMarquee.config[]`: 1-3 words, <= 24 chars each
- `PreSalesReasons[].title`: <= 72 chars
- `PreSalesReasons[].body`: <= 360 chars, <= 3 sentences
- `PreSalesPitch.title`: <= 78 chars
- `PreSalesPitch.bullets`: exactly 4 items, each <= 90 chars
- `PreSalesFloatingCta.label`: exactly `Learn more`

## 7B) Sales cap profile

- `SalesPdpHero.purchase.title`: <= 64 chars, product-name-only pattern
- `SalesPdpHero.purchase.offer.helperText`: <= 180 chars, <= 2 sentences
- `SalesPdpMarquee.items[]`: 1-3 words, <= 24 chars each
- `SalesPdpStoryProblem.paragraphs`: max 2 items, each <= 320 chars
- `SalesPdpStorySolution.bullets`: exactly 5 items
- `SalesPdpStorySolution.bullets[].title`: <= 56 chars
- `SalesPdpStorySolution.bullets[].body`: <= 160 chars
- `SalesPdpGuarantee.paragraphs`: max 1 item, <= 260 chars
- `SalesPdpGuarantee.whyBody`: <= 220 chars
- `SalesPdpGuarantee.closingLine`: <= 140 chars
- `SalesPdpFaq.items[].answer`: <= 280 chars, <= 3 sentences

## 7C) Integration mechanics (robustness)

- Implement as versioned validator profile in `template_bridge.py` (single source of truth).
- Validation occurs before patch operation generation.
- On violation, return deterministic `TEMPLATE_PAYLOAD_VALIDATION` errors with exact field path and observed vs allowed count.
- No hidden truncation fallback in phase-1 path.
- Add unit coverage for boundary, over-limit, and exact-count behavior to prevent brittle regressions.

## 8) Footer + Payment Icons Detailed Plan

## 8A) Footer data contract (all funnel pages)

Add to both template footer configs:

- `logo`
- `copyright`
- `links[]`: ordered policy links
  - `privacy`
  - `terms`
  - `returns/refunds`
  - `shipping`
  - `subscription` (only if URL exists)
- `paymentIcons[]`: key list, default order:
  - `american_express`
  - `apple_pay`
  - `google_pay`
  - `maestro`
  - `mastercard`
  - `paypal`
  - `visa`

## 8B) Payment icon rendering

- Add reusable icon strip component that renders the exact icon set you provided (sanitized inline SVG constants).
- Use semantic list wrapper and per-icon `aria-labelledby`/`title` for accessibility.
- Keep fixed icon viewport (`38x24`) and controlled spacing so layout is stable on mobile.

## 8C) Copyright format

- Enforce: `© {CURRENT_YEAR} {BRAND_NAME}`
- Example: `© 2025 PuppyPad`

## 8D) Shopify policy link source

- Source URLs from compliance profile fields synced to Shopify policy pages:
  - `privacy_policy_url`
  - `terms_of_service_url`
  - `returns_refunds_policy_url`
  - `shipping_policy_url`
  - `subscription_terms_and_cancellation_url` (optional)
- Inject into both pre-sales and sales footer payloads.
- Missing required policies => explicit blocking error listing missing policy keys.

## 9) Removed / Updated Prior Plan Items

Removed per your instruction:
- Prior SP04 “remove fabricated urgency model” item (replaced with urgency styling/contrast fix).
- SP11 testimonial compliance redesign for phase 1.
- SP12 no-op item.
- AG04.

Updated:
- 4C moved to Phase 2.
- AG2 moved to Phase 2.
- AG05 moved to Phase 2 with deeper section-lock detail.

## 10) Phase Execution Order (Updated)

Phase 1 (execute now)
1. Apply locked decisions (Learn more, product-name-only, remove pre-sales testimonial block, remove click-to-see-why).
2. Implement cap profile validators + prompt alignment.
3. Urgency styling contrast hardening and template token lock updates.
4. Footer system rollout across all funnel pages with Shopify policy links + payment icon strip + copyright format.

Phase 2 (deferred)
1. 4C media/testimonial/image-system optimization.
2. AG2 offer-data onboarding completeness flow.
3. AG05 brand variability hardening for critical module readability.

## 11) Acceptance Criteria for Phase 1

- Pre-sales no longer renders `PreSalesReviews` between reasons and marquee.
- Pre-sales CTA text is `Learn more`.
- Sales hero title is product-name-only.
- Selector “Click to see why” is absent.
- Urgency block visually passes stronger-contrast styling and remains structurally intact.
- Copy cap profile validation is active and rejects over-limit payloads with explicit field-path errors.
- Both pre-sales and sales footer show:
  - Shopify policy links (required pages)
  - payment icon strip (provided set)
  - `© {CURRENT_YEAR} {BRAND_NAME}` format.

