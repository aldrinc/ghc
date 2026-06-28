# Plan Gate: Foundational Step 01 DeerFlow Default

## Goal

Make Strategy V2 foundational Step 01 default to DeerFlow with DeepSeek V4 Pro while preserving an explicit GPT override flag.

## Problem

Step 01 is expensive when run through GPT. A successful DeerFlow DSV4 Pro parity run showed acceptable quality and much lower measured cost, but production routing still needed a safe provider switch.

## Diagnosis

The workflow lacked a provider boundary for foundational Step 01. Without that boundary, replacing GPT would either require changing the shared foundational runner or risk accidental fallback behavior.

## Current Machine

Foundational Step 01 used the shared tagged GPT runner. Steps 03, 04, and 06 use existing GPT/deep-research behavior.

## Designed Machine

Step 01 now goes through a provider selector. Default is `deerflow`, model is `deepseek-v4-pro`, and `STRATEGY_V2_FOUNDATIONAL_STEP01_PROVIDER=gpt` forces the old GPT path. DeerFlow sidecar prerequisites fail loudly.

## Worst-Day Test

If the sidecar is missing, config is absent, keys are unavailable, or output JSON is invalid, the run must fail with remediation instead of quietly falling back to GPT.

## Metrics

Leading metrics: provider selection, sidecar availability, tool-enabled DeerFlow execution, tagged output parsing, direct routing assertions.

Lagging metrics: per-run cost, source/citation quality, generated Step 01 quality compared to GPT.

## Owner / Review

Owner: Codex execution agent.

Review date: 2026-05-21.

Stop condition: plan contract, direct assertions, lint/compile, cost provenance, capture manifest, and proof dashboard pass.
