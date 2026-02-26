# Strategy V2 Single-Screen HITL Design Outline

Date: 2026-02-25
Owner: Workflow + UI
Status: Draft

## 1. Goal
Design a single, simple review experience for Strategy V2 where:
- The workflow runs automatically between human checkpoints.
- When a checkpoint is reached, the user sees one screen.
- The screen shows only the information required to make that specific decision.
- The user completes a consistent flow: `Review -> Decide -> Attest -> Submit`.

This aligns to the existing Strategy V2 workflow gates:
- `strategy_v2_proceed_research`
- `strategy_v2_confirm_competitor_assets`
- `strategy_v2_select_angle`
- `strategy_v2_select_ump_ums`
- `strategy_v2_select_offer_winner`
- `strategy_v2_approve_final_copy`

## 2. Core UX Principles
1. One active decision at a time.
2. One page for the entire workflow run.
3. Decision packet is minimal and purpose-built for the current gate.
4. Full source files are always available in a markdown viewer, not just summaries.
5. No fallback logic in UI; if required data is missing, show a blocking error with exact missing fields.

## 3. Single-Screen Layout (Center-First)

### A. Top Bar
- Workflow status: `Running` or `Needs Review`.
- Current step label and index, for example `Step 3 of 6`.
- Last update timestamp.
- `All artifacts` button (opens optional drawer/modal, hidden by default).

### B. Step Rail (left)
- Shows all six human checkpoints.
- States: `Completed`, `Current`, `Upcoming`.
- Click on completed steps opens read-only past decision summary.

### C. Center Workspace (Primary Surface)
No default right-side artifact panel. All required review work happens in the center panel.

Center workspace has two modes:

1. `Gate Overview Mode` (default for each gate)
- `Required Files` card row at the top (one card per required file).
- `Review Checklist` card under files (gate-specific checks user must complete).
- `Decide` card (single-select, multi-select, or approve/reject).
- `Attest` card (two required checkboxes + operator note).
- `Submit` action (disabled until required review + payload validation are complete).

2. `Document Reader Mode` (opens when file card is clicked)
- Header: `Back to Gate Review`, file title, stage key, artifact id.
- Body: full markdown rendered via `MarkdownViewer` (same baseline as Documents page).
- Footer actions: `Mark reviewed`, `Next required file`.

### D. Optional Artifact Surface
- `All artifacts` opens a secondary drawer/modal for non-required artifacts.
- This surface is for exploration only and is hidden by default.
- Required decision files are always surfaced directly in the center workspace.

## 4. Decision Packet Spec (Per Gate)

| Gate | Decision Question | Show in `Review` (only what is needed) | Required Full Files in Markdown Viewer | Required Operator Review Actions | `Decide` Control | Required Payload Fields |
|---|---|---|---|---|---|---|
| `strategy_v2_proceed_research` | Is foundational research sufficient to continue? | Research completeness summary, key assumptions, known gaps/risks, competitor coverage summary | STEP1/STEP4/STEP6 full research markdown files used to derive the summary | Read each file and verify category/segment coherence, competitor coverage, VOC depth, and synthesis consistency before deciding proceed/hold | `proceed` Yes/No | `proceed`, `attestation.reviewed_evidence`, `attestation.understands_impact`, `operator_note` |
| `strategy_v2_confirm_competitor_assets` | Which competitor assets are credible enough to lock in? | Ranked candidate assets with `source_ref`, `candidate_id`, evidence count, quality/compliance indicators, candidate summary | Full competitor-asset candidate dossier markdown for each candidate selected or rejected | Open each candidate dossier under consideration, validate source references and evidence quality, then confirm 3-15 assets | Multi-select confirmed assets | `confirmed_asset_refs` (3-15 source refs), `reviewed_candidate_ids` (candidate ids), attestation, note |
| `strategy_v2_select_angle` | Which angle should drive strategy? | Ranked angle candidates, top supporting VOC evidence, contradiction and velocity indicators | Full angle synthesis markdown and observation markdown that produced ranked candidates | Review full angle docs for top contenders, validate definition completeness and supporting evidence quality, then select one | Single-select angle | `selected_angle`, `reviewed_candidate_ids`, attestation, note |
| `strategy_v2_select_ump_ums` | Which UMP/UMS pair should advance? | Ranked pairs, key dimension scores, proof linkage relevant to credibility | Full offer architecture markdown including promise contract/scoring detail for each pair | Review compared pair files, inspect seven scoring dimensions and evidence quality, then select one pair | Single-select pair | `pair_id`, `reviewed_candidate_ids`, attestation, note |
| `strategy_v2_select_offer_winner` | Which offer variant is the winner? | Variant comparison table, score breakdown by evaluation dimensions, strongest tradeoffs | Full variant evaluation markdown for base and alternatives | Review full evaluation for all presented variants, inspect value/objection/novelty and dimension tradeoffs, then select winner | Single-select variant | `variant_id`, `reviewed_candidate_ids`, attestation, note |
| `strategy_v2_approve_final_copy` | Is final copy ready for approval? | Final copy summary, quality gate results, unresolved risk/compliance flags | Full final copy markdown artifacts (headline, advertorial/presell, sales page) with quality report markdown | Read full copy files and quality report, verify unresolved risk status, then approve or reject | Approve/Reject toggle | `approved`, `reviewed_candidate_ids`, attestation, note |

## 5. Document Review and Artifact Access Rules
1. Required review files are displayed as center-panel file cards, not in a side panel.
2. Clicking a required file card enters `Document Reader Mode` in the same center workspace.
3. Full markdown uses the existing `MarkdownViewer` component (`ReactMarkdown + remark-gfm + markdown.css` styling).
4. Viewer must render full file content with no truncation and no summary-only substitute.
5. Gate 1 required foundational docs resolve by step number (`01`, `04`, `06`) including prefixed keys such as `v2-02.foundation.01`.
6. If research content is wrapped in an artifact envelope (`payload.content`), the viewer renders the actual content body directly.
7. If an expected required file is missing or fails to load, block submit and show: `Missing artifact(s): <ids/keys>`.
8. Do not route users to external links for `artifact://` references; render in-app.
9. Optional non-required artifacts are available through `All artifacts` drawer/modal (hidden by default).
10. A decision can be submitted only after all required full files for that gate are loaded and marked reviewed.

## 6. User Lifecycle: Trigger -> Review -> Completion

### A. Trigger and Notification
1. Workflow runs automatically until a human gate is reached.
2. Backend sets pending signal type and pending decision payload for the current gate.
3. UI transitions run state to `Needs Review` immediately on poll/refresh when pending gate is present.
4. Notify the assigned operator in-app with a persistent banner and task badge: `Review required: <gate name>`.
5. Optional channel notifications (email/Slack) should deep-link to the same single review screen for the workflow run.

### B. In-Review Experience
1. Screen focuses current gate and locks future gates.
2. Center panel opens `Gate Overview Mode` with required file cards and review checklist.
3. Clicking a file card opens full markdown in `Document Reader Mode`, then returns to gate overview.
4. User completes `Decide -> Attest -> Submit` after required review is complete.

### C. Submit and Resume
1. On submit success, current gate is stamped with decision receipt (who, when, what, note).
2. Workflow automatically resumes processing the next automated stage.
3. UI state returns to `Running` until the next human gate appears.

### D. End of Experience
1. Final gate (`strategy_v2_approve_final_copy`) submission closes HITL loop.
2. Workflow status becomes `Completed` after backend finalization succeeds.
3. Screen switches to completion summary: final approved artifacts, decision log, and key output links.
4. No additional review prompts are shown unless a new workflow run is started.

## 7. Validation Rules (UI Mirrors Backend)
- `attestation.reviewed_evidence` must be true.
- `attestation.understands_impact` must be true.
- `operator_note` required and must meet backend minimum length.
- `reviewed_candidate_ids` required for candidate-based gates.
- Selected id must exist in reviewed candidate set.
- Gate-specific required field must be present (`pair_id`, `variant_id`, etc.).

## 8. What This Intentionally Avoids
- No multi-page wizard for HITL.
- No generic "all-data" step screens.
- No mixed terminology from pre-canon/canon UX.
- No hidden automatic fallback decisions.

## 9. Implementation Notes (UI)
1. Keep one route: workflow detail page as the single workspace.
2. Replace generic gate renderer with six typed gate components sharing a common shell.
3. Add a gate-to-decision-packet adapter layer so each step receives only needed fields.
4. Reuse `MarkdownViewer` as the in-place full document reader for all required files.
5. Implement optional `All artifacts` drawer/modal for non-required artifacts; hidden by default.

## 10. Acceptance Criteria
1. A user can complete all six HITL gates without leaving one page.
2. At each gate, the user sees only decision-critical context plus required full markdown files in the center panel.
3. All submit actions pass backend contract validation without hidden coercion.
4. Missing required evidence/data produces explicit blocking errors.
5. Completed decisions are visible as read-only receipts in the same screen.
6. The review lifecycle is explicit: trigger, in-app notification, review mode, resume, completed end-state.

## 11. Click-by-Click User Walkthrough (Operator View)

### 11.1 Landing State (Before Any Click)
1. User opens the workflow run page.
2. Top bar shows one of two states:
   - `Running`: no action needed right now.
   - `Needs Review`: action required now.
3. If `Needs Review`, the page auto-focuses the current gate and shows a persistent banner: `Review required: <gate name>`.
4. Left rail highlights current gate, marks past gates `Completed`, and future gates `Upcoming` and locked.
5. Center panel starts in `Gate Overview Mode` and shows:
   - Required file cards with status chips (`Required`, `Not opened`, `Loaded`, `Reviewed`).
   - Review checklist with gate-specific validation tasks.
   - Decide controls, Attestation controls, Submit button.
6. No default right panel is shown. Optional `All artifacts` is hidden behind top-bar button.

### 11.2 Document Reader Mode (Shared Behavior for Every Gate)
1. User clicks a required file card in the center panel.
2. Center panel transitions to `Document Reader Mode` with:
   - Top row: `Back to Gate Review`, file title, stage key, artifact id.
   - Main body: full markdown rendered with `MarkdownViewer`.
   - Footer: `Mark reviewed`, `Next required file`.
3. Markdown appearance is identical baseline to Documents:
   - Readable content column (`max-w-[75ch]`), heading hierarchy, code blocks, tables, links, images.
   - GitHub-flavored markdown support via `remark-gfm`.
4. User scrolls and reads full content.
5. User clicks `Mark reviewed` and either:
   - Clicks `Next required file`, or
   - Clicks `Back to Gate Review`.
6. Gate card status updates to `Reviewed`; submit gating updates in real time.

### 11.3 Gate 1 Detailed Walkthrough: `strategy_v2_proceed_research`
1. Gate Overview Mode shows three required file cards:
   - `STEP1_CONTENT` (market/category/segment foundation).
   - `STEP4_CONTENT` (VOC extraction body).
   - `STEP6_CONTENT` (structured synthesis/scoring body).
2. User opens `STEP1_CONTENT` and reviews:
   - Product/category fit and primary segment consistency.
   - Competitor coverage and whether competitor set appears complete enough.
   - Any obvious contradictions or missing critical sections.
3. User returns and opens `STEP4_CONTENT` and reviews:
   - VOC category breadth and whether evidence is materially thin.
   - Quote quality and presence of contradictory signals.
   - Source grounding for major claims.
4. User returns and opens `STEP6_CONTENT` and reviews:
   - Whether synthesis logically follows from STEP1/STEP4 evidence.
   - Whether key risks and assumptions are clearly surfaced.
   - Whether any critical unknowns should block progression.
5. User returns to Gate Overview and sets decision:
   - `Proceed = Yes` if research is decision-ready.
   - `Proceed = No` if issues are blocking.
6. User checks both attestation boxes, writes operator note describing rationale, clicks submit.
7. System validates required files reviewed + payload fields, then records decision and resumes workflow.

### 11.4 Gate 2 Detailed Walkthrough: `strategy_v2_confirm_competitor_assets`
1. Gate Overview Mode shows candidate asset cards/table with evidence signals.
2. Each candidate row shows:
   - Selection checkbox bound to candidate `source_ref` (the value sent as `confirmed_asset_refs`).
   - `Open dossier` action for full candidate dossier markdown.
   - Reviewed status chip bound to candidate `candidate_id`.
3. User clicks `Open dossier`; center panel transitions to Document Reader Mode and renders full candidate dossier in markdown.
4. User reads dossier and clicks `Mark reviewed`; system records that candidate `candidate_id` in reviewed set.
5. For each candidate under consideration, user verifies:
   - Source references are concrete and relevant.
   - Evidence quantity/quality supports using this asset.
   - Compliance/risk indicators are acceptable for inclusion.
6. User returns to Gate Overview and confirms final asset set (minimum 3, maximum 15 selected source refs).
7. User attests, writes rationale note, submits.
8. System validates that every confirmed `source_ref` maps to a reviewed candidate and records the decision.

### 11.5 Gate 3 Detailed Walkthrough: `strategy_v2_select_angle`
1. Gate Overview Mode shows ranked angle cards with evidence indicators.
2. User opens full markdown for each top contender.
3. For each contender, user verifies:
   - Angle definition is complete (`who`, `pain/desire`, `mechanism`, `belief shift`, `trigger`).
   - Supporting evidence is credible and sufficiently dense.
   - Contradictions are understood and acceptable.
4. User marks reviewed candidates and returns.
5. User selects one winning angle, attests, writes note, submits.
6. System validates selected angle belongs to reviewed set and records the decision.

### 11.6 Gate 4 Detailed Walkthrough: `strategy_v2_select_ump_ums`
1. Gate Overview Mode shows ranked UMP/UMS pairs.
2. User opens full markdown for each pair being compared.
3. For each pair, user verifies score rationale across the seven dimensions:
   - `competitive_uniqueness`
   - `voc_groundedness`
   - `believability`
   - `mechanism_clarity`
   - `angle_alignment`
   - `compliance_safety`
   - `memorability`
4. User marks reviewed pairs and returns.
5. User selects one pair, attests, writes note, submits.
6. System validates selected `pair_id` is in reviewed set and records the decision.

### 11.7 Gate 5 Detailed Walkthrough: `strategy_v2_select_offer_winner`
1. Gate Overview Mode shows variant cards (`base`, `variant_a`, `variant_b`) with score summaries.
2. User opens full evaluation markdown for each variant.
3. For each variant, user reviews:
   - Core promise clarity and value stack quality.
   - Objection coverage and novelty signals.
   - Dimension score tradeoffs and risk implications.
4. User marks variants reviewed and returns.
5. User selects one winner variant, attests, writes note, submits.
6. System validates selected `variant_id` is in reviewed set and records the decision.

### 11.8 Gate 6 Detailed Walkthrough: `strategy_v2_approve_final_copy`
1. Gate Overview Mode shows required copy file cards:
   - Headline markdown.
   - Advertorial/Presell markdown.
   - Sales page markdown.
   - Quality report markdown.
2. User opens each file in Document Reader Mode and reviews:
   - Message consistency with selected angle and selected offer.
   - Presence of unresolved high-risk/compliance issues.
   - Overall readiness for approval decision.
3. User marks all required copy files reviewed.
4. User chooses `Approve` or `Reject`, then attests and writes rationale note.
5. User submits final decision.
6. System records approval decision and finalizes workflow.

### 11.9 End Screen (After Final Submit)
1. What the user sees:
   - Status badge: `Completed`.
   - Final decision log with timestamp and operator for each gate.
   - Final artifacts list with markdown viewer access.
2. What the user clicks:
   - Click any completed gate in left rail for read-only receipt.
   - Click any final artifact to re-open full markdown.
3. What happens:
   - No further decision controls are enabled.
   - No pending review banner appears.
   - Page is now an audit and output review surface.
