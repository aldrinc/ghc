# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `step01-1to1-plan`
Contract: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/deerflow-step01-1to1-2026-05-21/step01-1to1-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/deerflow-step01-1to1-2026-05-21/proof_pack/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- none
