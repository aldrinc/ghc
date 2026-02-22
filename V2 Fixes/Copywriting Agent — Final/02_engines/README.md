# 02_engines/ -- Copywriting Engines

This folder contains the core engines that power headline generation, promise enforcement, and page-level copy construction.

---

## Folder Structure

```
02_engines/
  headline_engine/
    ENGINE.md                -- Step-by-step execution flow for headline writing
    WORKFLOW.md              -- Full Headline Engineering System (13 sections)
    reference/
      100-greatest-analysis.md   -- Analysis of 100 greatest headlines
      dr-headline-engine.md      -- DR headline formula reference
      open-loop-patterns.md      -- Open loop pattern library
      platform-adaptation.md     -- Platform-specific adaptation specs
  promise_contract/
    PROMISE_CONTRACT_SYSTEM.md   -- Consolidated Promise Contract reference
  page_templates/
    Presales Page Purposes.md                      -- Presale page purpose and structure
    Sales Page Purpose.md                          -- Sales page purpose and structure
    Presales and Sales Page General Constraints.md -- Shared constraints for both page types
```

---

## headline_engine/

The headline engine is the system for generating direct response headlines. It contains:

- **ENGINE.md** -- The operational execution flow. This is the step-by-step sequence the agent follows when writing headlines: load context, select archetypes, select formulas, write headlines, extract Promise Contracts, run differentiation checks, and pass the quality gate.

- **WORKFLOW.md** -- The full Headline Engineering System. 13 sections covering hook anatomy (3 required components), the 7 Laws of Headline Engineering, 9 headline archetypes, page-type calibration, headline stack construction, platform adaptation, message-match enforcement, HookBank differentiation, 30 headline formulas, bullet-to-headline conversion, testing protocol, self-evaluation checklist, and the quality gate (deterministic scorer + LLM QA loop).

- **reference/** -- Supporting reference material including headline analysis, DR formula templates, open loop patterns, and platform-specific adaptation rules.

## promise_contract/

The Promise Contract is the enforcement mechanism that connects headlines to page bodies. It ensures every headline's implicit promise is delivered by the body copy.

- **PROMISE_CONTRACT_SYSTEM.md** -- Consolidated reference covering: what a Promise Contract is, the 4 fields (LOOP_QUESTION, SPECIFIC_PROMISE, DELIVERY_TEST, MINIMUM_DELIVERY), the Step 4.5 extraction procedure, how the contract governs body copy writing, the PC1-PC4 congruency tests, the PC2 hard gate rule, and common failure modes.

## page_templates/

Page-level specifications for presale and sales page copy construction.

- **Presales Page Purposes.md** -- Purpose, structure, and function of presale pages (listicles and advertorials).
- **Sales Page Purpose.md** -- Purpose, structure, and function of the sales page.
- **Presales and Sales Page General Constraints.md** -- Shared constraints that apply across both presale and sales page types.

---

## How the Engines Connect

1. The **headline engine** generates headlines with Promise Contracts attached.
2. The **Promise Contract system** governs body copy writing -- the page writer uses the contract as a binding specification.
3. The **page templates** define the structural framework the body writer works within.
4. The congruency scorer (PC1-PC4 tests) verifies the finished page satisfies the Promise Contract.

The flow is: headline engine produces headline + contract --> page template provides structure --> body writer delivers against contract --> congruency scorer verifies delivery.
