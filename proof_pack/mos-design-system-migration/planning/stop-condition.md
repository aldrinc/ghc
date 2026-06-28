# Stop Condition

Plan-only stop condition:

- Design-system migration plan exists.
- Plan gate proof exists.
- `plangatecheck` passes.
- User has the exact execution phrase: `Ship the plan`.

Implementation stop condition after approval:

- Plan contract verifies.
- Source manifest verifies.
- Brand-freeze review passes.
- Tests/build/smoke checks pass or blockers are explicitly documented.
- Proof dashboard renders.
