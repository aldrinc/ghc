# Current Machine

Current flow:

- CSS variables in `theme.css` define the active visual system.
- Tailwind maps semantic aliases to those variables.
- Tailwind still exposes copied namespaces.
- `components/ui/*` wraps common controls but leaves several visual decisions in Tailwind strings.
- `design-system.css` provides a small set of shared classes.
- Screens use a mix of shared primitives and ad hoc utility styling.
- Brand identity blocks and naming hygiene are protected only by human review.

Failure point:

- The system allows visual and vocabulary drift because primitives and checks do not cover enough of the UI.
