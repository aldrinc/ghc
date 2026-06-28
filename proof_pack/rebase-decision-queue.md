# Rebase Decision Queue

## State

- Branch: `codex/paid-ads-qa-full-page-snapshot`
- Position after rebase: `0 ahead / 0 behind` versus `origin/main`
- Unmerged files: `0`
- Current tracked changes: `27 files`
- Current untracked entries: `1649`
- Code stash retained: `stash@{1}` (`codex-code-only-before-main-rebase-2026-05-20`)
- Overwrite-blocker stash retained: `stash@{0}` (`codex-untracked-overwrite-blockers-before-main-rebase-2026-05-20`)

## Commit Candidates

### 1. Site Funnel Variants

Current worktree. Highest-confidence code slice.

- Adds site funnel step options, paths, path steps, campaign funnel attachment models.
- Adds site funnel APIs and frontend controls.
- Adds publication snapshot support for funnel variants.
- Needs Alembic migration included from untracked `mos/backend/alembic/versions/0087_site_funnel_variants.py`.

Validation:

- `pytest mos/backend/tests/test_funnels.py mos/backend/tests/test_sites_api.py`
- frontend typecheck or targeted site-funnel tests if available.

### 2. Campaign Funnel Page Specs + Hermes State DB Capture

Current worktree.

- Adds explicit page specs to campaign funnel generation.
- Adds Hermes state DB response/usage capture.
- Updates tests around funnel generation and Hermes sidecar.

Validation:

- `pytest mos/backend/tests/test_hermes_sidecar.py mos/backend/tests/test_funnels.py`

### 3. Imported Navigation + Meta Event Mapping

Current worktree.

- Improves imported global navigation text/button slot handling.
- Extends Meta funnel event mapping.

Validation:

- frontend tests for imported navigation and Meta event mapping.

### 4. Docs / Operator Notes

Current worktree plus untracked doc.

- `docs/systems.md` now references `docs/landing-page-image-generation-operator-flow.md`.
- `agents.md` changed standing repo instructions.

Decision:

- Keep only if these instruction changes are intentional.
- `agents.md` should be reviewed carefully because it changes agent behavior.

### 5. Tenor Import Adapter

Untracked code.

- `mos/backend/app/services/tenor_import_adapter.py`
- `mos/backend/scripts/load_tenor_creative_context.py`
- `mos/backend/tests/test_tenor_import_adapter.py`

Decision:

- Separate commit if Tenor manual creative-context import is still wanted.

### 6. GetHookd Defaults Migration

Untracked code.

- `mos/backend/alembic/versions/0085_gethookd_sync_docs_alignment.py`

Decision:

- Include only if current main still needs the DB default/credits migration. Most GetHookd app code appears already merged into `main`.

### 7. Meta Management Report Migration

Untracked code.

- `mos/backend/alembic/versions/0086_meta_management_report_artifact.py`

Decision:

- Include only if current main lacks this migration. The report service itself is already present in `main` and matches the stash version.

## Protected In Stash

These conflicted with newer `main`, so I kept rebased `HEAD` in the worktree and left the local versions in `stash@{1}` for slice-by-slice review:

- Meta publish / management / change-plan files.
- Paid ads QA files.
- Meta frontend publish components and `types/meta.ts`.
- Config/env/model-default edits.
- Campaign delivery and campaign router overlap.
- Swipes router overlap.

Important decision:

- The `gpt-5.4` model default changes are not applied. They conflicted and were left out because repo instructions say not to change AI models without explicit authorization.

## Artifact Handling

- `.local/` is now ignored by `main`.
- `outputs/` is still unignored and accounts for most remaining untracked entries.
- `mos/backend/marketi.db` and root `marketi.db` remain local DB artifacts; do not commit.
- Campaign-forensics exports need provenance review before promotion.
