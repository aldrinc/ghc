# Keep Approved Main Slices

## Goal

Prepare a clean PR branch based on current `origin/main` containing only the approved local changes:

- site funnel variants/options/paths and publication snapshots
- Hermes sidecar state DB response and usage capture
- campaign funnel custom page specs
- small non-regressive checkout funnel event mapping, if clean
- authorized model standardization to `gpt-5.5` only where directly needed

## Plan

1. Create a dedicated branch from the current rebased main-equivalent HEAD.
2. Remove stale local changes not in the approved set.
3. Remove untracked junk/artifacts and explicitly dropped code: Tenor import adapter, GetHookD defaults/docs alignment, and meta management report artifact migration.
4. Keep and repair approved slices so the diff is coherent against current main.
5. Run targeted backend/frontend verification and `git diff --check`.
6. Stage only the intended PR files and leave unrelated artifacts untracked.

## Acceptance

- Branch is based on `origin/main` with zero ahead/behind before the new changes.
- No Tenor import adapter files remain in the intended diff.
- No GetHookD default/doc-alignment changes remain in the intended diff.
- No meta management report artifact migration remains in the intended diff.
- Site funnel variants migration and matching model/service/API/UI changes are present.
- Hermes sidecar tests cover persisted state DB response and usage capture.
- Campaign funnel custom page specs are present with tests.
- Verification commands pass or blocked failures are documented with exact output.
- Only intended files are staged for PR prep.
