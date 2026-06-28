# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `2026-05-20-onboarding-review-screen-redesign-plan`
Contract: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/2026-05-20-onboarding-review-screen-redesign-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/onboarding-review-screen-2026-05-20/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:187: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:203: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:207: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:210: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:216: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:275: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:281: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:312: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/dev/ComponentReviewPage.tsx:485: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/styles/design-system.css:495: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:971: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1056: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1072: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1089: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1279: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1342: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1362: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1426: brittle marker `placeholder`
