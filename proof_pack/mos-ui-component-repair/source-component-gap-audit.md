# Source Component Gap Audit

## Missed In Previous Pass

- Choice flows: full single-select choice stack with four options and Continue CTA, multi-select checkbox cards, compact choices, grid/card choices, selected ring behavior, and no-chevron card anatomy.
- Dropdowns: closed combobox trigger, placeholder state, grouped open panel, search row, selected checks, option subtext, keyboard hint, value pills, option metadata, and footer action.
- Inputs: hover/filled/success/error state grid, left icons, trailing keyboard hints, trailing buttons, prefix/suffix controls, phone, currency, password strength, copyable values, autocomplete, required/counter anatomy, OTP separator.
- Cards: feature cards, testimonial cards, pricing cards, featured pricing state, avatar/who rows, price rows, and checklist rows.
- Chips and tags: removable active chips, blue active chips, source status tags, live dot pulse, ink badge.
- Applied product patterns: campaign status card/list and step/process cards.
- Buttons: loading state and arrow icon movement state were underrepresented.

## Intentionally Excluded

- Logo, mark, wordmark, logo gallery, logo construction, brand lockups, brand dos/donts.
- Marketing hero, marketing CTA block, public nav/footer, fake customer logo strip.

## Repair Target

- Add reusable source-shaped choice variants to `ChoiceList`.
- Expand `/dev/components` until these compound patterns are visible in desktop and mobile browser proof.
- Keep names neutral/MOS-owned and avoid copied brand class names in app code.
