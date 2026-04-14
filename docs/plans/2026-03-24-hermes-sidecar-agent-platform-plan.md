# Hermes Sidecar Agent Platform Plan

## Decision

Use Hermes as the agent runtime and chat interaction sidecar, but keep mOS as the source of truth for tools, artifacts, approvals, tenancy, and mirrored memory.

This plan intentionally does **not** treat Hermes as the business system of record. Instead:

- Hermes owns the live agent loop, native session state, `SOUL.md`, skills, and native bounded memory for a scoped agent instance.
- mOS owns the canonical thread record, tool registry, draft/final artifacts, approval state, mirrored memory, and downstream contracts.
- Hermes talks to mOS through a runtime-agnostic tool interface, ideally via MCP.

This gives us:

- a general agent runtime we can customize
- chat-first HITL for offer, copy, author, and future agents
- native Hermes memory inside a scoped workspace instance
- a portable mOS memory layer so learnings are not trapped in one Hermes home
- the ability to swap or add runtimes later without rewriting the toolkit

## Why This Option

This option fits the repo and the product direction better than either extreme:

- It is more capable than the current in-house `AgentRuntime`, which today is only fully used for funnel draft/publish flows.
- It is lower risk than making Hermes the system of record for business artifacts and approvals.
- It supports the user-facing model you want: direct conversation with a persistent agent thread, revision in chat, explicit finalization, then downstream generation.

Hermes already provides the runtime primitives we want:

- persistent sessions and session search
- native `SOUL.md` identity
- native bounded memory
- skills and toolsets
- MCP integration
- a general tool-calling agent loop

We should adopt those primitives, but place them behind mOS-owned scope, security, and state boundaries.

## Design Principles

1. No silent model switching.
   mOS chooses the exact model for a run. Hermes may not swap to a fallback model without explicit authorization and visible audit.

2. Error clearly instead of guessing.
   Missing required inputs, unsafe tool invocations, or blocked approvals must fail with a clear, structured error.

3. Tools are the platform.
   The long-term value is not Hermes itself. It is the mOS toolkit that Hermes calls.

4. Every write must be typed and auditable.
   Draft writes, finalization, memory writes, and external actions must all carry provenance, idempotency, and explicit scope.

5. Artifacts remain exact.
   Memory helps guide future work. Artifacts remain the canonical source for exact approved content.

6. Native Hermes memory is allowed, but scoped.
   If Hermes owns memory, it must live inside an isolated agent home for a specific workspace and profile.

7. Mirrored memory is required.
   We still need an mOS-side mirrored memory ledger so memory is portable across agents and not trapped inside a single Hermes instance.

## Existing mOS Building Blocks

These are the current repo surfaces we should build on rather than replace:

- In-house tool runtime:
  - `mos/backend/app/agent/runtime.py`
  - `mos/backend/app/agent/types.py`
  - `mos/backend/app/agent/funnel_tools.py`
  - `mos/backend/app/agent/funnel_objectives.py`
- Existing agent persistence:
  - `mos/backend/app/db/models.py` (`AgentRun`, `AgentToolCall`, `AgentArtifact`)
  - `mos/backend/app/routers/agent_runs.py`
- Offer/copy domain logic and contracts:
  - `mos/backend/app/temporal/activities/strategy_v2_activities.py`
  - `mos/backend/app/temporal/workflows/strategy_v2.py`
  - `mos/backend/app/strategy_v2/contracts.py`
  - `mos/backend/app/strategy_v2/downstream.py`
  - `mos/backend/app/strategy_v2/template_bridge.py`
  - `mos/backend/app/strategy_v2/translation.py`
- Surface generation and publishing:
  - `mos/backend/app/services/funnel_ai.py`
  - `mos/backend/app/services/funnel_testimonials.py`
  - `mos/backend/app/services/shopify_theme_copy_agent.py`
  - `mos/backend/app/services/storefront_templates.py`
  - `mos/backend/app/services/site_imports.py`
  - `mos/backend/app/services/funnels.py`
- Campaign and launch context:
  - `mos/backend/app/services/campaign_creative_context.py`
  - `mos/backend/app/services/campaign_launch_context.py`
  - `mos/backend/app/services/meta_media_buying.py`
  - `mos/backend/app/services/paid_ads_qa.py`

The right move is to lift these capabilities behind a single tool contract layer.

## Hermes Integration Boundary

### Ownership

| Concern | Hermes | mOS |
| --- | --- | --- |
| Live chat loop | Yes | No |
| Session continuity | Yes | Mirror key metadata |
| `SOUL.md` and profile identity | Yes | Supplies overlays and scope |
| Native bounded memory | Yes | Mirrors approved memory |
| Skills / procedures | Yes | Supplies domain packs and policy |
| Tool execution | Calls tools | Implements tools |
| Artifact storage | No | Yes |
| Approval state | No | Yes |
| Tenancy and workspace scoping | No | Yes |
| Downstream contracts | No | Yes |
| Model policy | Obeys config | Defines and audits |

### Runtime Shape

The recommended implementation is:

1. mOS runs a `mos-mcp-server`.
2. Hermes sidecars attach to that MCP server.
3. The same mOS tool contracts can also be exposed to:
   - the current in-house `AgentRuntime`
   - future runtimes
   - direct HTTP/internal orchestration if needed

This keeps the toolkit runtime-agnostic.

## Workspace And Instance Scoping

Hermes memory is acceptable only if the Hermes home is isolated per scope.

Recommended Hermes instance scope:

- `org_id`
- `client_id`
- `product_id`
- `agent_profile`

Example profiles:

- `general`
- `offer`
- `copy`
- `author`
- `media_buyer`

Recommended filesystem layout:

```text
/var/lib/mos/hermes/
  org_<org_id>/
    client_<client_id>/
      product_<product_id>/
        copy/
          SOUL.md
          config.yaml
          memories/
          skills/
          state.db
          sessions/
        offer/
          SOUL.md
          config.yaml
          memories/
          skills/
          state.db
          sessions/
```

Why this matters:

- Hermes native memory and session search stay inside one workspace/profile boundary.
- Copy agent memory does not bleed into offer or author unless we deliberately share it.
- A later `author` agent can have its own identity, memory, and skills without contaminating the `copy` instance.

## Dual-Memory Architecture

We should explicitly support two memory planes.

### 1. Hermes Native Memory

Purpose:

- improve local continuity inside a specific Hermes instance
- capture working lessons, style reminders, and profile-local conventions

Storage:

- Hermes-managed native memory files and session history

Allowed contents:

- local procedural shortcuts
- role/persona notes
- scoped style preferences
- small summaries of prior approved work

Not sufficient for:

- cross-agent transfer
- multi-workspace reporting
- approval and provenance audit
- durable business knowledge that downstream systems depend on

### 2. mOS Mirrored Memory

Purpose:

- persist portable, approved, queryable knowledge outside Hermes
- support cross-agent sharing when needed
- make memory part of the business audit trail

Storage:

- new mOS tables for memory items, sources, approvals, and bundles

Kinds:

- `episodic_summary`
- `semantic_preference`
- `approved_claim_rule`
- `voice_constraint`
- `offer_learning`
- `copy_learning`
- `surface_adaptation`
- `tooling_lesson`

Statuses:

- `candidate`
- `approved`
- `rejected`
- `archived`

Sources:

- explicit user instructions in chat
- finalized artifacts
- approved thread summaries
- explicit “remember this” actions

### Memory Sync Rule

We should not try to fully sync every Hermes memory mutation into mOS in real time.

Instead:

- Hermes can own short-form native memory locally.
- mOS periodically extracts memory candidates from:
  - finalized artifacts
  - explicit user messages
  - optional Hermes memory snapshots
- mOS approves, rejects, or archives candidates.
- Approved items can later be projected back into Hermes as context or skill material.

That keeps Hermes useful without making its internal memory files the canonical ledger.

## Thread Model

We need first-class agent threads in mOS even if Hermes keeps its own sessions.

### New Tables

- `agent_threads`
- `agent_thread_messages`
- `agent_thread_participants`
- `agent_memory_items`
- `agent_memory_sources`
- `agent_memory_bundles`
- `agent_checkpoints`
- `agent_runtime_bindings`

### `agent_threads`

Core fields:

- `id`
- `org_id`
- `client_id`
- `product_id`
- `campaign_id` nullable
- `agent_profile`
- `runtime_kind` (`hermes`)
- `runtime_binding_id`
- `status`
- `active_model`
- `title`
- `created_by_user_id`
- `last_activity_at`

### `agent_runtime_bindings`

Purpose:

- map an mOS thread to a Hermes session and home

Core fields:

- `thread_id`
- `runtime_kind`
- `instance_scope_key`
- `hermes_home_path`
- `hermes_session_id`
- `runtime_metadata_json`

### Thread State Machine

- `active`
- `awaiting_agent`
- `awaiting_human`
- `ready_to_finalize`
- `finalized`
- `closed`
- `errored`

## Artifact Lifecycle

Artifacts need a stricter lifecycle than Hermes native outputs.

### States

- `draft`
- `candidate`
- `approved`
- `final`
- `superseded`
- `rejected`

### Required Operations

- create draft
- revise draft
- compare draft versions
- finalize one version
- promote finalized version to canonical downstream artifact
- attach artifact to thread
- derive memory from artifact

### Canonical Artifact Types We Must Preserve

At minimum we need compatibility with:

- `strategy_v2_stage3`
- `strategy_v2_offer`
- `strategy_v2_copy`
- `strategy_v2_copy_context`
- `campaign_creative_context`
- existing funnel/page draft artifacts

The Hermes sidecar should never decide canonical storage shape. mOS must.

## Tool Contract Standard

Every tool in the new toolkit must declare:

- `name`
- `version`
- `category`
- `scope requirements`
- `read/write class`
- `args schema`
- `result schema`
- `idempotency behavior`
- `approval requirement`
- `timeout budget`
- `async capability`
- `audit payload fields`
- `backing module or service`

### Read/Write Classes

- `R0`: read-only
- `W1`: draft write only
- `W2`: finalization or approval write
- `W3`: external actuation or irreversible mutation

### Approval Policy

- `none`
- `thread_user_confirmation`
- `workspace_operator_only`
- `always_blocked_for_agent`

This should be encoded in the tool registry itself, not buried in prompt text.

## Toolkit Design

We should build the toolkit in layers.

### Layer A: Platform Primitives

These tools are required for every agent profile.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.thread.get` | R0 | Load thread metadata and latest state | new thread service |
| `mos.thread.append_message` | W1 | Persist user/assistant/tool messages | new thread service |
| `mos.thread.set_status` | W2 | Change thread state | new thread service |
| `mos.context.bundle` | R0 | Build scoped context packet for the runtime | new context composer |
| `mos.artifact.list` | R0 | List artifacts in scope | `routers/artifacts.py`, artifact repo |
| `mos.artifact.get` | R0 | Fetch one artifact payload | artifact repo |
| `mos.artifact.save_draft` | W1 | Save draft output tied to thread | new artifact adapter |
| `mos.artifact.promote` | W2 | Promote one draft to final/canonical | new promotion service |
| `mos.memory.search` | R0 | Query approved mirrored memory in scope | new memory service |
| `mos.memory.write_candidate` | W1 | Propose memory candidate | new memory service |
| `mos.memory.approve` | W2 | Approve candidate memory | new memory service |
| `mos.memory.bundle_export` | R0 | Export approved memory bundle for another agent | new memory service |
| `mos.job.start` | W1 | Start long-running async mOS job | new job facade over workflows/services |
| `mos.job.status` | R0 | Poll async job status | new job facade |
| `mos.approval.request` | W1 | Create explicit approval item | new approval service |
| `mos.approval.resolve` | W2 | Approve/reject pending item | new approval service |
| `mos.obs.log_event` | W1 | Emit structured audit event | observability layer |

### Layer B: Context And Retrieval Tools

These are domain-aware read tools.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.context.load_strategy_v2` | R0 | Load normalized Strategy V2 outputs | `strategy_v2/downstream.py` |
| `mos.context.load_campaign_creative_context` | R0 | Load campaign creative packet | `campaign_creative_context.py` |
| `mos.context.load_design_system` | R0 | Load design tokens and logos | `design_systems.py` |
| `mos.context.load_brand_docs` | R0 | Load Claude/Gemini file references and docs | `claude_files.py`, `gemini_file_search.py` |
| `mos.context.load_product_offer` | R0 | Load product, variants, offers, checkout facts | products/shopify services |
| `mos.context.load_surface_template` | R0 | Load template/schema for page/site surface | `funnel_templates.py`, `storefront_templates.py` |
| `mos.context.search_prompt_assets` | R0 | Load canonical prompt assets and provenance | `strategy_v2/prompt_runtime.py` |

### Layer C: Offer Tools

These are the tools the Hermes `offer` profile should have.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.offer.load_input_packet` | R0 | Assemble validated offer input packet | `strategy_v2/translation.py`, contracts |
| `mos.offer.run_pipeline` | W1 | Execute step-01 to step-03 candidate generation | extracted from `strategy_v2_activities.py` |
| `mos.offer.score_pairs` | R0 | Score/rank UMP/UMS pairs | `strategy_v2/scorers.py` |
| `mos.offer.build_variants` | W1 | Build Step 04 variants | extracted from `strategy_v2_activities.py` |
| `mos.offer.score_variants` | R0 | Run Step 05 scoring | `strategy_v2/scorers.py` |
| `mos.offer.finalize_variant` | W2 | Create final Stage 3 + offer artifacts | extracted from `strategy_v2_activities.py` |
| `mos.offer.build_copy_context` | W1 | Produce copy context files from offer result | `strategy_v2/translation.py` |
| `mos.offer.export_memory_bundle` | R0 | Emit offer learnings for other profiles | new memory bundle service |

### Layer D: Copy Tools

These are the tools the Hermes `copy` profile should have.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.copy.load_input_packet` | R0 | Assemble Stage 3 + copy context + surface profile | `strategy_v2/copy_input_packet.py` |
| `mos.copy.generate_longform` | W1 | Produce presell/sales copy bundle | extracted from `strategy_v2_activities.py` |
| `mos.copy.run_headline_qa` | R0 | Evaluate headline candidates | `strategy_v2/scorers.py` |
| `mos.copy.extract_promise_contract` | W1 | Produce promise contract | extracted from `strategy_v2_activities.py` |
| `mos.copy.validate_quality` | R0 | Run quality and semantic gates | `copy_quality.py`, `copy_semantic_gates.py` |
| `mos.copy.build_template_payloads` | W1 | Convert copy into template patch operations | `template_bridge.py` |
| `mos.copy.finalize_bundle` | W2 | Promote copy bundle to canonical artifact | new promotion service |
| `mos.copy.export_memory_bundle` | R0 | Emit approved copy learnings | new memory bundle service |

### Layer E: Surface Generation Tools

These are reusable outputs from copy/offer into pages, sites, and storefronts.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.surface.generate_funnel_draft` | W1 | Generate or update funnel page draft | `funnel_ai.py`, current funnel tools |
| `mos.surface.apply_template_overrides` | W1 | Apply deterministic cleanup to draft | current funnel tools |
| `mos.surface.generate_images` | W1 | Fill image slots | `funnels.py`, image services |
| `mos.surface.generate_testimonials` | W1 | Generate page testimonials | `funnel_testimonials.py` |
| `mos.surface.generate_sales_carousel` | W1 | Generate sales carousel assets | `funnel_testimonials.py` |
| `mos.surface.generate_shopify_theme_copy` | W1 | Fill theme component copy slots | `shopify_theme_copy_agent.py` |
| `mos.surface.generate_storefront_variants` | W1 | Create storefront template variants | `storefront_templates.py`, `template_variant_engine.py` |
| `mos.surface.import_site` | W1 | Import external site and normalize sections | `site_imports.py` |

### Layer F: Campaign And Ads Tools

These are for future `author`, `copy`, and `media_buyer` profiles.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.ads.build_creative_context` | R0 | Load normalized campaign creative inputs | `campaign_creative_context.py` |
| `mos.ads.generate_copy_pack` | W1 | Produce ad copy pack from offer/copy memory | new adapter around campaign copy generation |
| `mos.ads.build_asset_briefs` | W1 | Build asset briefs for campaigns | current campaign generation flow |
| `mos.ads.generate_assets` | W1 | Generate image/video ad assets | creative services |
| `mos.ads.run_paid_ads_qa` | R0 | Check policy/compliance issues | `paid_ads_qa.py` |
| `mos.ads.plan_meta_management` | R0 | Build management plan | `meta_media_buying.py` |
| `mos.ads.publish_meta` | W3 | Launch/publish to Meta | Meta routes/services |

### Layer G: Publishing And Commerce Tools

These tools must be highly gated.

| Tool | Class | Purpose | Backing mOS primitive |
| --- | --- | --- | --- |
| `mos.publish.validate_funnel` | R0 | Validate funnel is ready | current publish tools |
| `mos.publish.execute_funnel` | W3 | Publish funnel | `services/funnels.py` |
| `mos.publish.prepare_deploy_plan` | W2 | Build deploy plan only | `services/deploy.py` |
| `mos.publish.execute_deploy` | W3 | Execute deploy job | `services/deploy.py` |
| `mos.commerce.create_checkout_preview` | R0 | Produce checkout preview or URL | commerce providers |

## Reusing Existing In-House Tools

The current `BaseTool` pattern is worth preserving.

Recommendation:

- refactor the current `BaseTool` implementations behind a shared tool registry
- keep `ArgsModel` and `ToolResult` as the internal contract
- add one adapter that exposes registry tools through the in-house runtime
- add one adapter that exposes the same registry tools through MCP for Hermes

That lets us write tool logic once and expose it to multiple runtimes.

## Hermes Profile Toolsets

### `copy` Profile

Allow:

- platform primitives
- context/retrieval tools
- copy tools
- selected surface generation tools
- mirrored memory tools

Block by default:

- deploy execution
- Meta publish
- unrestricted filesystem
- unrestricted terminal

### `offer` Profile

Allow:

- platform primitives
- context/retrieval tools
- offer tools
- mirrored memory tools

Block by default:

- deploy execution
- publish tools
- general terminal

### `author` Profile

Allow:

- platform primitives
- context/retrieval tools
- copy tools
- ads tools
- selected browse/search tools

Block by default:

- publish/deploy actuation

### `general` Profile

Allow:

- platform primitives
- context/retrieval tools
- selected domain tools as enabled by workspace policy

The `general` profile should be assembled from tool policies, not given blanket access.

## Runtime Policy

### Models

mOS owns model policy.

Required fields per thread/run:

- `provider`
- `model`
- `reasoning_mode`
- `temperature`
- `max_tokens`
- `allowed_fallback_models` default empty

Rules:

- default fallback list is empty
- if a fallback is configured, it must be explicit and visible in logs
- model changes between turns in the same thread require an explicit operator action

### Interrupts

If the human sends a new message while Hermes is running:

- Hermes run is interrupted
- partial draft artifacts remain draft-only
- thread state returns to `awaiting_human`
- new turn starts with latest draft references attached

### Long-Running Jobs

Hermes should not directly hold long external workflows open where possible.

Instead:

- Hermes starts async work via `mos.job.start`
- Hermes polls `mos.job.status`
- mOS persists progress and results

This is important for:

- site imports
- large image batches
- campaign funnel generation
- Meta publish flows

## Proposed New mOS Modules

Recommended new package layout:

```text
mos/backend/app/agent_platform/
  __init__.py
  registry.py
  tool_contracts.py
  tool_policies.py
  mcp_server.py
  context_bundle.py
  memory_sync.py
  profiles.py
  runtime_bindings.py
  threads.py
  approvals.py
  jobs.py
  tools/
    platform.py
    context.py
    offer.py
    copy.py
    surface.py
    ads.py
    publish.py
  adapters/
    hermes.py
    inhouse_runtime.py
```

Supporting routers:

```text
mos/backend/app/routers/agent_threads.py
mos/backend/app/routers/agent_memory.py
mos/backend/app/routers/agent_profiles.py
mos/backend/app/routers/agent_runtime.py
```

## Build Plan

### Phase 0: Spike

Goal:

- prove that a Hermes sidecar can attach to an mOS MCP server and drive a single scoped thread

Deliverables:

- one `copy` profile
- one thread type
- one small MCP toolset:
  - `mos.thread.get`
  - `mos.context.bundle`
  - `mos.artifact.save_draft`
  - `mos.artifact.promote`
  - `mos.memory.search`
  - `mos.memory.write_candidate`

Success criteria:

- user can chat with Hermes-backed copy agent
- agent can draft, revise, and finalize one copy artifact

### Phase 1: Platform Foundation

Goal:

- introduce threads, memory, approvals, runtime binding, and shared tool registry

Deliverables:

- new tables and repos
- MCP server
- tool registry
- thread/message APIs
- memory candidate and approval flows
- Hermes home lifecycle manager

### Phase 2: Copy Agent

Goal:

- make copy refinement fully chat-first

Deliverables:

- `copy` profile
- copy toolset
- canonical copy artifact promotion
- template payload generation
- page/site generation handoff

Success criteria:

- finalized copy can generate:
  - funnel pages
  - Shopify theme copy
  - surface-specific variants

### Phase 3: Offer Agent

Goal:

- move offer refinement into persistent Hermes-backed thread

Deliverables:

- `offer` profile
- offer toolset
- canonical Stage 3 and offer artifact promotion
- copy-context emission for copy agent handoff

Success criteria:

- finalized offer immediately becomes consumable by copy agent and campaign context loaders

### Phase 4: Cross-Agent Memory Bundles

Goal:

- allow one agent’s finalized learnings to help another agent

Deliverables:

- memory bundle export/import
- shared workspace memory policy
- explicit promotion of approved learnings from copy -> author, offer -> copy, copy -> ads

Success criteria:

- author agent can reuse approved copy learnings without reading the entire old thread

### Phase 5: Broader Agent Fleet

Add:

- `author`
- `media_buyer`
- future operations agents

All should reuse the same toolkit and thread/memory primitives.

## Acceptance Criteria

We should not call this complete until all of these are true:

1. Hermes-backed `copy` and `offer` threads work end-to-end in chat.
2. Native Hermes memory is isolated per workspace/profile.
3. Approved mirrored memory exists in mOS and can be queried independently of Hermes.
4. Finalization promotes canonical artifacts without manual copy/paste.
5. Copy outputs can drive page/site/ad surface generation through tools.
6. Tool writes are classified, audited, and approval-gated.
7. No silent model fallback occurs.
8. Existing downstream contracts remain valid.
9. The toolkit can be consumed by Hermes and by the in-house runtime from the same contract layer.

## Open Questions To Resolve Early

1. Do we want one Hermes process per active thread, or pooled Hermes workers keyed by instance scope?
2. Do we expose all tools over MCP, or keep some high-risk tools internal-only and brokered through mOS APIs?
3. How aggressively should we mirror Hermes memory into mOS?
4. Should cross-agent memory sharing be opt-in per workspace, per product, or per promoted memory bundle?
5. Do we want a neutral `general` profile first, or ship `copy` and `offer` first and add `general` later?

## Recommended Immediate Next Step

Build Phase 0 first.

Specifically:

1. create the thread and runtime binding tables
2. create the MCP bridge and minimal tool registry
3. stand up one scoped `copy` Hermes instance
4. prove draft -> revise -> finalize -> page generation

If that works cleanly, the rest of the platform follows naturally from the same toolkit.

## External References

- Hermes Agent repository: <https://github.com/NousResearch/hermes-agent>
- Hermes sessions: <https://hermes-agent.nousresearch.com/docs/user-guide/sessions/>
- Hermes memory: <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/>
- Hermes personality / `SOUL.md`: <https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/>
- Hermes tools and toolsets: <https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/>
- Hermes skills: <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/>
- Hermes MCP: <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/>
- Hermes architecture: <https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/>
