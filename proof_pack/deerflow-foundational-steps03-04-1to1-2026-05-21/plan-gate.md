# Plan Gate: DeerFlow DSV4 Foundational Steps 03/04

## Goal

Test foundational Steps 03 and 04 with DeerFlow DSV4 Pro, compare to persisted GPT artifacts, and decide whether they are ready to default.

## Problem

Step 01 looked good enough to default, but Step 04 is the deep research step and may require a different harness. We need proof before routing every brand through DSV4.

## Diagnosis

Step 03 is a prompt-writing task. Step 04 is a research-plus-synthesis task. Treating both as one generic DeerFlow call risks spending on research without forcing final tagged synthesis.

## Current Machine

Production GPT artifacts exist for Steps 03 and 04. The Step 04 persisted artifact already looks brittle because its full content block is only a short placeholder while the summary carries most visible substance.

## Designed Machine

Run only 03/04, preserve raw events and usage, attempt one same-thread continuation if Step 04 researches but fails final output, then stop and compare.

## Worst-Day Test

Worst case is exactly what happened: DSV4 spends on web research, says it has enough data, and fails to emit the final tagged report. The run must be captured as failed quality, not promoted.

## Metrics

Leading metrics: Step 03 tag validity, Step 04 tool use, final `<SUMMARY>/<CONTENT>` presence, quote-bank content, source/citation evidence.

Lagging metrics: cost, latency, report completeness, default-readiness.

## Owner / Review

Owner: Codex execution agent.

Review date: 2026-05-21.

Stop condition: Step 03/04 outputs or failure logs captured, comparison written, source manifest/provenance/contract pass.
