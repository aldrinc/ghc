# Token Naming Contract

Rules for this migration:

- Product tokens must use MOS-owned or neutral vocabulary.
- Do not introduce source-demo names such as `--moz-*`, `mozBlue`, or `moz-blue` as app API.
- Do not keep borrowed names such as `manus`.
- Prefer semantic tokens for call sites: `accent`, `surface`, `content`, `success`, `warning`, `danger`, `info`.
- Use primitive scales for system construction: `blue`, `ink`, `slate`, spacing, radius, shadow, and motion.
- Brand identity tokens remain out of scope until brand elements are finalized.

Permanent app vocabulary after this pass:

- Neutral primitives: `ink`, `blue`, `slate`.
- Product semantics: `bg`, `surface`, `panel`, `content`, `border`, `input`, `popover`, `card`, `sidebar`.
- Status semantics: `success`, `warning`, `danger`, `info`.
- Component/layout helpers: `ds-card`, `ds-section-card`, `ds-page`, `ds-section`, `ds-empty-surface`, `text-overline`.

Verification:

- `npm run check:design-system`
- `npm run check:semantic-ui`
