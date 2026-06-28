# Swipe Ad Strategic Congruence Audit Scope

## Decision

Build a first-class pre-render audit for swipe-remixed ads.

The repo has strategic source material and an asset brief, but it does not currently have a system that proves the remixed ad is congruent with the source swipe, the intended lane, the awareness level, fear/risk positioning, the internal brief, and the downstream page before sending the image prompt to the renderer.

This should be a blocking audit between stage-1 prompt generation and final image rendering. If required strategic inputs are missing or the prompt fails congruence, the workflow should stop with a clean, specific error instead of rendering.

## Current State Audit

### What Exists

1. Swipe image generation has a clear two-model pipeline.
   - `mos/backend/app/temporal/activities/swipe_image_ad_activities.py`
   - Current flow: Gemini writes the generation-ready image prompt, MOS extracts the fenced prompt, then sends that prompt to the image renderer.
   - Code reference: `generate_swipe_image_ad_activity` documents this as stage 1 prompt generation followed directly by stage 2 render.

2. Asset briefs exist, but they are thin.
   - `mos/backend/app/schemas/asset_brief.py`
   - `AssetRequirement` has `channel`, `format`, `angle`, `hook`, `funnelStage`, `destinationType`, and `destinationLabel`.
   - `AssetBrief` has `creativeConcept`, `requirements`, `constraints`, `toneGuidelines`, and `visualGuidelines`.
   - This is a useful brief, but it is not a full ad-strategy audit contract.

3. Swipe stage-1 prompt generation loads a lot of strategic context.
   - `swipe_stage1_client_canon`
   - `swipe_stage1_campaign_strategy_sheet`
   - `swipe_stage1_campaign_experiment_spec`
   - `swipe_stage1_campaign_asset_brief`
   - `swipe_stage1_strategy_v2_stage0/1/2/3`
   - `swipe_stage1_strategy_v2_awareness_angle_matrix`
   - `swipe_stage1_strategy_v2_offer`
   - `swipe_stage1_strategy_v2_copy_context`
   - `swipe_stage1_strategy_v2_copy`

4. Strategy V2 has the raw ingredients for some of the requested variables.
   - `ProductBriefStage3.awareness_level_primary` supports awareness level.
   - `AwarenessAngleMatrix` supports per-awareness framing, including `problem_aware.frame`, `headline_direction`, `entry_emotion`, and `exit_belief`.
   - VOC rows include `fear_risk`.

5. Existing prompt instructions emphasize visual preservation.
   - `mos/backend/app/prompts/swipe/swipe_to_image_ad.md`
   - The prompt has strong rules for preserving source swipe design DNA, native UI chrome, spatial fidelity, text zones, and prompt formatting.

6. Paid ads QA exists, but it is not this.
   - `docs/meta-paid-ads-qa-checks.md`
   - `mos/backend/app/services/paid_ads_qa.py`
   - That subsystem is a pre-publish Meta checklist and policy/readiness audit. It does not review source swipe congruence, lane fit, awareness-level fit, fear positioning, or stage-1 prompt quality before image rendering.

### What Does Not Exist

1. No pre-render audit runs after Gemini produces the prompt and before `create_image_ads`.
2. No persisted audit artifact records why a remixed ad prompt passed or failed strategic congruence.
3. No structured comparison exists between:
   - source swipe strategy
   - generated image prompt
   - asset brief requirement
   - Strategy V2 awareness matrix
   - fear/risk positioning
   - destination page logic
4. No explicit "lane" contract is enforced for remix generation.
5. No blocker exists for a prompt that is visually faithful but strategically wrong.

## Target System

Add a `SwipeAdStrategicAudit` step that evaluates the stage-1 output before render.

Target flow:

```text
Resolve asset brief + requirement
Resolve source swipe image
Resolve strategic context bundle
Generate stage-1 image prompt
Run strategic congruence audit
If pass: send prompt to image renderer
If fail: stop with audit findings
Persist audit result on generated asset metadata or workflow artifacts
```

## Audit Inputs

The audit should receive a deterministic bundle, not rely on implicit Gemini File Search behavior alone.

Required inputs:

1. Source swipe
   - image bytes or URL
   - `company_swipe_id` when available
   - source label and SHA256
   - any available swipe taxonomy: `funnel_stage`, `angle_family`, teardown, hook, proof, CTA, visible text

2. Generated stage-1 output
   - raw Gemini markdown
   - extracted image prompt
   - placeholder inlining map
   - prompt template SHA
   - prompt model used

3. Internal brief snapshot
   - `assetBriefId`
   - requirement index
   - channel, format, angle, hook, funnel stage, destination type
   - creative concept
   - constraints, tone guidelines, visual guidelines

4. Strategic logic snapshot
   - Strategy V2 stage3
   - awareness angle matrix row for the active angle and target awareness level
   - offer
   - copy context
   - approved copy where available
   - campaign strategy sheet and experiment spec

5. Destination continuity snapshot
   - destination type
   - resolved destination URL
   - relevant presell or sales page copy artifact

## Audit Criteria

The v1 audit should return structured findings for these checks:

1. Brief completeness
   - Required fields are present: angle, hook, funnel stage or destination type, awareness level, offer, and destination anchor.
   - Missing fields are blocking findings, not guessed values.

2. Lane fit
   - The ad prompt stays in the intended lane.
   - Proposed initial lane fields: `channel`, `format`, `funnelStage`, `destinationType`, `angle`, `angle_family`, `awareness_level`, and `creativeConcept`.
   - Open issue: "lane" needs a team-owned taxonomy if it means more than the fields above.

3. Problem-aware fit
   - If the active awareness level is Problem-Aware, the prompt should name or dramatize the problem state before selling the product.
   - It should avoid Most-Aware or Product-Aware behavior unless the brief says that is the target.

4. Fear/risk positioning
   - The prompt should reflect the approved `fear_risk` or entry emotion where relevant.
   - It should not invent a different fear, intensify beyond the approved strategic ceiling, or remove fear/risk when that is the intended driver.

5. Angle and hook match
   - The prompt should preserve the strategic promise behind the requirement angle and hook.
   - The wording does not need to repeat internal labels, but the generated ad must make the same reader-facing argument.

6. Source swipe congruence
   - The prompt preserves the source swipe's visible design structure, hierarchy, proof devices, CTA logic, and native UI shell when present.
   - It should separate "keep" design DNA from "swap" brand/product/copy changes.

7. Destination continuity
   - The ad does not over-reveal downstream narrative devices.
   - The promise, curiosity gap, and offer path should make sense for the selected destination page.

8. Offer and claim grounding
   - Product, price, guarantee, proof, ingredients, certifications, and claims must come from approved artifacts or visible source/product references.
   - Unknowns should produce findings rather than invented details.

9. Render readiness
   - The final image prompt has no unresolved placeholders.
   - Required typography zones are concrete.
   - Aspect ratio and framing match the source swipe and requested output.

## Output Contract

Create a Pydantic schema similar to:

```python
class SwipeAdStrategicAuditFinding(BaseModel):
    id: str
    severity: Literal["blocker", "high", "medium", "low"]
    status: Literal["failed", "passed", "needs_review"]
    dimension: str
    title: str
    message: str
    evidence: dict[str, Any] = {}
    source_refs: list[str] = []

class SwipeAdStrategicAuditResult(BaseModel):
    version: Literal["swipe_ad_strategic_audit_v1"]
    status: Literal["passed", "failed", "needs_review"]
    score: int
    asset_brief_id: str
    requirement_index: int
    company_swipe_id: str | None = None
    swipe_source_url: str | None = None
    target_lane: dict[str, Any]
    strategic_snapshot: dict[str, Any]
    findings: list[SwipeAdStrategicAuditFinding]
```

Status rules:

1. `failed`: any blocker finding exists.
2. `needs_review`: no blocker exists, but at least one high-severity uncertainty exists.
3. `passed`: no blocker and no high-severity uncertainty.

For automated generation, v1 should render only when status is `passed`.

## Implementation Plan

### Phase 1: Audit Service And Contract

1. Add schemas:
   - `mos/backend/app/schemas/swipe_ad_strategic_audit.py`

2. Add service:
   - `mos/backend/app/services/swipe_ad_strategic_audit.py`

3. Build deterministic context assembly:
   - Reuse the same artifact resolution already used by swipe stage-1 RAG.
   - Extract a compact `target_lane` from asset brief, Strategy V2 stage3, awareness matrix, and swipe taxonomy.
   - Error if required values are missing.

4. Add an audit prompt only if rule-based checks are insufficient.
   - Use the same approved stage-1 text model unless a different model is explicitly authorized.
   - The audit should output strict JSON only.
   - The audit should not rewrite the image prompt in v1.

### Phase 2: Workflow Gate

1. Insert audit after:
   - `extract_new_image_prompt_from_markdown`
   - `inline_swipe_render_placeholders`

2. Insert audit before:
   - `CreativeServiceImageAdsCreateIn`
   - `render_client.create_image_ads`

3. If audit fails:
   - Raise a clear `RuntimeError` with blocker IDs and short messages.
   - Log the full audit result to workflow activity output or an artifact before stopping.

4. Include audit metadata in generated asset metadata when passed:
   - audit status
   - score
   - finding summary
   - audit artifact id if persisted

### Phase 3: Persistence

Preferred: add a new artifact type:

```text
swipe_ad_strategic_audit
```

Store:

1. audit input snapshot hashes
2. target lane
3. strategic snapshot
4. audit result
5. prompt SHA and source swipe SHA

Reason: `qa_report` is too generic and paid ads QA tables are campaign/publish-oriented, not prompt/remix-oriented.

### Phase 4: UI Surface

Add a compact audit summary to:

1. workflow detail activity output
2. generated asset detail metadata
3. campaign creative review panel

Operator-facing fields:

1. status
2. score
3. target lane
4. top blocker findings
5. source refs
6. prompt excerpt

### Phase 5: Tests

Add tests for:

1. Missing awareness/angle/fear positioning fails with a clean error.
2. Problem-Aware brief rejects Product-Aware prompt behavior.
3. Prompt that changes the source swipe proof device fails.
4. Prompt that preserves design DNA and matches target lane passes.
5. Workflow does not call `create_image_ads` when audit fails.
6. Workflow includes audit summary in metadata when audit passes.

Likely test files:

1. `mos/backend/tests/test_swipe_ad_strategic_audit.py`
2. `mos/backend/tests/test_swipe_image_ad_workflow_contract.py`
3. `mos/backend/tests/test_swipe_image_ad_file_search.py`

## Acceptance Criteria

1. Every workspace-mode swipe image ad run produces a strategic audit result before rendering.
2. The image renderer is never called when the audit status is `failed` or `needs_review`.
3. Failed runs explain exactly which strategic dimensions failed.
4. Audit result includes the source swipe, target lane, awareness-level basis, fear/risk basis, asset brief basis, and destination basis.
5. The audit uses approved product/campaign artifacts and does not invent missing strategic context.
6. Generated asset metadata links back to the audit result when rendering succeeds.

## Open Questions

1. What is the canonical lane taxonomy?
   - Candidate v1: `channel`, `format`, `funnelStage`, `destinationType`, `angle`, `angle_family`, `awareness_level`, `creativeConcept`.

2. Should `fear_risk` be the canonical "Fear positioning" field?
   - Strategy V2 already emits `fear_risk` in VOC-derived rows, but the active ad-level brief does not expose a dedicated `fearPositioning` field.

3. Should the audit require a source swipe teardown?
   - If yes, source swipes without teardowns should fail before remix.
   - If no, the audit can derive source-swipe observations from the image, but that is less auditable.

4. Should `needs_review` stop rendering in all automated flows?
   - Recommended v1 answer: yes. Only `passed` renders.

## Recommended Next Step

Implement Phase 1 and Phase 2 first. That creates the actual quality gate with minimal UI work, and it directly addresses the cost issue by stopping low-congruence prompts before the image model is called.
