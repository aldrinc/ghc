# MOS AI Systems (Agents, Tools, Workflows)

This file is a catalog of the AI-driven and automation-driven “agents” and workflows in MOS, what they do, and what they can touch.

## Primitives (Simple Definitions)

- **Agent**: a named capability (AI and/or automation) that completes a specific job (draft a page, generate research, launch ads).
- **Tool**: an allowed action the agent can take (load data, generate a draft, call a platform API, save results).
- **Workflow**: the step-by-step sequence an agent follows to get from “request” to “saved output”.
- **Artifact**: something saved for later use (draft versions, images/assets, research outputs, design tokens).

## Funnel Editing Agents (Tool-Based)

These are the “interactive” agents that run as a sequence of tool calls and are traceable as an agent run.

### Funnel Page Draft Agent

What it does:

- Creates or updates a funnel page draft from a prompt.
- Optionally generates the images needed by that draft.
- Saves the result as a new draft version (and can optionally generate template testimonials).

Primary workflow:

1. Load funnel + page + template context.
2. Load product/offer context and brand context (tokens and optional brand docs).
3. Generate a page draft.
4. Apply deterministic fixes (brand logo, product images, template hardening).
5. Validate the draft.
6. Plan images, generate images (optional).
7. Persist the draft version.
8. Generate/apply template testimonials (optional, with retries).

Tools it uses (tool names):

- `context.load_funnel`
- `context.load_product_offer`
- `context.load_design_tokens`
- `context.load_brand_docs`
- `draft.generate_page`
- `draft.apply_overrides`
- `draft.validate`
- `images.plan`
- `images.generate`
- `draft.persist_version`
- `testimonials.generate_and_apply` (optional)

Outputs:

- `FunnelPageVersion` draft saved to the database
- Generated image assets (optional)
- Trace data for the run and each tool call

Where it lives:

- Orchestration: `mos/backend/app/agent/funnel_objectives.py` (`objective.page_draft`)
- Tools: `mos/backend/app/agent/funnel_tools.py`
- Runtime/tracing: `mos/backend/app/agent/runtime.py`

### Funnel Page Testimonials Agent

What it does:

- Generates and applies synthetic testimonials to a page draft (template pages only).

Primary workflow:

1. Load the target draft version (or use provided page content).
2. Generate testimonials in the correct format for the template.
3. Render testimonial media (images) and apply them back onto the page.
4. Save a new draft version containing the testimonial updates.

Tools it uses:

- `testimonials.generate_and_apply`

Where it lives:

- Orchestration: `mos/backend/app/agent/funnel_objectives.py` (`objective.page_testimonials`)
- Tool implementation: `mos/backend/app/agent/funnel_tools.py`

### Funnel Publish Agent

What it does:

- Validates a funnel is publishable and then publishes it.

Primary workflow:

1. Validate the funnel is ready (entry page set, versions exist, links are not broken, etc.).
2. Publish the funnel.

Tools it uses:

- `publish.validate_ready`
- `publish.execute`

Where it lives:

- Orchestration: `mos/backend/app/agent/funnel_objectives.py` (`objective.publish_funnel`)
- Tool implementation: `mos/backend/app/agent/funnel_tools.py`

## Funnel AI Services (Non Tool-Based)

These are AI services used by tools/agents, or older “one-shot” flows that run without the explicit tool runtime.

### Funnel Page Draft Generator (Legacy)

What it does:

- Generates a full page draft (and optionally generates images) in one call.

Where it lives:

- `mos/backend/app/services/funnel_ai.py` (`generate_funnel_page_draft`, `stream_funnel_page_draft`)

Notes:

- This code path contains the “full” end-to-end logic (prompting, parsing/repair, validation, deterministic overrides, image generation, persistence).

### Funnel Testimonials Generator

What it does:

- Generates synthetic testimonials and renders testimonial media to fit supported funnel templates.

Where it lives:

- `mos/backend/app/services/funnel_testimonials.py` (`generate_funnel_page_testimonials`)

## Marketing Execution Agents (Meta)

### Meta Media Buying Agent (Graph API Integration)

What it does:

- Connects MOS to a Meta (Facebook/Instagram) ad account.
- Uploads MOS creative assets (images/videos) to Meta.
- Creates Meta objects for launch: campaigns, ad sets, creatives, and ads.
- Stores a record in MOS of what was created (so you can track what’s live and avoid duplicates).
- Provides a “pipeline view” that shows each asset and its Meta upload/creative/ad status.

Primary workflows:

1. Plan (optional): save “specs” for what you intend to launch.
   - Creative specs: copy + destination URL + CTA for a specific asset.
   - Ad set specs: targeting + budget + schedule + optimization settings for an experiment/campaign.
2. Launch to Meta: push the plan into Meta in the correct order.
   - Upload asset -> create creative -> create campaign -> create ad set -> create ad.
3. Inspect: preview creatives and list remote Meta objects to verify what exists in the ad account.

Tools it uses (API actions):

- Upload an asset to Meta: `POST /meta/assets/{asset_id}/upload`
- Create a creative: `POST /meta/creatives`
- Create a campaign: `POST /meta/campaigns`
- Create an ad set: `POST /meta/adsets`
- Create an ad: `POST /meta/ads`
- Preview a creative: `POST /meta/creatives/{creative_id}/previews`
- Save/list creative specs: `POST /meta/specs/creatives`, `GET /meta/specs/creatives`
- Save/list ad set specs: `POST /meta/specs/adsets`, `GET /meta/specs/adsets`
- Pipeline view (assets + Meta state): `GET /meta/pipeline/assets`
- List remote account objects: `GET /meta/remote/*` (`adimages`, `advideos`, `adcreatives`, `campaigns`, `adsets`, `ads`)

Where it lives:

- API routes: `mos/backend/app/routers/meta_ads.py`
- Meta Graph API client: `mos/backend/app/services/meta_ads.py`
- Persistence models: `mos/backend/app/db/models.py` (`MetaAssetUpload`, `MetaAdCreative`, `MetaCampaign`, `MetaAdSet`, `MetaAd`, `MetaCreativeSpec`, `MetaAdSetSpec`)
- Repository helpers: `mos/backend/app/db/repositories/meta_ads.py`
- Config/env: `mos/backend/app/config.py` (`META_ACCESS_TOKEN`, `META_GRAPH_API_VERSION`, `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_INSTAGRAM_ACTOR_ID`)

## Brand and Design Agents

### Design System Tokens Generator

What it does:

- Generates a brand “design system” for funnel pages (colors, fonts, tokens, defaults) based on brand/product context.

Primary workflow:

1. Start from a base template of required tokens.
2. Ask the model for either a patch (recommended) or a full token set.
3. Validate output against strict rules (required keys, no overriding locked layout tokens, light backgrounds, etc.).

Where it lives:

- `mos/backend/app/services/design_system_generation.py` (`generate_design_system_tokens`)

### Onboarding Design System Builder

What it does:

- Generates a design system during onboarding and ensures a brand logo exists (uses an existing logo if present, otherwise generates a default one).

Where it lives:

- `mos/backend/app/temporal/activities/client_onboarding_activities.py` (`build_design_system_activity`)

## Research and Planning Agents (Temporal)

These run as Temporal activities/workflows (background, durable execution) and typically save results as artifacts.

### PreCanon Market Research Workflow

What it does:

- Runs a multi-step market research pipeline (multiple numbered steps) and persists structured outputs.
- Includes a deep-research step that can run for a long time and may use web search.

Where it lives:

- Workflow orchestration: `mos/backend/app/temporal/workflows/precanon_market_research.py`
- Step prompting/parsing: `mos/backend/app/temporal/precanon/` and `mos/backend/app/prompts/precanon_research/`

Key tools/capabilities it uses (high level):

- LLM text generation for multiple steps (some with web search)
- Deep research jobs for the long research step
- Competitor extraction and enrichment (including Facebook page resolution)
- Artifact persistence (research step outputs and summaries)

### Deep Research Job Service

What it does:

- Runs “deep research” using OpenAI’s background responses API and optionally web search, and stores job status/output in the database.

Where it lives:

- `mos/backend/app/services/deep_research.py` (`DeepResearchJobService`)

### Competitor Facebook Page Resolver

What it does:

- Resolves official competitor Facebook Page URLs.
- First tries deterministic extraction from competitor websites, then uses an LLM with web search for the remaining unresolved competitors.

Where it lives:

- `mos/backend/app/temporal/activities/competitor_facebook_activities.py` (`resolve_competitor_facebook_pages_activity`)

### Strategy Sheet Generator

What it does:

- Generates a campaign strategy “sheet” (goal, hypothesis, channel plan, messaging pillars, risks/mitigations).
- Enforces constraints like “no demographic/targeting details” and validates output shape.

Where it lives:

- `mos/backend/app/temporal/activities/strategy_activities.py` (`build_strategy_sheet_activity`)

### Experiment Spec Generator

What it does:

- Generates a set of testable marketing experiments (one per “angle”) and validates coverage and required fields.

Where it lives:

- `mos/backend/app/temporal/activities/experiment_activities.py` (`build_experiment_specs_activity`)

### Asset Brief Generator (From Experiments)

What it does:

- Generates creative briefs for experiment variants (what to make, constraints, tone, requirements).
- Validates coverage and enforces rules (for example, blocks certain unverified claims).

Where it lives:

- `mos/backend/app/temporal/activities/experiment_activities.py` (`create_asset_briefs_for_experiments_activity`)
