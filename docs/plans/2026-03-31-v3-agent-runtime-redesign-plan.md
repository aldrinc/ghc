# V3 Agent Runtime Redesign Plan

**Date:** 2026-03-31
**Status:** Draft for architecture review

## Decision

Build V3 around an **mOS-native control plane** with **runtime adapters**, not around Hermes as the primary sidecar runtime.

The recommended shape is:

- mOS remains the single source of truth for threads, runs, artifacts, approvals, skill bundles, model policy, and telemetry.
- Skills are stored as **immutable, versioned mOS bundles** with explicit roles and runtime projections.
- Hermes is optional as an **execution adapter** for interactive sessions after the mOS contracts are stable.
- The current Claude-home export shape in `mos_strategy_v3` should **not** become the production runtime contract.

This is the cleanest way to get adequate agents with adequate skills in a runtime that is trackable, debuggable, and production-safe.

## Oracle Validation

I ran Oracle via `@steipete/oracle` against the Hermes plan, the EMBER refactor docs, the current runtime code, and the EMBER example bundle.

What happened:

- Initial session `v3-agent-runtime-redesign` failed on browser auth because no ChatGPT cookies were available.
- After browser login, I retried as session `v3-agent-runtime-redesign-2`.
- That retry completed in ChatGPT Pro and produced a full architecture recommendation.
- Oracle's CLI still did **not** harvest a final markdown output file, so I retrieved the finished answer directly from the live ChatGPT conversation.

What Pro materially confirmed:

- V3 should be **mOS-orchestrated, runtime-pluggable, and artifact-first**.
- Hermes should stay an **optional runtime adapter**, not the primary V3 control plane.
- The raw `mos_strategy_v3` export is a **developer workstation bundle**, not a production runtime package.
- The system must distinguish:
  - approved skill/business artifacts
  - runtime packages and overlays
  - runtime projections
- Bundle validation is mandatory because the current EMBER example already contains cross-artifact inconsistencies.
- Page-agent sessions and explicit page context bindings are the right direction.
- The real UX is conversational and approval-gated: the user chats with a skill-loaded agent, reviews drafts in-thread, and only then approves final output.

What I did **not** carry forward unmodified:

- Pro repeated one stale technical-PRD assumption that `instantiate_template(...)` seeds pages with empty `{}` `puck_data`.
- Live `marketi` code in `site_templates.py` actually deep-copies real template puck data into initial draft and approved versions.

This plan is therefore based on:

- verified local code and docs in `marketi`
- verified local code and docs in `mos_strategy_v3`
- the completed Oracle Pro review
- local code re-validation where the Pro answer relied on stale technical-PRD assumptions

The recommendation below is my synthesis after reconciling the Pro feedback with live code.

## Inputs Reviewed

Primary `marketi` inputs:

- `docs/plans/2026-03-24-hermes-sidecar-agent-platform-plan.md`
- `mos/backend/app/agent/runtime.py`
- `mos/backend/app/agent/types.py`
- `mos/backend/app/services/campaign_creative_context.py`
- `mos/backend/app/schemas/campaign_creative_context.py`
- `mos/backend/app/services/ember_import_adapter.py`
- `mos/backend/app/services/site_templates.py`
- `mos/backend/app/db/models.py`
- `docs/funnel-ai-agent.md`
- `docs/langfuse-observability.md`
- `docs/mos-telemetry-spec.md`

Primary `mos_strategy_v3` inputs:

- `MOS_EMBER_SKILLS_REFACTOR_PRD.md`
- `MOS_EMBER_SKILLS_REFACTOR_TECHNICAL_PRD.md`
- `EMBER_TO_MARKETI_MAPPING.md`
- `SETUP.md`
- `settings.json`
- `CLAUDE.md`
- `memory/MEMORY.md`
- `skills/FutrGroup_pipeline-orchestrator/SKILL.md`
- `skills/FutrGroup_copy-forge/SKILL.md`
- `skills/FutrGroup_offer-architect/SKILL.md`
- `FutrGroup-Hookd-Project/EMBER/EMBER-KNOWLEDGE-BASE.md`
- `FutrGroup-Hookd-Project/EMBER/cso/EMBER-CSO.md`
- `FutrGroup-Hookd-Project/EMBER/offer/EMBER-OFFER-DOCUMENT.json`
- `FutrGroup-Hookd-Project/EMBER/pages/EMBER-PRESALE-ADVERTORIAL.md`
- `FutrGroup-Hookd-Project/EMBER/pages/EMBER-SALES-PAGE.md`

## Assessment: Hermes Sidecar Plan

### What is strong

- The plan gets the most important boundary right: mOS should stay canonical for tools, artifacts, approvals, and downstream contracts.
- The plan correctly treats Hermes as a runtime candidate, not the business system of record.
- The MCP boundary is directionally correct. Tool execution should sit behind a runtime-agnostic contract.
- The plan is right to require scoped runtime homes and mirrored memory instead of letting runtime-local memory become canonical.
- The plan is right to insist on no silent model switching and explicit auditability.

### What is risky

- It still gives too much conceptual weight to Hermes-owned session state, local memory, and local skills.
- In production, a second mutable control plane is expensive:
  - Hermes session store
  - Hermes home files
  - Hermes config
  - Hermes toolset discovery state
  - mOS artifacts and approvals
- That split makes replay, audit, and debugging materially harder.
- If Hermes homes remain writable and long-lived, runtime behavior becomes partly filesystem state, not only database state.
- If tool availability is discovered at Hermes startup, runtime behavior can drift without a corresponding mOS release event.

### What is missing

- A canonical thread and run model in mOS that fully outlives Hermes.
- A replay contract:
  - exact prompt bundle
  - exact skill bundle release
  - exact tool registry version
  - exact model policy
  - exact runtime adapter version
- A hard rule for runtime mutability:
  - can runtime modify skills?
  - can runtime write memory locally?
  - can runtime change toolsets at runtime?
- A clean rule for high-risk tools. Not every mOS capability should be exposed directly over MCP.
- A production posture for runtime isolation, quotas, cancellation, and failure recovery.

### Production judgment

Hermes is acceptable as an **optional execution adapter**.

Hermes is not a good choice for the **primary production control plane**.

## Assessment: EMBER Skills Refactor

### What is strong

- The compatibility-first approach is right.
- A first-class `skills` creative-context provider is directionally correct.
- Preserving the normalized `campaign_creative_context` seam is the correct migration move.
- The proposed page-agent session idea is correct. Page-level AI actions need a durable audit object, not loose `ai_metadata`.
- The conversational, human-gated workflow is also directionally correct:
  - the orchestrator model pauses at human gates
  - headline selection is intended to happen in chat before downstream writing
  - page-agent work is supposed to produce drafts for review, not auto-finalized output
- The actual EMBER artifact family is good as an approved handoff example:
  - knowledge base
  - signal report
  - CSO
  - offer document
  - headlines
  - presell page
  - sales page

### What is overfit or under-specified

- The refactor conflates three separate concerns:
  - approved business artifacts
  - runtime skill packages and overlays
  - developer environment export
- The PRD and technical PRD still conflict on downstream compatibility:
  - the product direction says `skills` should remain semantically separate from `manual`
  - the technical PRD still proposes writing `campaign_loaded_*` artifacts on skills activation
- The refactor under-specifies the most important safety layer:
  - bundle validation before activation
  - explicit experiment-spec linkage
  - clean failure on missing or contradictory required roles
- The current `ember_import_adapter.py` is a one-off translator, not a general skills importer:
  - it hardcodes EMBER-specific description and core promise text
  - it fabricates experiment specs by default
  - it encodes bundle assumptions directly in code
- The runtime-export concept is still effectively a portable Claude home, not a production bundle contract.

### What the current export shape proves

The current `mos_strategy_v3` export is not yet a production runtime abstraction.

It is a **Claude-oriented operator environment snapshot** built from two separate layers:

- operating layer
  - `skills/`
  - `memory/`
  - `CLAUDE.md`
  - `settings.json`
- project artifact layer
  - `FutrGroup-Hookd-Project/`
  - including the approved EMBER example assets

The export therefore mixes:

- `SETUP.md` instructs copying raw `skills/`, `commands/`, `CLAUDE.md`, `settings.json`, and `memory/` into `~/.claude`
- `settings.json` uses `defaultMode: "bypassPermissions"` and pins `model: "opus[1m]"`
- `memory/MEMORY.md` mixes user preferences, project state, and procedural notes
- `CLAUDE.md` repeats mutable preference memory
- individual skills still contain defaulting, repair, and fictionalization behavior that cannot be canonical in production

That is useful for a power-user workflow.

It is not a clean production runtime boundary.

### Concrete issues in the current skill layer

- `FutrGroup_copy-forge` contains auto-repair behavior for missing protocol, guarantee, and bundle tiers.
- `FutrGroup_copy-forge` also explicitly allows adapting VOC into fictionalized reviews when real reviews do not exist.
- `FutrGroup_offer-architect` mixes required business inputs with rigid output defaults and UX assumptions.
- `FutrGroup_pipeline-orchestrator` is a large prompt procedure, not a typed orchestration contract.
- Project memory is path-specific and runtime-specific, not product-canonical.
- The actual workflow assumes user-visible review in chat before downstream execution:
  - approved headlines are shown in-conversation first
  - downstream copy/page work consumes approved selections, not just saved files

### Bundle validation requirement

The current EMBER example already proves activation cannot be a blind "import and trust" step.

- `offer-architect` says the 60 Day Supply should be the default bundle.
- `EMBER-OFFER-DOCUMENT.json` marks 60 Day Supply as default but also badges 30 Day Supply as "default selected".
- `EMBER-SALES-PAGE.md` still contains conflicting default-bundle language in its buy blocks.

V3 therefore needs a validator layer that runs before approval and activation:

- required role presence checks
- cross-artifact consistency checks
- explicit provenance for synthesized fields
- clean hard errors instead of silent repair, fallback, or invented defaults

### Important doc drift

The technical PRD is not fully synced with current `marketi` code.

Example:

- The PRD says template-backed site pages are instantiated with empty `{}` `puck_data`.
- Current `marketi` code in `site_templates.py` actually resolves template puck data and deep-copies it into initial draft and approved versions.

That does not invalidate the refactor direction, but it does mean the PRD should not be treated as an exact implementation map without re-grounding it against live code first.

## Option Set

| Option | Summary | Pros | Cons | Verdict |
| --- | --- | --- | --- | --- |
| A. Hermes-first sidecar runtime | Hermes owns live agent loop, native skills, native memory, and local session continuity; mOS owns artifacts and tools via MCP | Faster interactive runtime, fewer in-house runtime features to build immediately | Two mutable control planes, harder replay/debug, skill and memory drift, model/tool policy conflicts | Not recommended as the primary V3 architecture |
| B. mOS-native runtime first | Expand current `AgentRuntime` into the full thread/run/session/runtime system inside mOS | Cleanest audit, single control plane, easiest production debugging | More build work up front, slower path to rich chat ergonomics | Strong option if speed is secondary to purity |
| C. mOS-native control plane with runtime adapters | mOS owns canonical contracts; Hermes or other runtimes plug in as adapters behind the same execution envelope | Best balance of control, observability, migration flexibility, and future runtime optionality | Requires disciplined adapter design and read-only runtime projections | Recommended |

## Recommended V3 Architecture

### 1. Canonical control plane in mOS

Create one canonical state plane in mOS with these first-class entities:

- `campaign_creative_context_config`
- `campaign_creative_context`
- `skill_*` artifacts and `skills_bundles`
- `agent_profiles`
- `agent_threads`
- `agent_turns`
- `agent_runs`
- `agent_run_events`
- `runtime_sessions`
- `site_page_context_bindings`
- `site_page_agent_sessions`
- `approval_items`
- `approval_resolutions`
- `agent_artifact_links`
- `approved_memory_items`
- `memory_projections`

Rules:

- A thread is the durable business conversation.
- A turn is the conversational transcript unit inside the thread.
- A run is one execution attempt within a thread.
- Events are append-only and auditable.
- Runtime-specific session ids are stored only as external references.

### 2. Skill-loaded conversational agent model

The real user interaction model is not "import a bundle and auto-finalize."

It is:

1. the user opens or continues a thread
2. mOS selects a profile such as `campaign-strategy`, `offer`, `copy`, or `page-copy`
3. mOS projects the approved skill/business context into a run-scoped runtime view
4. the agent loads that projected profile and performs the task
5. the user can chat with the agent, request revisions, and inspect drafts before approval
6. approval finalizes artifacts or page versions, but the thread remains open for further work

This matches the actual skill system better than a batch pipeline model:

- orchestrator flows pause at human gates
- headline review is intended to happen in chat before downstream writing
- page-manager flows should create draft page versions for review, not auto-publish

Approval is therefore **not** the end of the conversation.

It is the promotion step that turns a draft into canonical output.

### 3. Runtime adapters, not runtime ownership

Define a runtime adapter contract:

- `prepare_context(run_context_packet)`
- `execute(run_envelope)`
- `stream_events()`
- `cancel(run_id)`
- `collect_state(run_id)`
- `dispose(session_ref)`

Supported adapters:

- `mos_native`
- `hermes`
- later: other runtimes if needed

Critical rule:

- adapters do not own canonical state
- adapters consume a prepared execution envelope from mOS
- adapters emit structured events back into mOS

`run_context_packet` should include:

- thread and subject scope
- active creative-context provider and artifact ids
- approved skills bundle id
- runtime profile id and package release ids
- page context binding snapshot when relevant
- approved memory projection ids
- model policy
- tool snapshot
- approval policy snapshot

### 4. Separate business artifacts, runtime packages, and runtime projections

Do not make `skills/ + commands/ + CLAUDE.md + settings.json + memory/` the core object.

Use three layers:

1. **Business artifact layer**
   - approved `skill_*` artifacts and bundle selections
   - example: knowledge base, CSO, offer document, headline pool/selection, presell page, sales page

2. **Runtime package / overlay layer**
   - installable skill packages
   - command packages
   - memory projections
   - root/runtime files
   - plugin manifests
   - MCP manifests

3. **Runtime projection layer**
   - exact read-only runtime mount derived from approved artifacts plus profile policy
   - contains only the skills, overlays, identity, tool permissions, and memory seeds allowed for that run

This keeps approved business content separate from runtime packaging and from per-run execution views.

### 5. Artifact and bundle model

Keep the current downstream seam, but make upstream skills artifacts first-class.

Recommended canonical upstream roles:

- `skill_knowledge_base`
- `skill_signal_report`
- `skill_cso`
- `skill_offer_document`
- `skill_headline_pool`
- `skill_headline_selection`
- `skill_presell_page`
- `skill_sales_page`

Also keep `skills_bundle_items.role_key` so future families are extensible without redesigning the whole model.

Recommended additions:

- `campaign_creative_context_config`
- `skills_bundle`
- `skills_bundle_item`
- `site_page_context_binding`
- `site_page_agent_sessions`

Rules:

- `campaign_creative_context_config` is the provider selector
- `campaign_creative_context` remains the canonical downstream compatibility artifact
- `skill_*` artifacts are the canonical upstream skills/business layer
- derived compatibility artifacts may exist only when a real downstream consumer still requires them
- `campaign_loaded_*` should not become the canonical skills source layer

### 6. Bundle approval and validation model

The approval unit should be the bundle, not only individual files.

Activation rules:

- exactly one active approved skills bundle per campaign
- all required roles present
- linked experiment spec present when downstream readiness requires it
- normalization succeeds
- cross-artifact validation succeeds

Validation rules must fail cleanly. Do not silently:

- invent experiment specs
- repair missing offer structure
- infer contradictory defaults
- fabricate evidence or reviews

This is required both by the current EMBER inconsistencies and by the production rule that the system should error clearly instead of hiding behavior behind fallbacks.

### 7. Skill package and runtime profile model

Use immutable, versioned skill releases.

Recommended concepts:

- `skill_package`
- `skill_package_release`
- `runtime_profile`
- `runtime_profile_item`

Suggested package kinds:

- `skill`
- `command`
- `memory_projection`
- `root_file`
- `plugin_manifest`
- `mcp_manifest`

A package release should capture:

- source repo/path
- source sha
- manifest hash
- package kind
- normalized metadata
- runtime compatibility metadata
- allowed tools and required context types where applicable

A runtime profile should capture:

- exact ordered package release ids
- exact tool allowlist
- exact model policy
- exact approval thresholds
- exact runtime preference order
- exact projection rules

Start with a small fleet of stable profiles:

- `campaign-strategy`
- `offer`
- `copy`
- `page-copy`

Do not start with a broad generalist profile.

Do not allow production runtimes to mount mutable skills directly from a user home directory.

### 8. Creative-context model

Keep:

- `strategy_v2`
- `manual`

Add:

- `skills`

Resolution rule:

- `campaign_creative_context_config` chooses provider
- `campaign_creative_context` remains the normalized downstream packet

That splits provider selection from compatibility payload generation.

### 9. Memory model

Support three planes:

1. **Canonical mOS memory**
   - typed
   - approved
   - queryable
   - portable across runtimes

2. **Thread working memory**
   - run summaries
   - compressed context checkpoints
   - scoped to one thread
   - regenerated or replaced as needed

3. **Runtime-local scratch memory**
   - optional
   - disposable
   - never canonical

Rules:

- no direct runtime-local writes into canonical memory
- no attempt to mirror every local mutation in real time
- memory promotion happens through explicit summary or approval actions

### 10. Tool contract layer

All tool execution should go through one mOS registry with:

- typed args/result schemas
- tool version
- risk tier
- read/write class
- approval requirement
- idempotency policy
- timeout/cancellation policy
- audit metadata

High-risk tools should remain brokered inside mOS and not be exposed as free-form runtime calls.

Expose the registry through:

- internal Python calls
- HTTP/internal orchestration
- MCP adapter where appropriate

Also broaden `ToolContext` so it carries:

- campaign scope
- product scope
- site scope
- page scope
- thread scope
- approval scope

### 11. Page generation and page-manager model

The page layer should distinguish:

- campaign creative context
- site/page template
- page context binding
- page agent session
- execution mode

Recommended rules:

- `site_page_context_bindings` capture the selected angle, selected offer, source skills bundle, creative-context artifact, and template/page role
- `site_page_agent_sessions` should point to `agent_thread_id` plus page/version ids, not become a second conversation system
- default v1 output should be slot assignments first, bounded `puck_data` patches second
- use `skills_copy` for bounded copy generation/rewriting inside known slots or approved copy regions
- use `funnel_ai` for template-aware structural enforcement, media enrichment, testimonial tooling, and bounded page mutation

Important correction from live code:

- do **not** design the migration around the stale assumption that template-backed pages seed with empty `{}` data
- current `site_templates.py` already deep-copies real template puck data into initial draft and approved versions
- the real remaining blockers are page-context binding, provenance, conversation/session modeling, and making `template_id` the canonical routing field

### 12. Approval and finalization flow

Every conversational agent flow should follow:

1. open or continue thread
2. load approved context and runtime profile projection
3. run the agent
4. let the user chat, clarify, and request revisions
5. persist draft artifacts or draft page versions
6. create approval items where needed
7. finalize exact selected artifacts or page versions
8. emit or refresh downstream normalized projections

Runtime-produced text is not canonical until mOS finalizes the corresponding artifact.

### 13. Observability and debugging

Use one correlation model across:

- `trace_id`
- `agent_thread_id`
- `agent_run_id`
- `campaign_id`
- `page_id`
- `runtime_adapter`
- `runtime_profile_id`
- `model_policy`
- `tool_name`

Persist:

- exact run-context-packet hash
- exact artifact input ids
- exact skill bundle release ids
- exact model id
- exact memory projection ids
- exact tool calls with result digests
- runtime adapter session refs
- cancellation and retry events

Combine:

- OpenTelemetry for platform traces/logs/metrics
- Langfuse for LLM-level inspection

Provide one run viewer in mOS that reconstructs:

- what the agent saw
- what it called
- what changed
- what failed
- what was approved

## What Must Remain Canonical In mOS

- thread/turn history
- run/event history
- artifact storage and lineage
- approvals and finalization state
- skill bundle releases
- model policy
- tool registry and permissions
- page bindings and creative-context provider choice
- canonical memory
- telemetry and replay metadata

## What May Live In A Runtime Home

- ephemeral cache
- provider-specific session ids
- temporary scratch files
- optional local memory summaries
- prompt assembly intermediates

Rules:

- runtime home contents are disposable
- runtime home contents are not the system of record
- runtime home contents must be reproducible from mOS inputs plus adapter version where possible

## Migration Plan

### Phase 0: Stabilize the compatibility seam

- Keep current `strategy_v2` and `manual`
- add `campaign_creative_context_config`
- formalize a generic `skills` translator contract
- keep the existing manual path as a bootstrap ingest path only
- stop silently fabricating experiment specs in the EMBER translator
- replace one-off defaults and fallback evidence with explicit required inputs and clean errors
- add bundle validators before any activation path

### Phase 1: Create the canonical agent kernel

- add threads, turns, runs, runtime sessions, events, and approvals
- extend current `AgentRuntime` into a canonical run envelope and event system
- keep existing funnel tools as-is behind the registry
- make in-thread review and revision a first-class flow before approval

### Phase 2: Create immutable skill/profile releases

- define `skill_package_releases`
- define `runtime_profiles`
- define `runtime_profile_items`
- stop treating raw Claude home exports as deployable runtime bundles
- generate read-only runtime projections from mOS releases

### Phase 3: Add the `skills` creative-context provider

- persist canonical `skill_*` artifacts and `skills_bundles`
- derive normalized compatibility artifacts from the approved active bundle
- preserve current downstream consumers unchanged where possible

### Phase 4: Add page-agent sessions

- add `sites.campaign_id`
- standardize `site_pages.template_id` as the canonical routing/template field
- create `site_page_context_bindings`
- create `site_page_agent_sessions`
- bind site, campaign, page, angle, offer, and creative context explicitly
- route bounded page generation through the shared execution layer
- keep using real template-backed `puck_data` from `site_templates.py`; do not rework this phase around the stale `{}` assumption

### Phase 5: Introduce runtime adapters

- implement `mos_native` first
- add `hermes` second behind the same contract
- if Hermes is used:
  - isolate `HERMES_HOME` per scope
  - mount read-only skill projections
  - force model policy from mOS
  - disable uncontrolled runtime mutation paths
  - treat Hermes local memory as non-canonical

### Phase 6: Production hardening

- replay support
- cancellation guarantees
- quotas
- per-profile tool policies
- alerting and run failure dashboards
- runtime adapter health monitoring

## Immediate Build Recommendations

Do first:

1. Add `campaign_creative_context_config` and a real `skills` provider path.
2. Replace the EMBER-specific importer with a generic translator plus bundle validators.
3. Make experiment specs explicit instead of synthesized-by-default.
4. Add canonical thread/turn/run/approval tables before integrating any richer external runtime.
5. Define immutable runtime profiles and profile package releases.
6. Add page context bindings and page-agent sessions.

Do not do first:

- make Hermes the primary production control plane
- turn the current Claude export layout into the production runtime contract
- collapse project artifacts, runtime overlays, and skill packages into one deployable object
- auto-finalize skill outputs without an in-thread review and approval step
- silently repair, invent, or backfill required business inputs
- rely on runtime-local memory as canonical state

## Bottom Line

The Hermes plan is directionally smart but too generous to runtime-owned state.

The EMBER refactor is directionally smart but currently bundles business artifacts, runtime packaging, and operator environment export into one concept.

V3 should be:

- **mOS-native at the control plane**
- **bundle- and artifact-driven at the business layer**
- **conversation-first and approval-gated at the agent layer**
- **adapter-based at the runtime layer**
- **Hermes-optional, not Hermes-dependent**

That gives you clean production traceability without throwing away the good parts of the current Hermes and EMBER work.
