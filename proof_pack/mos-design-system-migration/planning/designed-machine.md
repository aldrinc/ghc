# Designed Machine

Target flow:

1. Source design-system HTML is captured and verified.
2. Tokens are extracted and mapped to stable MOS-owned or neutral semantic variables.
3. Borrowed namespaces such as `manus` and source-demo token names are removed outright.
4. Tailwind exposes the complete product UI scale through product-owned/neutral names.
5. Core primitives encode the system once.
6. Product screens compose primitives and semantic tokens.
7. Brand-sensitive files and borrowed-name scans are checked before final.
8. Tests, build, screenshots, source manifest, naming scan, and proof dashboard close the loop.

Design principle:

- Product UI changes should happen through a naming contract, tokens, and primitives first, then page migration.
