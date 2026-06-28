# Goal

Fix MOS modal readability by moving default title-description spacing into shared modal primitives.

Key results:

- Standard `Dialog` and `AlertDialog` headers are readable without caller-supplied `mt-*`.
- Manual spacing overrides are removed where redundant.
- Component review shows the fixed default.
- Design-system and unit checks pass after implementation.

