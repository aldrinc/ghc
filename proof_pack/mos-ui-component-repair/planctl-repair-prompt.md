# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `2026-05-20-mos-ui-component-repair-plan`
Contract: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/2026-05-20-mos-ui-component-repair-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:187: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:203: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:207: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:210: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:275: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:281: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:312: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:485: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:187: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:203: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:207: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:210: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:275: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:281: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:312: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:485: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/logs/unit-tests.log:49: brittle marker `Not implemented`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/logs/unit-tests.log:49: brittle marker `Not implemented`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:561: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system.css:594: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system.css:594: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system.css:991: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/input.tsx:13: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/input.tsx:13: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/textarea.tsx:12: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/textarea.tsx:12: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:561: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:187: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:203: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:207: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:210: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:275: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:281: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:312: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:485: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source-component-gap-audit.md:6: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:561: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:598: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:598: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:995: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3083: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3087: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3109: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3123: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3130: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3135: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3259: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3334: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3350: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extracted.html:3451: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source-component-gap-audit.md:6: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:345: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/source/moz-design-system-extract.json:561: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/input.tsx:13: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/input.tsx:13: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/textarea.tsx:12: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/ui/textarea.tsx:12: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/workspaces-new-input-focused-after.audit.json:11: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:187: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:203: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:207: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:210: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:275: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:281: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:312: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:485: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/logs/unit-tests-after-compound-repair.log:31: brittle marker `Not implemented`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/mos-ui-component-repair/logs/unit-tests-after-compound-repair.log:31: brittle marker `Not implemented`
