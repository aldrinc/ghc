# Root-Cause Diagnosis

## Problem
The current first-run experience feels like admin setup, not a premium guided agent experience.

## 5 Whys
1. Why does it feel admin-like?
   - It leads with forms, bordered panels, explanatory copy, and field validation.
   - Classification: proximate cause.

2. Why does it lead with forms?
   - The onboarding component is designed around gathering every required backend payload field before starting work.
   - Classification: proximate cause.

3. Why does the backend payload shape dominate the UI?
   - The design system lacks a separate "first-run/agentic setup" layer that can translate backend requirements into progressive moments.
   - Classification: approaching root.

4. Why is that layer missing?
   - Current design system work focuses on reusable UI primitives and funnel tokens, not the branded workflow grammar for setup, progress, review, and publish states.
   - Classification: root cause.

5. Why does that matter?
   - Without workflow-specific primitives, every onboarding screen re-creates local layout and copy choices, so the experience cannot compound into a recognizable brand.
   - Classification: root cause.

## Root Cause
Design-system coverage stops at generic app primitives and funnel CSS variables. It does not define the experiential grammar needed for a premium agentic onboarding flow.

## Machine Thinking
- Current machine: collect required fields -> create client/product/compliance -> start onboarding workflow -> navigate to workspace overview.
- Break point: first-run UI makes users feel they are filling a setup form instead of commanding an agent.
- Flaw type: design flaw, with input constraints from real backend requirements.
