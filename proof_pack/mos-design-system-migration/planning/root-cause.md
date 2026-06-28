# Root-Cause Diagnosis

Working root cause:

- The new design language has not been turned into a repo-native token, primitive, naming, and verification system.

Cause chain:

1. Source design system is a bundled local HTML file.
2. Current MOS app tokens were built around copied/temporary visual systems.
3. Borrowed names such as `manus` became internal API because speed mattered more than naming hygiene.
4. Component primitives are incomplete, so pages bypass them.
5. Brand and product UI are not isolated by automated checks.
6. Verification proves compile/test status but not design-system adoption, naming hygiene, or brand preservation.

System flaw:

- Migration currently depends on human memory instead of a source manifest, naming contract, component-first execution order, borrowed-name scan, and proof checks.
