status: pass

Main thread repaired and integrated:

- Replaced the wrapper card/grid on `/workspaces/new` with a single-page first-run setup form.
- Kept reusable onboarding primitives available for the design-system preview and modal/debug surfaces.
- Reframed the `/workspaces/new` page as workspace, brand source, product, audience/source, and constraint sections.
- Repaired user feedback after visual review: removed the default stepper/progress rail, removed the persistent right-side setup context rail, removed the intent heading/card, and moved setup context behind an explicit debug toggle.
- Repaired mobile after screenshot QA by removing the sticky launch bar that overlapped form content.
- Added first-run previews to `BrandDesignSystemPage`.
- Added targeted tests for first-run primitives and the page wizard.
- Captured desktop/mobile screenshots.
- Ran semantic UI check, targeted tests, full Vitest suite, build, capture manifest, plan gate, lane check, and planctl verification.
