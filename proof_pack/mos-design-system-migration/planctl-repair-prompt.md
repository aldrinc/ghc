# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `2026-05-20-mos-design-system-migration-plan`
Contract: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/2026-05-20-mos-design-system-migration-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-design-system-migration/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/input.tsx:13: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/textarea.tsx:12: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-design-system-migration/logs/unit-tests.log:82: brittle marker `Not implemented`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-design-system-migration/logs/unit-tests.log:82: brittle marker `Not implemented`
