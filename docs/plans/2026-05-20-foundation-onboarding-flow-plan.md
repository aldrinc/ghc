# Marketing Agent Onboarding Flow Plan

Date: 2026-05-20
Status: plan only
Reference: FernDesk-inspired first-run flow, existing MOS onboarding runtime, and Context.dev docs captured in `proof_pack/foundation-onboarding-flow-2026-05-20/sources/context-dev-docs/source_manifest.json`

## Decision

Replace current onboarding with a marketing-agent first-run flow.

The new flow should feel like FernDesk: one question per screen, quiet split layout, thin progress rail, black primary CTA, and visible setup theatre after submit. The backend contract must also change. The UI should not collect offer, proof, voice, channel, claims, or copy inputs during onboarding.

Customer-facing promise:

- set up your marketing agent
- teach it what business it is working on
- point it at the first product or service
- for existing businesses, use Context.dev to learn from the website instead of asking every setup question
- let it prepare the workspace in the background

Internal output remains foundation docs only:

- competitor landscape
- deep research meta prompt
- deep buyer/VOC research
- avatar and segment brief
- aggregate foundation bundle for later workflows

No offer architecture, page copy, ad copy, design system, logo, proof strategy, or launch assets are generated in this onboarding loop.

## Goal

Create a customer-friendly onboarding path that lets a new or existing business create a workspace, set up a marketing agent, define the first product or service it should work on, and prepare the internal foundation docs with minimal friction.

Key results:

- Customer can complete onboarding in 7-9 focused screens.
- Existing-business path can complete from workspace name, website URL, and optional competitors.
- New-business path asks only the product/service details the agent cannot infer.
- Price is optional and can be set later.
- Competitor/source URLs are optional seeds, not blockers.
- Existing business onboarding is supported.
- Background foundation preparation runs without extra human gates.
- Onboarding never runs or requires copy generation artifacts.

## Problem

The current onboarding machine is full Strategy V2 wearing an onboarding UI.

Observable issues:

- `POST /clients/{id}/onboarding` rejects `business_type="existing"`.
- `OnboardingStartRequest` requires offer/copy-adjacent inputs like proof assets, brand voice notes, target platforms, and target regions.
- `ClientOnboardingWorkflow` immediately starts `StrategyV2Workflow`, which proceeds into offer selection and copy generation stages.
- Price is required because the route assumes a product variant with non-null `amount_cents`, which does not fit services or unknown pricing.
- The UI exposes too many operational fields before the customer has seen any value.
- New and existing businesses are treated too similarly. Existing businesses should be source-first; new businesses need guided product/service input.

## Diagnosis

Root cause: backend execution requirements leaked into first-run UX.

The system never created a separate "marketing agent setup" contract. Because onboarding starts full Strategy V2, the UI is forced to ask for fields needed later by offer and copy workflows. That makes onboarding heavy and causes false sequencing: the user must answer later-stage strategy questions before the agent has enough background context.

## Current Machine

1. UI asks workspace, business/source, product-only details, platforms, regions, proof, voice, constraints.
2. Frontend creates client with Strategy V2 enabled.
3. Backend creates product, default offer, default variant.
4. Backend requires concrete price to create variant.
5. Backend rejects existing-business onboarding.
6. Client onboarding workflow starts full Strategy V2.
7. Strategy V2 runs foundation research, then offer pipeline, then copy pipeline.
8. Downstream checks expect Strategy V2 offer/copy artifacts.

## Designed Machine

1. UI asks workspace name and whether this is new or existing.
2. Existing-business branch asks for business website URL and optional competitors, then Context.dev extracts the business model and likely offering context with source evidence.
3. New-business branch asks guided product/service questions because no website source exists yet.
4. Frontend submits a marketing-agent setup payload with `input_mode="source_extract"` or `input_mode="manual_seed"`.
5. Backend creates/updates workspace and offering shell only from explicit customer input or source-grounded extraction.
6. If price/rate is known and relevant, backend creates pricing/variant data. If pricing is unknown or service-specific, pricing waits.
7. Backend supports `new` and `existing` business stages.
8. Background workflow prepares all foundation docs automatically.
9. Backend persists a foundation bundle and step payload artifacts.
10. Workspace moves to "Marketing agent ready".
11. Later workflows collect offer, proof, voice, channels, claims constraints, design system, and copy inputs only when needed.

## Question-By-Question Flow

### Shared Entry

| Step | Customer question | UI pattern | Required | Stored field(s) | Downstream mapping |
|---|---|---|---:|---|---|
| 1 | What should we call this workspace? | Single text input | Yes | `client.name`, `workspace_name` | Workspace identity, workflow labels, artifact titles |
| 2 | Is this a new business or an existing business? | Two choice rows | Yes | `business_type` = `new` or `existing` | Branches helper copy and source prompts; backend must support both |

### Existing Business Branch

| Step | Customer question | UI pattern | Required | Stored field(s) | Downstream mapping |
|---|---|---|---:|---|---|
| 3E | What is the business website? | URL input | Yes | `business_url`, `source_urls[]`, `input_mode="source_extract"` | Agent extraction source, source manifest seed, workspace context |
| 4E | Any competitors your agent should know about? | Optional URL list | No | `competitor_urls[]` | Narrows extraction and later agent setup; never a blocker |
| 5E | Does this look right to you? | Editable extracted summary | Yes | confirmed or edited `business_model`, `offering_kind`, `offering_name`, `offering_description`, `offering_type`, `offering_category`, `pricing_status`, evidence refs | Customer confirms or fixes Context.dev extraction before workspace creation |
| 6E | Create workspace | CTA | Yes | confirmed payload | Creates workspace and starts background setup workflow |

Existing-business extraction rules:

- Context.dev is the scraper/enrichment layer for existing businesses.
- The backend calls Context.dev from a server-side proxy only. The Context.dev API key must live in backend env as `CONTEXT_DEV_API_KEY`; it must never be sent to the browser, written into plan files, or stored in client-visible payloads.
- The agent may infer business model, offering kind, offering name, offering description, category, and pricing only from Context.dev outputs and provided website/source URLs.
- Every extracted field must carry `provenance.provider="context_dev"`, `provenance.endpoint`, `provenance.source_url`, `provenance.evidence_excerpt`, and `provenance.confidence`.
- If the website does not clearly state a field, store it as `unknown` or `needs_review`; do not guess.
- The 5E review screen should show the extracted information as editable fields, not static text.
- Editable 5E fields: business name, business model, product/service/software/course/offer type, primary offering name, primary offering description, category, pricing model, price/rate if found, and competitor URLs.
- Unknown fields should appear as empty or "not found" fields the customer can fill, not as errors.
- The customer can submit with unknown pricing. Pricing can be set later.
- Optional competitor URLs should be accepted before extraction because they help narrow the agent's interpretation.

### Existing-Business Context.dev Pipeline

Use Context.dev only after the customer enters a business URL.

1. Normalize the URL to a domain and persist the original URL.
2. Call `utility.prefetch({ domain })` as soon as the URL validates to reduce later latency.
3. Call `brand.retrieve({ domain })` to collect brand title, description, slogan, links, socials, industry, logos, colors, and contact fields.
4. Call `ai.aiQuery({ domain, data_to_extract })` for onboarding-specific business fields.
5. Call `ai.extractProducts({ domain, maxProducts })` only when the site appears product, SaaS, course, or ecommerce-oriented. Treat output as candidate offering evidence, not final truth.
6. Call `web.webScrapeMd({ url, useMainContentOnly: true, includeLinks: true })` for specific pages such as homepage, about, pricing, product, services, and top links from brand retrieval.
7. Store raw Context.dev responses in the source manifest and persist a compact extraction payload for onboarding review.
8. Build the 5E "Does this look right to you?" screen from the compact payload.

Context.dev docs used:

- `llms.txt`: documentation index.
- pre-filled onboarding guide: backend proxy, early domain capture, no secret exposure, editable confirmation.
- AI Query endpoint: extracts requested datapoints from a domain and returns `urls_analyzed` plus `data_extracted`.
- Brand Retrieve endpoint: returns brand identity, description, links, industries, logos, colors, and social fields.
- Product Extraction endpoint: returns products with name, description, features, audience, tags, images, SKU, price, currency, URL, and category.
- Scrape Markdown endpoint: returns LLM-ready Markdown for a URL.

### Context.dev AI Query Datapoints

Use `datapoint_type="text"` unless the SDK docs expose a stronger enum during implementation.

| Datapoint name | Prompt / description | Valid output rule |
|---|---|---|
| `business_model` | "How does this business make money? Choose one: ecommerce, digital_product, saas, service, lead_generation, marketplace, other, unknown. Return unknown if the website does not make this clear." | one enum value only |
| `primary_offering_kind` | "What does the business primarily sell or plan to sell? Choose one: product, service, software, course, lead_gen_offer, marketplace, other, unknown." | one enum value only |
| `primary_offering_name` | "Name the main product, service, software, course, or offer the website emphasizes most." | short text or unknown |
| `primary_offering_description` | "Describe what the main offering helps customers do, using only claims visible on the website." | 1-2 sentences or unknown |
| `target_customer` | "Who appears to be the main buyer or user?" | short text or unknown |
| `pricing_model` | "How does the business charge? Choose one: one_time, subscription, usage_based, seat_based, hourly, project, retainer, consultation, commission, free, not_found, unknown." | one enum value only |
| `price_or_rate` | "If the website states a price, rate, starting price, or plan price, extract it exactly with currency and billing period." | exact text or not_found |
| `important_pages` | "List the homepage, product, service, pricing, about, case study, or contact pages that support these answers." | URLs only |
| `evidence_summary` | "Return the shortest source-grounded explanation for the extracted fields." | cite URLs from analyzed pages |

Adapter rules:

- Do not ask Context.dev to invent missing data.
- Do not convert missing price into `0`.
- Do not convert service pricing into product variants unless an explicit fixed price exists.
- Do not overwrite user edits if late Context.dev data arrives after the customer changed a field.
- Save both raw provider output and the user-confirmed final values.

### New Business Branch

| Step | Customer question | UI pattern | Required | Stored field(s) | Downstream mapping |
|---|---|---|---:|---|---|
| 3N | How does this business make money? | Visual choice list | Yes | `business_model`, `input_mode="manual_seed"` | Business profile, later offer/campaign defaults, internal foundation context |
| 4N | What do you sell or plan to sell? | Choice row: product, service, software, course, lead-gen offer, marketplace, other | Yes | `offering_kind`, `offering_type` | Offering shell, internal category fallback |
| 5N | Product/service-specific name question | Single text input | Yes | `offering_name` | Agent context, offering shell |
| 6N | Product/service-specific buyer outcome question | Short textarea, 1-3 sentences | Yes | `offering_description` | Agent context, buyer setup seed |
| 7N | Product/service-specific pricing question | Branch-specific pricing input | No | `pricing_status`, `price`, `pricing_model` | Later offer setup; no fake defaults |
| 8N | Any competitors your agent should know about? | Optional URL list | No | `competitor_urls[]` | Narrows market prep; never a blocker |
| 9N | Review your workspace | Editable summary + CTA | Yes | Submit payload | Creates workspace and starts background setup workflow |

New-business branch rule: ask only for fields the agent cannot derive from a live business source.

## Offering-Specific Question Copy

Use the selected `offering_kind` to change the questions. Do not reuse product language for services.

| Offering kind | Name question | Outcome question | Pricing question | Stored pricing fields |
|---|---|---|---|---|
| Product | What is the product called? | What does the product help buyers do? | What is the product price? | `pricing_model="one_time"` plus optional `price` |
| Service | What service do you provide? | What outcome does the service create for clients? | How do you charge for your service? | `pricing_model`: hourly, project, retainer, performance, consultation, not_sure; optional `starting_rate` |
| Software/SaaS | What is the software called? | What job does the software help customers do? | How is it priced? | `pricing_model`: subscription, usage_based, seat_based, freemium, custom, not_sure; optional `starting_price` |
| Course/digital product | What is the course or digital product called? | What does the customer learn or achieve? | What is the enrollment or purchase price? | `pricing_model="one_time"` or `subscription`; optional `price` |
| Lead-gen offer | What offer should your agent start with? | What does someone get after opting in? | Is there a paid offer after this? | `pricing_model`: free, paid_followup, consultation, not_sure |
| Marketplace/platform | What side of the marketplace should your agent focus on first? | What problem does that side need solved? | How does the platform make money? | `pricing_model`: commission, subscription, listing_fee, transaction_fee, not_sure |
| Other | What should your agent work on first? | What does the buyer or user get? | How do customers pay, if they do? | free text + optional structured model |

Pricing is always optional. The question changes by offering kind; the system must not require a product-style fixed price for services.

### Screen Copy Shape

Use FernDesk-like phrasing:

- "What should we call this workspace?"
- "Is this new or already live?"
- "What is the business website?"
- "How does this business make money?"
- "What do you sell or plan to sell?"
- "What does the buyer get?"
- "Do you know the price or rate yet?"
- "Any competitors your agent should know about?"
- "Does this look right to you?"
- "Create workspace"

No in-app text should say "research", "foundation docs", "avatar docs", "VOC", or "Strategy V2". Those are internal implementation terms. Each screen should ask the next useful question in marketing-agent language.

## Business Model Choices

Start with these choices:

- E-commerce product
- Digital product or course
- SaaS or software
- Service business
- Lead generation
- Marketplace or platform
- Other

Mapping:

- `ecommerce`: product-first; price optional; source URL can be Shopify/store URL.
- `digital_product`: product/course-first; price optional.
- `saas`: software offering name and buyer outcome; pricing can be later.
- `service`: service-first; collect service name, buyer outcome, delivery model if needed later.
- `lead_generation`: first agent focus is the lead-gen offer or service category.
- `marketplace`: first agent focus is the demand-side category unless user chooses otherwise.
- `other`: store literal value and require offering type/description clarity.

## Product Or Service Handling

Customer-facing language should use **offering** unless the user has explicitly selected product or service.

Domain fields:

- `offering_kind`: `product`, `service`, `software`, `course`, `lead_gen_offer`, `marketplace`, or `other`
- `offering_type`: finer category such as supplement, coaching, SaaS, agency service, course, book, physical product
- `offering_name`
- `offering_description`
- `offering_category`

Persistence rule for the first implementation:

- The current database can still persist the first agent-focus offering in the existing `products` table.
- For service onboarding, store `product_type="service"` or a canonical service subtype and preserve `offering_kind="service"` in the onboarding/foundation payload.
- Do not expose product-only labels in the first-run UI or API docs.
- Do not require product-only artifacts such as product image, SKU, inventory, variant, or fixed price for service onboarding.
- Later, if service workflows need richer fields, add a dedicated offering/service model. Do not block this onboarding redesign on that larger model split.

## Post-Submit Setup Theatre

After submit, the customer sees agent setup states, not research-operation labels and not more inputs.

Setup checklist:

1. Workspace created
2. Offering shell created
3. Agent learning the market
4. Agent mapping buyer patterns
5. Agent preparing positioning context
6. Agent packaging workspace memory
7. Marketing agent ready

Final state:

- "Marketing agent ready"
- Show setup outputs with status: ready, blocked, failed
- CTA: "Open marketing agent"
- Secondary CTA: "Set pricing and offer details" only if pricing is missing or offer setup is next

## Downstream Mapping

| Data | Collected in onboarding? | Used immediately | Used later | Notes |
|---|---:|---|---|---|
| Workspace name | Yes | client/workspace | all flows | Required first screen |
| Business type | Yes | branch UX, payload | workspace lifecycle | Must support `existing` |
| Business website URL | Existing only | extraction source | source provenance | Required for existing-business path |
| Business model | New yes / existing extracted | payload/profile | offer/campaign setup | Existing path should infer and confirm from source |
| Offering kind | Yes | offering shell, agent context | product/service-specific setup | Required; product and service are first-class |
| Offering name | Yes | offering shell, agent context | product/service flows | Required |
| Offering description | Yes | offering shell, agent context | product/service flows | Required |
| Offering type | Yes | offering shell, category fallback | render/asset/service logic | Required |
| Offering category | Optional | internal category | later targeting | Helpful but not a blocker |
| Price/rate | Optional | pricing/variant only if known and relevant | offer setup | Question must match offering kind |
| Competitor URLs | Optional | seed refs | source provenance | Ask both new and existing businesses; helps narrow agent context |
| Proof assets | No | none | offer/copy setup | Ask later |
| Brand voice notes | No | none | copy setup | Ask later |
| Target platforms | No | none | campaign setup | Ask later |
| Target regions | No | none | campaign setup | Ask later |
| Claims/legal constraints | No | none | copy/launch setup | Ask later |
| Product/service media | No | none | creative setup | Ask later |
| Design system/logo | No | none | brand setup | Separate workflow |

## Backend Plan

1. Add `MarketingAgentSetupRequest`.
   - Shared required: `business_type`, `input_mode`.
   - Existing required: `business_url`.
   - New required: `business_model`, `offering_kind`, `offering_name`, `offering_description`, `offering_type`.
   - Optional shared: `workspace_name` if endpoint creates client, `competitor_urls`.
   - Optional new-business fields: `offering_category`, `price`, `starting_rate`, `pricing_model`.
   - Optional existing-business extracted fields: `business_model`, `offering_kind`, `offering_name`, `offering_description`, `offering_type`, `offering_category`, `pricing_status`, `price`, `starting_rate`, `pricing_model`, each with provenance.
   - Remove from this request: proof assets, brand voice notes, target platforms, target regions, funnel position, copy constraints, product image/media.
   - Adapter fields may map `offering_*` into the current product persistence layer, but external API should be offering-first and marketing-agent setup oriented.
   - Internal code may still call the background workflow foundation setup, but API and UI naming should use marketing-agent setup.

2. Add or repurpose endpoint.
   - Preferred: `POST /clients/{client_id}/marketing-agent/setup`.
   - Keep old endpoint only as compatibility wrapper if needed.
   - Existing business must not return 501.

3. Offering persistence.
   - Always create offering shell.
   - In the first implementation, reuse the current product table as the storage shell if needed.
   - Create variant/pricing data only when price or rate is provided and applicable.
   - If price/rate is missing, persist `pricing_status="later"` in onboarding payload and leave pricing to product/service offer setup.
   - Service offerings must not require SKU, inventory, product image, or fixed variant price.
   - Existing-business extracted fields must be persisted with source provenance. Unknown fields must stay unknown, not defaulted.

4. Add an existing-business extraction step.
   - Input: business URL and optional competitor URLs.
   - Provider: Context.dev.
   - Output: source-grounded business profile and first offering candidate(s).
   - Blocks only on inaccessible business URL, not on missing price/category/model.
   - Produces a source manifest before synthesis.
   - Stores raw Context.dev response artifacts and compact reviewed extraction payload.
   - Requires user confirmation or edits on the 5E review screen before creating the workspace.

5. Add `FoundationOnboardingWorkflow`.
   - Reuse Strategy V2 stage 0/foundation activities where possible.
   - Stop after internal foundation docs: steps 01, 03, 04, 06, and generated competitor analysis.
   - Do not enter offer pipeline, offer winner selection, copy context generation, copy pipeline, or copy approval.

6. Persist foundation artifacts.
   - Add artifact type: `strategy_v2_foundation_bundle` or `foundation_research_bundle`.
   - Include doc payloads, summaries, source refs, input snapshot, blocked source list, and provenance ids.
   - Continue storing step payload artifacts for audit/debug.

7. Update downstream prerequisites.
   - Offer strategy starts from approved/ready foundation bundle.
   - Copy starts from foundation + offer outputs, not onboarding.
   - Campaign/launch flows should not require onboarding-time copy artifacts.

## Frontend Plan

1. Rebuild `WorkspaceOnboardingPage` around first-run marketing-agent setup screens.
   - Full-height split shell.
   - Thin progress rail.
   - One question per screen.
   - Persistent right context panel with current answers and setup state.

2. Simplify `OnboardingWizard`.
   - Either replace it with `FoundationOnboardingWizard` or make old wizard legacy-only.
   - Remove dense product editor modal from first-run path.
   - Replace product-only labels with offering-aware copy that branches to product or service after selection.
   - Use `ChoiceList`, `OnboardingProgressRail`, `SetupChecklist`, and `ContextPreviewPanel`.

3. Add branching.
   - Existing business path asks for website URL first, then optional competitors, then review/confirm extracted agent context.
   - Existing business 5E screen asks "Does this look right to you?" and lets the customer edit all extracted fields.
   - New business path asks business model, "What do you sell or plan to sell?", offering-specific details, offering-specific pricing, then optional competitors.
   - Business model changes offering labels and examples.
   - Product/service selection changes naming: price vs rate, product vs service, product image later vs service proof later.
   - Price/rate yes/no controls whether pricing input appears.

4. Add review screen.
   - Show only collected or extracted fields.
   - Existing business review is editable because Context.dev data is source-grounded but not guaranteed correct.
   - New business review is editable so the customer can correct product/service setup before creation.
   - Show deferred fields as "later" only if useful, not as warnings.
   - CTA says "Create workspace".

5. Add marketing-agent-ready screen.
   - Show setup outputs and statuses.
   - No copy approval UI.
   - Next action routes to marketing-agent workspace or offer setup.

## Acceptance Checks

- A user can onboard a new business without price/rate, competitor URLs, proof, voice, target platforms, or target regions.
- A user can onboard an existing business without a 501 error.
- Existing-business onboarding requires only workspace name, business URL, and confirmation of extracted context.
- Existing-business extraction uses Context.dev from a backend proxy.
- The Context.dev API key is read from backend env and never exposed to frontend code or client-visible payloads.
- Context.dev raw responses are captured in a source manifest or equivalent source artifact.
- Existing-business extracted context includes provenance or stays unknown.
- Existing-business 5E review asks "Does this look right to you?" and lets the customer edit business model, offering type, offering name, offering description, category, pricing, and competitors.
- A user can onboard a service without product-only requirements like SKU, variant, inventory, fixed price, or product image.
- New-business pricing questions change by offering kind.
- New-business step 4 asks "What do you sell or plan to sell?"
- New-business flow does not ask whether the product/service/offer can change later.
- Optional competitor URLs appear on both new and existing paths.
- The foundation workflow completes without running offer or copy activities.
- No `strategy_v2_copy` or `strategy_v2_copy_context` artifact is created by foundation onboarding.
- A foundation bundle exists after successful onboarding.
- UI asks one primary question per screen.
- UI copy frames onboarding as setting up a marketing agent, not researching or generating foundation docs.
- Product price or service rate is set later without fake defaults.
- Downstream offer/copy setup asks deferred fields when needed.

## Verification Commands

Expected local checks after implementation:

```bash
cd mos/backend && pytest tests/test_client_onboarding_v2_ordering.py tests/test_strategy_v2_workflow_ordering.py tests/test_api.py
cd mos/frontend && npm run check-semantic-ui
cd mos/frontend && npm run build
cd mos/frontend && ./node_modules/.bin/vitest run src/components/clients/OnboardingWizard.test.tsx
```

Add new focused tests:

- backend schema test for optional price/rate and optional competitor URLs
- backend route test for `business_type="existing"`
- backend route test for `offering_kind="service"` without variant-only/product-only fields
- backend extraction test proving existing-business website URL can create a source-grounded setup payload
- backend Context.dev adapter test for domain prefetch, brand retrieve, AI query, scrape markdown, and optional product extraction calls
- backend test proving the Context.dev token is never returned in API responses or frontend bundles
- workflow test proving marketing-agent setup stops before offer/copy
- artifact test proving foundation bundle persistence
- frontend test for step-by-step branch flow and submit payload
- frontend test for editable 5E "Does this look right to you?" extraction review
- frontend test for new-business "What do you sell or plan to sell?" screen
- frontend test proving product vs service pricing question copy changes
- frontend test proving competitor URLs appear on both branches

## Failure Modes

| Risk | Failure shape | Mitigation |
|---|---|---|
| Shallow diagnosis | Only removing fields from UI while backend still needs them | Split API/workflow contract first |
| Symptom fix | Current wizard gets prettier but still starts full Strategy V2 | Agent setup workflow must stop before offer/copy |
| Willpower plan | Depends on users knowing what to skip | UI should never show later-stage inputs |
| Perfect-day plan | Works only when user has URLs, price, and assets ready | Make those optional with clear later steps |
| Missing metrics | Cannot tell if simplified onboarding helped | Track completion, time-to-submit, failure rates |
| Overengineering | Too many branches for every business model | Keep same core flow, only change labels/examples |
| Scope creep | Adds design system, copy, launch setup, or research-heavy UX back into onboarding | Explicit deferred-fields and customer-language boundary |
| Secret leak | Context.dev API key reaches frontend bundle, logs, or source artifacts | Backend proxy only, env-only key, redaction tests |
| Provider overtrust | Context.dev returns plausible but wrong business data | Editable 5E confirmation; never overwrite user edits |
| Product bias | Product extraction misclassifies service businesses | AI query owns offering kind; product extraction is optional supporting evidence |

## Worst-Day Test

A tired customer can still finish whether the business already exists or is only an idea.

Minimum viable existing-business path:

1. workspace name
2. existing business
3. business website URL
4. optional competitors skipped
5. review "Does this look right to you?"
6. edit any wrong extracted fields
7. create workspace

Minimum viable new-business path:

1. workspace name
2. new business
3. business model
4. product or service
5. offering name
6. offering description
7. offering-specific pricing skipped
8. optional competitors skipped
9. create workspace

Everything else can be skipped, extracted, or set later. Extracted values need source evidence.

## Metrics

Leading:

- screens with exactly one primary question
- required fields count in marketing-agent setup payload
- percentage of users who reach submit without validation errors
- existing-business extraction fields with concrete source provenance
- existing-business extraction fields corrected on 5E review
- Context.dev extraction success, timeout, and unavailable rates
- workflow runs that stop before offer/copy stages

Lagging:

- onboarding completion rate
- median time from start to submit
- internal foundation bundle success rate
- downstream offer setup completion rate
- support/debug issues caused by missing onboarding data

## Parallelization Map

parallelizable: yes

Lanes:

- Backend contract lane: schemas, endpoint, offering/product persistence adapter, artifact type.
- Context.dev lane: backend adapter, prompt datapoints, source manifest persistence, redaction tests.
- Workflow lane: foundation-only workflow and activity reuse.
- Frontend lane: first-run screens and payload submission.
- Verification lane: tests, artifact checks, visual checks.

Expected speed gain: meaningful, because frontend and backend contract work can proceed after the shared payload schema is locked.

Token spend justification: worth using parallel lanes during implementation because this touches workflow, API, UI, and tests.

Write ownership:

- Backend contract lane: `mos/backend/app/schemas/onboarding.py`, `mos/backend/app/routers/clients.py`, enum/migration files.
- Context.dev lane: backend Context.dev client/adapter files, extraction prompt/data-point definitions, related tests.
- Workflow lane: `mos/backend/app/temporal/workflows/*`, foundation activity wrappers/tests.
- Frontend lane: `mos/frontend/src/pages/workspaces/WorkspaceOnboardingPage.tsx`, onboarding components, client API types.
- Verification lane: tests and proof pack only.

Fan-in: main agent owns schema fan-in and final verification.

## Meta-Tooling Opportunity

Create an onboarding contract map generator that compares:

- frontend payload fields
- Pydantic request fields
- workflow input fields
- downstream artifact prerequisites

This would prevent backend requirements from leaking into first-run UX again.

## Owner And Review

Owner: Codex implementation lane after explicit `Ship the plan`.

Review point: after backend contract and first frontend happy path compile, before broad polish.

Stop condition: plan is ready to implement when the question flow, payload contract, downstream mapping, and acceptance checks are locked.

Say "Ship the plan" when you want me to implement and verify it.
