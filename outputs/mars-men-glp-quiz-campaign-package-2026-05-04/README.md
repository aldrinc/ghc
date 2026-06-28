# Mars Men GLP + Quiz Campaign Package

Scope: GLP lander and quiz funnel only.

Primary file:
- `glp-quiz-copy-units-with-creatives.csv`: one row per source copy unit with the Tenor remixed full ad copy and related creative image paths.

Additional files:
- `glp-quiz-campaign-ready-copy-units.csv`: same campaign-ready copy-unit table as the primary file.
- `glp-quiz-campaign-ready-expanded.csv`: one row per copy-unit/creative pairing for campaign build tooling.
- `creatives/`: copied unique static creative images referenced by the CSV files.
- `references/tenor-ad-remix-output.csv`: original remixed output used for the merge.
- `manifest.json`: machine-readable package summary.

Counts:
- Remixed copy units: 11
- Expanded copy/creative rows: 23
- Unique creatives copied: 23

Dedupe basis from source launch kit:
- Creative uniqueness: exact SHA-256 hash of static image bytes.
- Copy uniqueness: normalized title + ad body + CTA + link description.
