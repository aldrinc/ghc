# Foundational Step 01 DeerFlow Default Plan

- Add backend settings so Strategy V2 foundational Step 01 defaults to DeerFlow/DSV4 Pro and can be forced back to GPT with an explicit provider flag.
- Add a MOS-owned DeerFlow Step 01 sidecar runner that sends the already-rendered production prompt through DeerFlow with web search, web fetch, calculator, thinking enabled, and no output token cap.
- Wire only foundational Step 01 to the DeerFlow provider path; leave foundational Steps 03, 04, and 06 on the existing GPT/deep-research path.
- Fail loudly when DeerFlow sidecar prerequisites are missing; do not silently fall back to GPT.
- Add focused tests for default provider config, GPT override behavior, DeerFlow routing, and missing sidecar failure.
- Record cost math from the tested run and verify implementation locally.
