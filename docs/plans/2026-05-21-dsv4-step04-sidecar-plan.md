# DSV4 Step 4 Sidecar Plan

## Goal

Add a separate DSV4 Pro / DeerFlow Step 4 path without changing the existing GPT Step 4 path.

## Scope

1. Keep GPT Step 4 routed through the current `_run_tagged_foundational_step` implementation.
2. Add a `STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER` flag with default `gpt`.
3. Add a DSV4 Step 4 path that uses DeerFlow for research, then synthesizes from captured evidence with DSV4 without tools.
4. Add output validation so Step 4 cannot pass with status text or placeholder content.
5. Add focused tests for provider routing, config defaults, and Step 4 validation helpers.

## Acceptance

- GPT Step 4 provider uses the existing `_run_tagged_foundational_step` call shape.
- DSV4 Step 4 provider calls a distinct DeerFlow Step 4 function with `deepseek-v4-pro`.
- Invalid DSV4 outputs like "Let me write it now" fail validation.
- Placeholder GPT-style content is detected by the stricter DSV4 validator.
- Unit tests pass for the changed backend paths.
