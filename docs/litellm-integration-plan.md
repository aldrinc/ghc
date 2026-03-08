# LiteLLM Integration Plan For Centralized Model Management

Date: 2026-03-06  
Status: Draft for review  
Scope: `mos/backend`, `mos/infra`, runtime env/config, workflow model selection

## Intent

Centralize AI model registration, credentials, routing, and workflow-level model selection through LiteLLM so MOS can:

- add or swap models through configuration instead of code edits
- assign different workflows and workflow steps to different models intentionally
- keep fail-fast behavior with explicit errors instead of silent fallback behavior
- preserve Langfuse observability and Agenta prompt management

For this document, "light LLM" is interpreted as **LiteLLM**.

## Non-Negotiables

- No silent fallbacks.
- No automatic model substitution.
- No changing a workflow's effective model unless the change is explicit in reviewed config.
- No attempt to force non-text/image-provider APIs through LiteLLM unless that path is verified first.
- Agenta remains the prompt registry.
- Langfuse remains the primary app-level trace system.

## Executive Summary

MOS already has a partial LLM abstraction in [`mos/backend/app/llm/client.py`](../mos/backend/app/llm/client.py), but model selection is still fragmented across:

- env vars in [`mos/backend/app/config.py`](../mos/backend/app/config.py)
- per-workflow step config in [`mos/backend/app/temporal/workflows/precanon_market_research.py`](../mos/backend/app/temporal/workflows/precanon_market_research.py)
- step-specific constants in [`mos/backend/app/temporal/activities/strategy_v2_activities.py`](../mos/backend/app/temporal/activities/strategy_v2_activities.py)
- request-level model overrides in funnel and swipe endpoints
- direct provider SDK integrations for OpenAI deep research, Gemini File Search, Claude Files, Gemini vision, and image rendering

The right target is **LiteLLM Proxy as the LLM control plane**, with MOS using stable internal model aliases instead of raw provider model ids.

The practical rollout is:

1. Stand up LiteLLM as a separate service.
2. Route the existing shared text generation client through LiteLLM first.
3. Move workflow model choice to explicit aliases.
4. Migrate compatible workflows first.
5. Leave provider-specific advanced APIs on direct integrations until they are proven behind LiteLLM or replaced with a provider-neutral abstraction.

## Current-State Assessment

### What is already centralized

- Shared text client:
  [`mos/backend/app/llm/client.py`](../mos/backend/app/llm/client.py)
  already normalizes OpenAI-compatible, Anthropic, and Gemini text generation.
- Langfuse tracing:
  [`mos/backend/app/observability/langfuse.py`](../mos/backend/app/observability/langfuse.py)
  and [`docs/langfuse-observability.md`](./langfuse-observability.md).
- Prompt registry abstraction:
  [`mos/backend/app/llm_ops/agenta.py`](../mos/backend/app/llm_ops/agenta.py)
  and [`docs/agenta-llm-ops.md`](./agenta-llm-ops.md).

### What is fragmented today

| Area | Current files | Current pattern | Problem |
| --- | --- | --- | --- |
| Shared LLM defaults | [`mos/backend/app/config.py`](../mos/backend/app/config.py), [`.env.production.example`](../.env.production.example) | Raw provider model ids in env vars | Model management is scattered and env-heavy |
| Precanon research | [`mos/backend/app/temporal/workflows/precanon_market_research.py`](../mos/backend/app/temporal/workflows/precanon_market_research.py) | Per-step env vars like `PRECANON_STEP01_MODEL` | Workflow logic and provider choice are coupled |
| Strategy V2 | [`mos/backend/app/temporal/activities/strategy_v2_activities.py`](../mos/backend/app/temporal/activities/strategy_v2_activities.py) | Many global model constants and step overrides | Hard to reason about effective model policy |
| Funnel generation/testimonials | [`mos/backend/app/agent/funnel_objectives.py`](../mos/backend/app/agent/funnel_objectives.py), [`mos/backend/app/schemas/funnels.py`](../mos/backend/app/schemas/funnels.py) | Request-level raw model overrides | UI/API can bypass a central model registry |
| Deep research | [`mos/backend/app/services/deep_research.py`](../mos/backend/app/services/deep_research.py), [`mos/backend/app/routers/openai_webhooks.py`](../mos/backend/app/routers/openai_webhooks.py) | Direct OpenAI Responses API and webhook handling | Not yet behind a common gateway |
| Claude files/chat | [`mos/backend/app/services/claude_files.py`](../mos/backend/app/services/claude_files.py), [`mos/backend/app/routers/claude.py`](../mos/backend/app/routers/claude.py) | Anthropic Files API and direct Anthropic streaming | Provider-specific document flow |
| Gemini File Search | [`mos/backend/app/services/gemini_file_search.py`](../mos/backend/app/services/gemini_file_search.py), [`mos/backend/app/routers/gemini.py`](../mos/backend/app/routers/gemini.py) | Direct Google GenAI File Search stores + `generate_content` | Provider-specific retrieval flow |
| Swipe stage 1 / ad breakdown | [`mos/backend/app/temporal/activities/swipe_image_ad_activities.py`](../mos/backend/app/temporal/activities/swipe_image_ad_activities.py), [`mos/backend/app/temporal/activities/ad_breakdown_activities.py`](../mos/backend/app/temporal/activities/ad_breakdown_activities.py) | Direct Gemini vision and file-search-aware requests | Same issue; high-feature Gemini path |
| Image generation | [`mos/backend/app/services/image_render_client.py`](../mos/backend/app/services/image_render_client.py) | Higgsfield / creative-service selection | Not an LLM text-routing problem; out of scope for LiteLLM |

### Important current constraints

- Funnel draft generation explicitly requires Claude when image attachments or Claude document blocks are present.
- Swipe image-ad generation has a hard split between stage-1 text/vision prompting and stage-2 image rendering.
- Deep research uses OpenAI background responses and a webhook path today.
- MOS already prefers explicit errors over guessy fallback behavior.

## Recommendation

Adopt **LiteLLM Proxy**, not just the LiteLLM Python SDK.

Why:

- MOS has multiple runtime entrypoints: API server, Temporal worker, scripts, and workflow activities.
- The user requirement is centralized model management, not just a nicer Python call surface.
- A proxy gives a single place for:
  - provider credentials
  - model aliases
  - access control
  - budgets / rate limits
  - per-environment model configuration

## Target Architecture

```text
MOS API / Temporal Worker / Scripts
            |
            v
   Workflow Model Registry
            |
            v
        LLMClient
            |
            v
      LiteLLM Proxy
            |
            +--> OpenAI
            +--> Anthropic
            +--> Gemini
            +--> Baseten / other OpenAI-compatible providers

Direct provider adapters retained temporarily for:
- OpenAI deep research webhook path
- Claude Files document workflow
- Gemini File Search stores and Gemini-specific vision/file flows
- Image rendering providers
```

## Control-Plane Design

We should separate two concerns that are mixed together today.

### 1. LiteLLM model alias registry

LiteLLM should own the mapping from a **stable internal alias** to a real provider model.

Example:

- `mos-precanon-reasoning` -> `openai/gpt-5`
- `mos-strategy-copy` -> `anthropic/claude-sonnet-4-5`
- `mos-funnel-draft-standard` -> `anthropic/claude-sonnet-4-5`

Changing the actual provider model should happen here.

### 2. MOS workflow model registry

MOS should own the mapping from a **workflow/step** to a LiteLLM alias plus capability requirements.

Example:

- `precanon.step01` -> `mos-precanon-reasoning`
- `strategy_v2.copy.qa` -> `mos-strategy-copy-qa`
- `funnel.page_draft` -> `mos-funnel-draft-standard`

Changing which alias a workflow uses should happen here.

This split gives us:

- stable workflow names in application code
- stable model aliases at the proxy boundary
- explicit review points for both workflow policy changes and provider/model changes

## Workflow Migration Tiers

### Tier 1: Move behind LiteLLM first

These already fit the shared text-generation pattern well.

| Workflow / surface | Files | Target transport | Notes |
| --- | --- | --- | --- |
| Precanon steps `01`, `015`, `03`, `06`, `07`, `08`, `09` | [`mos/backend/app/temporal/workflows/precanon_market_research.py`](../mos/backend/app/temporal/workflows/precanon_market_research.py) | LiteLLM proxy | Best first migration |
| Strategy V2 VOC / offer / copy text generation | [`mos/backend/app/temporal/activities/strategy_v2_activities.py`](../mos/backend/app/temporal/activities/strategy_v2_activities.py) | LiteLLM proxy | Large payoff; lots of raw model env sprawl today |
| Design system generation | [`mos/backend/app/services/design_system_generation.py`](../mos/backend/app/services/design_system_generation.py) | LiteLLM proxy | Uses shared client already |
| Shopify theme copy / content planner | [`mos/backend/app/services/shopify_theme_copy_agent.py`](../mos/backend/app/services/shopify_theme_copy_agent.py), [`mos/backend/app/services/shopify_theme_content_planner.py`](../mos/backend/app/services/shopify_theme_content_planner.py) | LiteLLM proxy | Also shared-client friendly |
| Generic direct text routes that do not depend on provider-only file primitives | shared `LLMClient` consumers | LiteLLM proxy | Migrate opportunistically with shared client cutover |

### Tier 2: Migrate only after validation

These may be able to use LiteLLM, but only after we prove the exact endpoint/SDK behavior.

| Workflow / surface | Files | Risk |
| --- | --- | --- |
| Strategy V2 copy QA | [`mos/backend/app/strategy_v2/scorers.py`](../mos/backend/app/strategy_v2/scorers.py) | Currently has its own provider resolution and OpenAI/Anthropic direct code path |
| Funnel page draft generation | [`mos/backend/app/agent/funnel_objectives.py`](../mos/backend/app/agent/funnel_objectives.py), [`mos/backend/app/services/funnel_ai.py`](../mos/backend/app/services/funnel_ai.py) | Claude file blocks and attachment requirements tie model choice to Anthropic features |
| Funnel testimonials | [`mos/backend/app/services/funnel_testimonials.py`](../mos/backend/app/services/funnel_testimonials.py) | Similar concern depending on prompt and asset/document path |
| OpenAI deep research | [`mos/backend/app/services/deep_research.py`](../mos/backend/app/services/deep_research.py) | Background responses + webhook lifecycle must be tested explicitly |

### Tier 3: Keep direct initially

These should not be forced through LiteLLM in phase 1.

| Workflow / surface | Files | Why keep direct initially |
| --- | --- | --- |
| Claude Files upload / Claude chat with attached documents | [`mos/backend/app/services/claude_files.py`](../mos/backend/app/services/claude_files.py), [`mos/backend/app/routers/claude.py`](../mos/backend/app/routers/claude.py) | Provider-specific file id/document block semantics |
| Gemini File Search store management and Gemini chat over those stores | [`mos/backend/app/services/gemini_file_search.py`](../mos/backend/app/services/gemini_file_search.py), [`mos/backend/app/routers/gemini.py`](../mos/backend/app/routers/gemini.py) | Provider-specific file-search store API |
| Swipe image-ad stage 1 | [`mos/backend/app/temporal/activities/swipe_image_ad_activities.py`](../mos/backend/app/temporal/activities/swipe_image_ad_activities.py) | Gemini vision + file search + special output handling |
| Ad breakdown | [`mos/backend/app/temporal/activities/ad_breakdown_activities.py`](../mos/backend/app/temporal/activities/ad_breakdown_activities.py) | Gemini media upload + vision-heavy flow |
| Image rendering | [`mos/backend/app/services/image_render_client.py`](../mos/backend/app/services/image_render_client.py) | Not a LiteLLM use case |

## Proposed Configuration Layout

### LiteLLM proxy config

Add a new repo-managed config file:

- `mos/infra/litellm/config.yaml`

Example shape:

```yaml
model_list:
  - model_name: mos-precanon-reasoning
    litellm_params:
      model: openai/gpt-5
      api_key: os.environ/OPENAI_API_KEY

  - model_name: mos-strategy-copy
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: mos-design-system
    litellm_params:
      model: openai/gpt-5
      api_key: os.environ/OPENAI_API_KEY

litellm_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/LITELLM_DATABASE_URL
  set_verbose: false
```

Rules for this file:

- Only stable internal aliases appear in MOS app config.
- Raw provider model ids live here.
- No router fallback chains unless explicitly approved later.
- No alias should point to a different provider/model without review.

### MOS workflow model registry

Add a repo-managed workflow policy file:

- `mos/backend/app/llm/workflow_models.yaml`

Example shape:

```yaml
workflows:
  precanon.step01:
    transport: litellm_proxy
    model_alias: mos-precanon-reasoning
    requires:
      - text
      - structured_output
      - web_search

  precanon.step04:
    transport: direct_openai
    provider_model: o3-deep-research-2025-06-26
    requires:
      - responses_api
      - background_mode
      - web_search

  strategy_v2.copy:
    transport: litellm_proxy
    model_alias: mos-strategy-copy
    requires:
      - text
      - structured_output

  funnel.page_draft:
    transport: direct_anthropic
    provider_model: claude-sonnet-4-20250514
    requires:
      - vision
      - document_blocks
```

Rules for this file:

- It is the single source of truth for workflow-to-model policy.
- Capability mismatches must raise startup or runtime config errors.
- It is acceptable for the file to use direct-provider transports temporarily.
- The long-term goal is to reduce direct-provider entries over time.

### Environment variables to add

Add to [`mos/backend/app/config.py`](../mos/backend/app/config.py) and env examples:

- `LITELLM_ENABLED`
- `LITELLM_PROXY_BASE_URL`
- `LITELLM_PROXY_API_KEY`
- `LITELLM_PROXY_TIMEOUT_SECONDS`
- `LITELLM_WORKFLOW_REGISTRY_PATH`
- `LITELLM_PROXY_HEALTHCHECK_TIMEOUT_SECONDS`

For infra only:

- `LITELLM_MASTER_KEY`
- `LITELLM_DATABASE_URL`
- provider secrets consumed by the LiteLLM container

### Environment variables to deprecate gradually

We should not remove existing workflow model env vars immediately. Instead:

- phase 1: allow them to hold **aliases** instead of raw provider model ids
- phase 2: replace them with workflow registry entries
- phase 3: remove or limit them to emergency override use only

Examples:

- `PRECANON_STEP01_MODEL=mos-precanon-reasoning`
- `STRATEGY_V2_COPY_MODEL=mos-strategy-copy`

## Backend Code Changes

### 1. Make LiteLLM an explicit backend dependency

Current state:

- `litellm` is present in `mos/backend/uv.lock`
- `litellm` is importable in the backend venv
- it is **not** declared explicitly in [`mos/backend/pyproject.toml`](../mos/backend/pyproject.toml)

Plan:

- add `litellm` explicitly to `mos/backend/pyproject.toml`
- keep the version pinned by lockfile/update process

Reason:

- the project should not rely on a transitive dependency for a core control-plane component

### 2. Add a workflow registry loader

Create:

- `mos/backend/app/llm/workflow_registry.py`

Responsibilities:

- load and validate `workflow_models.yaml`
- expose `resolve_workflow_model(workflow_key: str) -> WorkflowModelPolicy`
- validate capability requirements
- produce clear config errors at startup or first access

### 3. Extend `LLMClient` to support LiteLLM proxy mode

Primary file:

- [`mos/backend/app/llm/client.py`](../mos/backend/app/llm/client.py)

Planned behavior:

- if `transport == litellm_proxy`, send requests to `LITELLM_PROXY_BASE_URL`
- use LiteLLM aliases, not raw provider model ids
- continue using OpenAI-compatible request formats for chat/responses paths
- attach metadata/tags needed for observability and spend analysis

Do not:

- silently fall back from proxy to direct provider
- silently rewrite unsupported workflows to another model

### 4. Introduce workflow-aware resolution instead of raw model scattering

Update the main workflow entrypoints so they ask for a workflow policy first, not a model string first.

Files likely involved:

- [`mos/backend/app/temporal/workflows/precanon_market_research.py`](../mos/backend/app/temporal/workflows/precanon_market_research.py)
- [`mos/backend/app/temporal/activities/strategy_v2_activities.py`](../mos/backend/app/temporal/activities/strategy_v2_activities.py)
- [`mos/backend/app/agent/funnel_objectives.py`](../mos/backend/app/agent/funnel_objectives.py)
- [`mos/backend/app/services/design_system_generation.py`](../mos/backend/app/services/design_system_generation.py)
- [`mos/backend/app/services/shopify_theme_copy_agent.py`](../mos/backend/app/services/shopify_theme_copy_agent.py)
- [`mos/backend/app/services/shopify_theme_content_planner.py`](../mos/backend/app/services/shopify_theme_content_planner.py)

Target pattern:

- workflow code refers to `workflow_key`
- registry resolves `transport + alias + constraints`
- client executes according to resolved policy

### 5. Keep direct adapters explicit

Do not hide direct-provider exceptions inside generic code paths.

Recommended approach:

- keep direct adapters named clearly:
  - `direct_openai`
  - `direct_anthropic`
  - `direct_gemini`
- require an explicit transport in registry for those workflows
- log both requested workflow key and resolved transport

## Observability And Audit Design

### Langfuse remains primary

Keep existing tracing behavior in:

- [`mos/backend/app/observability/langfuse.py`](../mos/backend/app/observability/langfuse.py)
- [`docs/langfuse-observability.md`](./langfuse-observability.md)

### Add model governance metadata to traces

Every managed request should include:

- `workflowKey`
- `modelAlias`
- `transport`
- `resolvedProvider`
- `resolvedProviderModel`
- `orgId`
- `workflowRunId`
- `agentRunId`
- `stepKey` where relevant

### Persist better model audit fields

Current DB fields are too thin for a proper gateway rollout.

Examples:

- [`mos/backend/app/db/models.py`](../mos/backend/app/db/models.py) `AgentRun.model`
- [`mos/backend/app/db/models.py`](../mos/backend/app/db/models.py) `DeepResearchJob.model`

Recommended additions:

- `model_alias`
- `resolved_model`
- `resolved_provider`
- `transport`

These can be added either as new columns or as structured metadata fields if we want a smaller migration first.

## Deployment Plan

### Local development

Update:

- [`mos/infra/docker-compose.yml`](../mos/infra/docker-compose.yml)

Add:

- `litellm` service
- optional LiteLLM Postgres if we want separate storage, or reuse existing Postgres with a separate database/schema
- healthcheck

### Production deployment

Update:

- [`mos/infra/docker-compose.deploy.yml`](../mos/infra/docker-compose.deploy.yml)

Add:

- `litellm` service
- env file wiring for LiteLLM secrets
- networking so backend and worker call LiteLLM over the internal Docker network

### Secret handling

Move toward this split:

- LiteLLM container owns provider API keys for migrated workflows
- backend/worker keep only:
  - LiteLLM service key
  - direct-provider keys still needed for non-migrated advanced flows

### Health and startup checks

Add startup validation so backend/worker fail clearly when:

- `LITELLM_ENABLED=true` but proxy base URL/key are missing
- workflow registry references an alias that LiteLLM does not expose
- a workflow requires a capability not declared for its selected transport

## Phased Delivery Plan

### Phase 0: Freeze And Inventory

Goal:

- record the current effective model map before introducing a control plane

Tasks:

- inventory every workflow and step that selects a model
- decide the first alias set and naming convention
- add this plan document
- make LiteLLM an explicit dependency in `pyproject.toml`

Exit criteria:

- a reviewed alias naming scheme exists
- a reviewed workflow inventory exists

### Phase 1: Stand Up LiteLLM Proxy

Goal:

- deploy LiteLLM without changing MOS runtime behavior yet

Tasks:

- add `mos/infra/litellm/config.yaml`
- add compose/deploy service definitions
- add LiteLLM env vars to examples
- verify health and auth locally

Exit criteria:

- LiteLLM is running locally and in deploy environments
- alias config is version-controlled

### Phase 2: Move Shared Text Client To Proxy

Goal:

- migrate shared `LLMClient` text generation to LiteLLM for compatible flows

Tasks:

- add `workflow_registry.py`
- teach `LLMClient` about `litellm_proxy` transport
- route Tier 1 workflows through LiteLLM
- keep direct-provider paths unchanged for Tier 2/Tier 3

Exit criteria:

- Precanon non-step04 flows work via LiteLLM
- Strategy V2 text flows work via LiteLLM
- design system + Shopify theme copy flows work via LiteLLM

### Phase 3: Tighten Workflow Governance

Goal:

- remove raw model ids from application-level workflow config

Tasks:

- convert existing workflow env vars to aliases only
- move policy to `workflow_models.yaml`
- reject raw provider model ids in migrated workflow entrypoints

Exit criteria:

- migrated workflows no longer depend on raw provider model ids in code

### Phase 4: Evaluate Advanced Provider Paths

Goal:

- determine which advanced integrations can actually move behind LiteLLM

Tasks:

- deep research proxy proof-of-compatibility
- Anthropic files / document block proof-of-compatibility
- Gemini File Search store proof-of-compatibility
- decide whether to keep those direct or re-architect to a provider-neutral retrieval/document abstraction

Exit criteria:

- each advanced path has an explicit decision:
  - migrate now
  - keep direct
  - redesign first

### Phase 5: Cleanup

Goal:

- simplify runtime secrets and remove obsolete config

Tasks:

- remove unused direct-provider env vars from backend where possible
- document final workflow model policy
- add runbooks for changing aliases safely

Exit criteria:

- model changes happen through reviewed config, not code edits

## Testing Strategy

### Unit tests

Add tests for:

- workflow registry loading/validation
- capability mismatch errors
- LiteLLM proxy client initialization
- alias resolution behavior
- no-fallback behavior

Likely files:

- `mos/backend/tests/test_litellm_workflow_registry.py`
- `mos/backend/tests/test_litellm_client.py`

### Integration tests

Add targeted tests for:

- chat completions via LiteLLM
- responses API via LiteLLM for reasoning/web-search-compatible workflows
- streaming via LiteLLM
- structured JSON outputs via LiteLLM

### Workflow smoke tests

Minimum smoke set:

- precanon step 01
- precanon step 03
- strategy v2 voc
- strategy v2 copy
- design system generation
- Shopify theme copy

### Non-regression tests for direct exceptions

Ensure unchanged behavior for:

- deep research
- Claude file uploads and Claude streaming chat
- Gemini File Search
- swipe image-ad stage 1
- ad breakdown

## Rollout And Rollback

### Rollout

- enable LiteLLM in local dev first
- enable Tier 1 workflows behind a feature flag
- compare outputs, traces, and latency/cost against baseline
- enable in production for a small internal workflow subset first

### Rollback

Rollback must be explicit config, not automatic runtime fallback.

Recommended rollback levers:

- `LITELLM_ENABLED=false` for broad rollback
- per-workflow transport override back to direct provider
- revert LiteLLM alias mapping in config via deploy

## Risks

### Risk: advanced provider APIs are not actually proxy-compatible

Impact:

- broken document/file-search/vision flows

Mitigation:

- keep those flows direct until tested

### Risk: proxy hides actual provider/model in traces

Impact:

- harder debugging and auditability

Mitigation:

- persist and trace both alias and resolved provider/model

### Risk: current env sprawl survives and creates two sources of truth

Impact:

- operator confusion

Mitigation:

- move to workflow registry, then deprecate raw env model ids

### Risk: backend still needs direct provider secrets for exception flows

Impact:

- not all secrets are centralized immediately

Mitigation:

- treat this as an explicit transitional state, not the final architecture

## Decisions Needed Before Implementation

1. Alias naming convention:
   `mos-<workflow>-<purpose>` vs `workflow.<family>.<step>`
2. Whether to keep workflow policy in YAML only, or support DB-backed admin overrides later.
3. Whether deep research should stay direct until webhook parity is proven.
4. Whether funnel draft/testimonial flows should be redesigned around a provider-neutral document context layer before trying to proxy them.
5. Whether Gemini File Search should remain direct long-term or be replaced with a provider-neutral retrieval layer.

## Recommended First Slice

If the goal is quickest value with lowest regression risk, implement in this order:

1. LiteLLM service and config in `mos/infra`
2. explicit LiteLLM dependency and backend settings
3. workflow registry
4. `LLMClient` proxy mode
5. migrate:
   - precanon non-step04
   - strategy v2 text flows
   - design system generation
   - Shopify theme copy/content planner

Do **not** put the following into the first slice:

- deep research webhook flow
- Claude Files
- Gemini File Search
- swipe image-ad stage 1
- ad breakdown
- image rendering

## Reference Files In This Repo

- Shared client: [`mos/backend/app/llm/client.py`](../mos/backend/app/llm/client.py)
- Backend settings: [`mos/backend/app/config.py`](../mos/backend/app/config.py)
- Precanon workflow: [`mos/backend/app/temporal/workflows/precanon_market_research.py`](../mos/backend/app/temporal/workflows/precanon_market_research.py)
- Strategy V2: [`mos/backend/app/temporal/activities/strategy_v2_activities.py`](../mos/backend/app/temporal/activities/strategy_v2_activities.py)
- Funnel objective runner: [`mos/backend/app/agent/funnel_objectives.py`](../mos/backend/app/agent/funnel_objectives.py)
- Deep research: [`mos/backend/app/services/deep_research.py`](../mos/backend/app/services/deep_research.py)
- OpenAI webhook route: [`mos/backend/app/routers/openai_webhooks.py`](../mos/backend/app/routers/openai_webhooks.py)
- Claude files: [`mos/backend/app/services/claude_files.py`](../mos/backend/app/services/claude_files.py)
- Claude route: [`mos/backend/app/routers/claude.py`](../mos/backend/app/routers/claude.py)
- Gemini File Search: [`mos/backend/app/services/gemini_file_search.py`](../mos/backend/app/services/gemini_file_search.py)
- Gemini route: [`mos/backend/app/routers/gemini.py`](../mos/backend/app/routers/gemini.py)
- Swipe image ads: [`mos/backend/app/temporal/activities/swipe_image_ad_activities.py`](../mos/backend/app/temporal/activities/swipe_image_ad_activities.py)
- Ad breakdown: [`mos/backend/app/temporal/activities/ad_breakdown_activities.py`](../mos/backend/app/temporal/activities/ad_breakdown_activities.py)
- Observability: [`docs/langfuse-observability.md`](./langfuse-observability.md)
- Prompt registry: [`docs/agenta-llm-ops.md`](./agenta-llm-ops.md)
- Deployment compose: [`mos/infra/docker-compose.yml`](../mos/infra/docker-compose.yml), [`mos/infra/docker-compose.deploy.yml`](../mos/infra/docker-compose.deploy.yml)

## External References

- LiteLLM docs home and proxy overview: <https://docs.litellm.ai/>
- LiteLLM proxy config docs: <https://docs.litellm.ai/docs/proxy/configs>
- LiteLLM virtual keys docs: <https://docs.litellm.ai/docs/proxy/virtual_keys>
- LiteLLM model access docs: <https://docs.litellm.ai/docs/proxy/model_access>
- LiteLLM cost tracking docs: <https://docs.litellm.ai/docs/proxy/cost_tracking>
- LiteLLM supported endpoints docs: <https://docs.litellm.ai/docs/supported_endpoints>
