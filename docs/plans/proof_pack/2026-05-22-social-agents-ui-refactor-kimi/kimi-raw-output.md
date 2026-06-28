 ## Decision

Rebuild the Social Agents page as an operator workbench with a clear pipeline mental model: **Configure → Generate → Validate → Handoff**. Reduce visual noise by replacing card stacks with a single scrollable canvas and a pinned right context panel. Unify the TikTok Carousel tab as the primary workflow and demote Connected Social / Action Queue to secondary overlays accessible via the top strip callouts.

## Diagnosis

- **Hierarchy collapse**: four bordered form sections (Program, Conversion Source, Experiment, Handoff) compete for attention without indicating sequence.
- **Container overload**: every subsection is wrapped in independent cards, creating a table-within-form aesthetic that fractures operator focus.
- **Preview poverty**: gradient placeholders fail to communicate the six-slide Larry-style output; operators cannot validate media readiness before handoff.
- **Disconnected states**: sidebar "Selected Loop" and "Latest Variant" duplicate context that should live adjacent to the actions that mutate them.
- **Tab silos**: Action Queue hiding in a separate tab breaks the approval→handoff causal chain; operators lose queue awareness while creating variants.

## Target IA

**Workbench layout** replaces the current two-column left stack.

- **Top rail**: Persistent execution header with Postiz link + three live badges ( readiness, pending proposals, growth loops). Badges for Connected Social and Action Queue open drawered overlays instead of tabs.
- **Main stage** (left 60%): Vertical step rail with numbered stages: 1 Program, 2 Conversion Source, 3 Experiment & Variant, 4 Postiz Handoff. Stages unlock progressively based on backend state.
- **Context panel** (right 40%): Sticky preview pane showing Selected Loop metadata and a six-slide carousel preview with real thumbnails when media URLs exist.
- **Queue drawer**: Slides in from the right when the pending-proposals badge is clicked; approvals surface inline without leaving the TikTok workflow.

## Component Split

| Component | Responsibility |
|---|---|
| `SocialWorkbench` | Orchestrates stage state, query loop/variant data, manages drawer flags. |
| `StageRail` | Renders 1–4 vertical steps; handles disabled/enabled states and completion badges. |
| `ProgramStage` / `ConversionStage` / `ExperimentStage` / `HandoffStage` | Isolated form payloads; each emits `onComplete` to advance the rail. |
| `VariantPreview` | Accepts `mediaUrls[]` and `slideCount`; renders swipeable six-slide Larry preview; shows placeholder skeletons until URLs populate. |
| `LoopContextPanel` | Read-only Selected Loop + Latest Variant metadata; docks beside StageRail. |
| `ProposalQueueDrawer` | Overlay approval table for pending proposals; emits `onApprove` to refresh parent readiness state. |
| `ConnectedSocialDrawer` | Overlay provider asset table; non-blocking reference. |

## Phases

1. **Structure**: Replace tab shell with Workbench + StageRail; move Connected Social and Queue into drawer triggers on the top rail.
2. **Preview**: Replace gradient placeholders with `VariantPreview`; wire media URL polling against existing variant endpoint.
3. **Validation**: Lock Handoff stage until `approved === true && mediaUrls.length === slideCount`; surface blocking reasons inline.
4. **Polish**: Remove nested card borders, adopt subtle section dividers, normalize spacing constants.

## Acceptance

- Operator can create a program through Stage 1 without scrolling horizontally.
- Variant generation in Stage 3 immediately reflects in `VariantPreview` as URLs arrive; placeholders resolve to slides.
- Handoff button is clearly disabled with explicit tooltip until approval and media parity conditions are met.
- Approving a proposal from the Queue drawer updates the top-rail pending-proposals badge and unlocks Handoff within the same session.
- Postiz link and system-of-record flag remain untouched in API contracts.

## Tests

- Verify stage progression locks and unlocks against mock states (program missing → Stage 2–4 disabled; variant unapproved → Handoff disabled).
- Assert `VariantPreview` renders exactly six slides from `basePrompt` + `---` split overlay text; assert skeleton-to-thumbnail transition when media count matches `slideCount`.
- Confirm drawer open/close on queue badge click does not unmount StageRail state.
- Check that Postiz proposal creation payload retains `postizSystemOfRecord: true`.

## Risks

- **Backend coupling**: If media URL availability is not event-driven, polling `VariantPreview` may feel sluggish; confirm webhook or existing polling interval before commit.
- **Drawer overflow**: Queue approval table inside a drawer may truncate on small viewports; reserve min-width constraint or fallback to modal.
- **State lift complexity**: Moving queue state from dedicated tab to drawer requires parent-level invalidation of proposal counts; ensure cache keys align.

## Non-goals

- No changes to LLM prompt construction, slide generation logic, or overlay `---` parsing.
- No new AI models or fallback image generation.
- No alteration to Postiz API contracts or proposal schema beyond UI-layer payload assembly.
- No addition of publish-to-Postiz direct action; handoff remains proposal-only.
- No redesign of Connected Social provider ingestion; table moves to drawer, behavior preserved.
