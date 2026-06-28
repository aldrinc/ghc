# Brand System Repair Plan

## Goal
Repair the MOS UI regressions caused by incomplete design-system refactors without changing unfinished brand elements.

## Items
1. Replace copied Manus design tokens with neutral MOS tokens and define every token currently used by components.
2. Add missing first-run, choice-card, and enhanced input CSS so onboarding primitives render as designed.
3. Restore sign-in routing to the existing `/sign-in` path flow while keeping the neutral wordmark untouched.
4. Validate with static token checks, frontend build, component review screenshot, onboarding screenshot, and workspace screenshot.
5. Remove the split-panel onboarding page treatment and validate the actual onboarding page as a single focused flow.
6. Repair the workspace Cards/List segmented selector and validate it in the live workspaces UI.
7. Repair onboarding progress behavior and typography readability, then validate the exact branch-choice sequence in browser.
