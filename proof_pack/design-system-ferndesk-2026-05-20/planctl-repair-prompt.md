# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `2026-05-20-ferndesk-design-system-onboarding-plan`
Contract: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/2026-05-20-ferndesk-design-system-onboarding-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/design-system-ferndesk-2026-05-20/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:147: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:176: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:221: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:2926: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:3043: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:147: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:176: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:221: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:2926: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/pages/workspaces/BrandDesignSystemPage.tsx:3043: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1039: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1104: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1180: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1205: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1218: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1230: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1244: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1276: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1289: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1299: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1316: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1335: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1370: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1499: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1562: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1581: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1612: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1627: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1645: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1663: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1683: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1701: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1720: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1739: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1758: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1796: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1039: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1104: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1180: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1205: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1218: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1230: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1244: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1276: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1289: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1299: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1316: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1335: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1370: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1499: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1562: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1581: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1612: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1627: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1645: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1663: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1683: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1701: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1720: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1739: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1758: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/mos/frontend/src/components/clients/OnboardingWizard.tsx:1796: brittle marker `placeholder`
