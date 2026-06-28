# Onboarding Color Icons Plan

## Goal
Make MOS onboarding choice screens feel more polished and scannable by replacing generic Lucide line icons with original colorful SVG icons inspired by the downloaded quiz treatment.

## Problem
Current onboarding choices use monochrome line icons inside gray icon wells. They are functional, but they do not carry much product personality or fast visual recognition.

## Diagnosis
The downloaded quiz uses self-contained colorful SVG illustrations: a pale rounded tile, saturated gradient fills, and tiny highlight strokes. Our onboarding uses icon-font style components and selected-state repainting, so icons flatten instead of acting as memorable visual anchors.

## Design
- Add a reusable original `OnboardingIcon` SVG component pack.
- Add a color-icon mode to `ChoiceList` so selected state does not repaint colorful icons black.
- Replace onboarding choice icons for business stage, business model, offering kind, and pricing.
- Add optional colorful icons to setup checklist rows.
- Keep surrounding UI restrained and aligned with the existing MOS design system.

## Doing
1. Add original onboarding SVG icon component.
2. Export icon component from onboarding module.
3. Update `ChoiceList` to support color icons.
4. Update onboarding wizard icon mappings.
5. Update tests for icon presence and existing behavior.
6. Run targeted tests, build, and planctl verification.

## Acceptance
- Onboarding choice screens render colorful original SVG icons.
- Color icons keep their colors when selected.
- Setup progress can show colorful semantic icons.
- Existing onboarding navigation and validation behavior remains unchanged.
- Targeted frontend tests and build pass.

## Verification
- `cd mos/frontend && npm test -- --run src/components/clients/OnboardingWizard.test.tsx src/components/ui/toast.test.tsx`
- `cd mos/frontend && npm run build`
- `test -f proof_pack/onboarding-color-icons-2026-05-21/color-icons-qa.json`

## Speed Map
- parallelizable: no
- single-agent reason: one shared UI component and one onboarding wizard are the edit surface; parallel writers would create conflict risk.
- expected speed gain: local parallel reads only.
- token spend justification: no native sub-agents needed.
- write ownership: onboarding components, onboarding wizard, design-system CSS, targeted tests, proof pack.
- fan-in plan: single-lane implementation and verification.
- validation owner: main Codex thread.
- meta-tooling opportunity: future icon packs can reuse the same semantic icon component.
