# MOS UI Component Repair Diff Summary

## Component Layer

- Rebuilt shared primitives around the extracted Moz source values: pill buttons, 54px fields, 12px form radius, 20px cards, 14px floating panels, and compact 22px badges.
- Updated `Button`, inputs, selects, textareas, form fields, badges, status badges, tabs, tables, callouts, dialogs, menus, popovers, tooltips, toasts, skeletons, filter bars, empty states, error states, and onboarding choice cards.
- Expanded `ComponentReviewPage` at `/dev/components` into a real primitive harness: button variants/states/sizes, chips, dots, input groups, combobox-style panels, autocomplete, password strength, copyable values, OTP cells, source-shaped choice flows, multi-select choices, compact choices, grid/card choices, tabs, table, floating panels, feedback states, and route-level examples.
- Fixed mobile overflow in the review harness by constraining tabs, table columns, toast width, and empty-state actions.
- Reworked `ChoiceList` into neutral MOS-owned source-shaped variants instead of the skipped basic card pass: stack, multi-select, compact, and grid/card layouts with selected rings and no chevron anatomy.
- Fixed the real first-run route input focus ring by splitting `--input-ring` from `--first-run-focus`, so focused fields no longer inherit the thick ink ring.
- Split `FunnelRuntimeProvider`, `useFunnelRuntime`, and runtime path helpers into `funnels/funnelRuntime.tsx` to remove a `puckConfig` import cycle that blanked browser proof during HMR.
- Preserved the `default` button variant only as a legacy compatibility path for existing call sites.

## Token And CSS Layer

- Restored source radius scale: 4px, 6px, 10px, 14px, 20px, 28px, and pill.
- Restored product card/panel primitives to the source-like shape instead of the earlier over-dense square pass.
- Kept display headings for the source-like setup/component surfaces while avoiding brand/logo/wordmark edits.
- Added component utility classes for state cards, chips, dots, input groups, combobox panels, choice cards, and OTP cells.
- Added responsive choice-card CSS so mobile choices keep readable text columns and selected rings stay anchored to the card.
- Removed a copied third-party reference from the sales PDP template stylesheet comment.

## Browser Validation

- Rechecked `/dev/components`, `/workspaces/new`, and `/workspaces/overview` in the attached Chrome profile.
- Verified expanded `/dev/components` at desktop and 390px mobile width with no horizontal overflow.
- Verified actual `/workspaces/new` focused input and selected choice step after the token/component refactor.
- Captured refreshed screenshots and audit JSON under `proof_pack/mos-ui-component-repair/`.
