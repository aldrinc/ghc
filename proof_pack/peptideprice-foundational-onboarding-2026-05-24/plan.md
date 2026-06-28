# Peptide Price Foundational Onboarding Run

## Goal

Create a new MOS onboarding for `https://peptideprice.store/`, run the full foundation-only docs flow, record the UI, and deliver a downloadable ZIP of the foundational docs.

## Acceptance

- Source capture manifest exists for `https://peptideprice.store/` and verifies.
- MOS UI recording exists and covers sign-in, onboarding submission, wait/progress, and docs download/review.
- New onboarding starts from the UI and produces a client, product, onboarding workflow, strategy workflow, and complete foundational bundle.
- Foundational readiness reaches `foundation_ready` with all required foundational step keys present.
- Foundational docs ZIP exists locally and contains the system-required foundation-only Markdown documents: `v2-02.foundation.01`, `v2-02.foundation.03`, and `v2-02.foundation.04`.
- Proof dashboard exists with logs, IDs, artifact paths, and blockers if any.

## Verification

- `/Users/aldrinclement/.codex/bin/capturectl verify proof_pack/peptideprice-foundational-onboarding-2026-05-24/source/source_manifest.json`
- Validate backend health and Temporal connectivity locally.
- Poll `/clients/{client_id}/foundation-readiness?productId={product_id}` until `foundation_ready`.
- Validate ZIP contents with `unzip -l`.
- `/Users/aldrinclement/.codex/bin/planctl verify proof_pack/peptideprice-foundational-onboarding-2026-05-24/plan.contract.json --run`

## Notes

- No fabricated business facts, competitor URLs, prices, or classifications.
- Use data captured from the provided website or extraction output. Missing optional inputs stay omitted.
- During execution, the UI still referenced a fourth/avatar brief document, but backend readiness and generated artifacts define the foundation-only bundle as steps `01`, `03`, and `04`; the UI copy was corrected to match that contract.
