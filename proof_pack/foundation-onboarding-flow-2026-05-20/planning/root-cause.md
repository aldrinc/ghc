# Root Cause Diagnosis

Root cause: MOS lacks a separate marketing-agent setup contract and a provider-backed extraction contract for existing businesses.

5 Whys:

1. Why is onboarding heavy? Because it collects offer/copy/workflow fields.
2. Why does it collect those fields? Because the backend request and workflow require them.
3. Why does the backend require them? Because client onboarding starts full Strategy V2.
4. Why does full Strategy V2 run during onboarding? Because foundation research, offer strategy, and copy generation share one workflow path.
5. Why is that wrong? Because first-run onboarding should feel like setting up a marketing agent, while website extraction, foundation research, and offer/copy setup each need separate contracts and review points.

Diagnosis type: design flaw.

Machine flaw: execution boundaries are wrong. The first-run machine asks for data needed by later machines and has no provider-specific path for existing-business source extraction.
