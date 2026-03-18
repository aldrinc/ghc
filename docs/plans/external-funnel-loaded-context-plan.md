# External Funnel Loaded Context Plan

## Purpose

This document explains, in simple terms, how an external URL campaign should produce valid downstream creatives.

The key point is:

- an external URL does **not** provide creative strategy by itself
- it only tells the system where traffic should go
- the creative system still needs approved angles, offer facts, copywriting, and brand guardrails
- for this flow, those inputs must be **loaded into the campaign directly**
- they should **not** come from the Strategy V2 flow

So the external flow needs two separate things:

1. a valid destination contract
2. a valid creative-input contract


## Simple Mental Model

For an external campaign, the system should work like this:

1. The operator creates a campaign.
2. The operator adds external destination URLs.
3. The operator loads approved creative inputs into the campaign:
   - angles
   - offer facts
   - copywriting
   - brand voice and constraints
4. The system generates asset briefs from those loaded inputs.
5. The system generates ad copy packs from those briefs and loaded inputs.
6. The system generates creative assets.
7. The system prepares Meta specs using the generated creatives plus the external URLs.
8. The system publishes to Meta.

The external URL is only used at the delivery layer and Meta destination layer.
The external URL is **not** enough to generate creative strategy.


## What The External URL Actually Solves

When a user adds an external funnel, the system gets:

- `preSalesUrl`
- `salesUrl`
- optionally `checkoutUrl`
- optionally `thankYouUrl`

Those URLs tell the system:

- which page type exists
- where a given creative should send the click
- which URL should be written into the Meta creative spec

That is necessary, but it is not sufficient for creative generation.

The URLs do **not** tell the system:

- what angle to push
- what promise to lead with
- what copy claims are approved
- what proof points are allowed
- what tone of voice to use
- what hook families should be explored


## What The Creative System Actually Needs

To produce valid creatives for an external campaign, the system needs a campaign-level creative packet with approved inputs.

That packet should contain at least:

- approved angles
- the selected active angles for this campaign
- approved offer facts
- approved copywriting
- brand voice guidance
- legal and claims guardrails
- product facts and positioning context
- destination mapping by page type

In practical terms, the creative system needs enough information to answer:

- what are we selling?
- to whom?
- with what approved angle?
- with what approved proof and constraints?
- what kind of page is this ad pointing to?


## The Canonical Inputs We Should Load

For external campaigns, we should load the following inputs directly into the campaign.

### 1. Destination Contract

This is the external funnel definition:

- `deliveryMode = external_urls`
- `preSalesUrl`
- `salesUrl`
- optional `checkoutUrl`
- optional `thankYouUrl`
- validation status

This is the routing contract.
It is not the creative contract.

### 2. Angle Contract

We should load:

- one or more approved campaign angles
- a stable angle id for each angle
- angle name
- angle summary
- supporting rationale or proof points
- operator-selected active angles for the campaign

This replaces the Strategy V2 selected-angle dependency for this flow.

### 3. Offer Contract

We should load:

- product offer summary
- offer mechanics
- pricing facts if approved
- bonuses / guarantee facts if approved
- disallowed claims
- proof points that are safe to reuse

This replaces the Strategy V2 offer dependency for this flow.

### 4. Copy Contract

We should load:

- approved core copy blocks
- message hierarchy
- approved claims
- forbidden claims
- hooks or headline directions
- CTA guidance
- proof language
- compliance guardrails

This replaces the Strategy V2 copy and copy-context dependency for this flow.

### 5. Brand / Product Contract

We should load:

- client canon / brand context
- tone of voice
- product facts
- audience / positioning notes
- visual constraints

Some of this may already exist in canonical client docs.
That is fine.
The important rule is that anything missing from general brand context but needed for the campaign must be loaded into the campaign directly, not inferred from Strategy V2.


## How Strategy V2 Does This Today

Today, Strategy V2 does not hand downstream systems a single "external funnel" object.
Instead, it builds the creative context indirectly through a set of approved artifacts and a normalized downstream packet.

In simple terms, Strategy V2 currently gives the system:

- the selected angle
- supporting angle candidates and evidence
- the chosen offer structure
- approved copy
- copy context and guardrails
- awareness-angle context when present
- brand and product context from canon docs

That information is then consumed by:

- asset brief generation
- ad copy pack generation
- creative generation
- campaign launch context

So the important observation is:

- Strategy V2 already produces almost the same **kind** of information this external-loaded flow needs
- the difference is the **provenance**
- today that information comes from Strategy V2 artifacts
- in the external-loaded flow, it should come from directly loaded campaign inputs


## Strategy V2 To External-Loaded Crosswalk

This is the missing mapping between the current system and the proposed external-loaded system.

| Current Strategy V2 source | What it means today | External-loaded equivalent | Why downstream needs it |
| --- | --- | --- | --- |
| `strategy_v2_stage3.selected_angle` | The approved campaign angle | `angles.active[]` or `selected_angle` | Gives briefs and copy generation a clear campaign message direction |
| `ranked_angle_candidates` and optional `awareness_angle_matrix` | Supporting angle options, audience-awareness framing, evidence | `angles.available[]` and optional `awareness_angle_matrix` | Useful for brief generation, future variation logic, and keeping angle choice grounded |
| `strategy_v2_offer` | Approved offer structure, value stack, guarantee, selected variant, product offer facts | `offer` | Gives copy and creative systems the actual commercial facts they are allowed to use |
| `strategy_v2_copy` | Approved long-form copy, promise contract, semantic gates, congruency, template payloads | `copy` | Gives downstream systems approved language and message hierarchy |
| `strategy_v2_copy_context` | Supporting copy guardrails and context | `copy_context` | Gives copy-pack generation the rules around how to express the message safely |
| `client_canon` / `client_canon_compact` | Brand, tone, constraints, product context | `brand_context` | Keeps generated assets aligned to brand and compliance rules |
| `experiment_specs` and `strategy_sheet` | The campaign’s experiment / creative structure | `generation_inputs` or `experiment_specs` | Tells the brief generator what creative variants still need to be produced |
| `downstream_packet` | A normalized packet combining angle, offer, copy, copy context, and provenance | `campaign_creative_context` | This should become the compatibility target for the loaded external flow |


## The Practical Match

The easiest way to think about this is:

- Strategy V2 currently builds a normalized creative packet
- the external-loaded flow should build the same kind of packet
- only the source changes

So the current Strategy V2 path is roughly:

1. choose an angle
2. choose the offer winner
3. approve final copy
4. normalize those outputs into a downstream packet
5. use that packet and related docs to drive briefs and copy generation

The external-loaded path should be:

1. load approved angles
2. load approved offer facts
3. load approved copy and constraints
4. normalize those loaded inputs into a campaign creative context
5. use that context to drive briefs and copy generation

This means we should preserve the **semantic contract** while changing the **input source**.


## Recommended Compatibility Rule

To minimize churn, the external-loaded campaign context should intentionally mirror the existing Strategy V2 downstream packet shape as closely as possible.

That means the loaded campaign context should have sections like:

- `selected_angle`
- `angles.available`
- `offer`
- `copy`
- `copy_context`
- `awareness_angle_matrix`
- `brand_context`
- `generation_inputs`
- `provenance`

If we do that, most of the downstream system does not need a new mental model.
It only needs a new source of truth.


## What Should Stay The Same

These semantic expectations should stay the same between Strategy V2 and the external-loaded flow:

- there is always a selected campaign angle
- there is always an approved commercial offer packet
- there is always an approved copy packet
- there is always a copy-context / guardrail packet
- there is always destination typing for each creative requirement
- there is always brand / legal context

If those stay true, briefs, copy packs, and Meta specs can be generated the same way.


## What Should Change

These provenance assumptions should change for the external-loaded flow:

- do not remove the existing Strategy V2 path
- add a second provider path for campaigns that are manually loaded
- when the provider is manual, do not require Strategy V2 launch lineage
- when the provider is manual, do not require Strategy V2 artifact ids
- when the provider is manual, do not require Strategy V2 docs to be the active source

Instead:

- keep `strategy_v2` as the existing provider
- add `manual` as a second provider
- require loaded campaign creative context when provider is `manual`
- require that loaded context to be operator-approved
- allow downstream generation to proceed from that loaded context directly


## Where The Current Code Is Coupled

There are two important places where the current code still assumes Strategy V2 is the source:

### Asset brief generation

The brief generator currently selects docs such as:

- `strategy_v2_stage3`
- `strategy_v2_offer`
- `strategy_v2_copy`
- `strategy_v2_copy_context`

and uses a Strategy V2 packet summary as prompt context.

### Ad copy pack generation

The ad copy pack step currently expects the attached strategy, offer, copy, and copy-context documents to exist in the workspace, and those are presently Strategy V2-oriented.

So the implementation goal is not to invent a second downstream logic model.
It is to keep the downstream logic and add a source toggle:

- provider `strategy_v2` -> use the current Strategy V2 artifacts
- provider `manual` -> use loaded campaign creative context artifacts

while keeping the downstream semantics aligned.


## Provider Toggle

The simplest design is a campaign-level source selector:

- `creativeContextProvider = "strategy_v2" | "manual"`

Recommended behavior:

- `strategy_v2`
  - current behavior
  - current launch-context and doc-key path
- `manual`
  - skip Strategy V2 as the active context source
  - use manually loaded campaign context docs instead
  - keep the rest of the downstream creative and Meta pipeline the same

This toggle should live on the campaign or a campaign-level creative-context config.
It should not live inside the external URL object itself because the external URL only defines delivery, not creative provenance.


## How To Set This Up Now

If we want this working with the current system shape, and we already have:

- a custom angle doc
- a custom offer doc

then the clean implementation is:

1. normalize those source docs into structured campaign JSON
2. persist those JSON payloads as campaign artifacts
3. upload those JSON payloads into the Claude workspace as campaign-scoped context docs
4. update downstream generation code to read those campaign-scoped docs instead of Strategy V2 docs

The important rule is:

- do **not** feed raw arbitrary source docs directly into downstream generation and hope the prompts figure it out
- normalize once into stable JSON
- then make downstream generation consume the normalized JSON


## Exact Manual Provider Contract

If `creativeContextProvider = "manual"`, the campaign should be considered ready only when this payload exists in normalized form:

```json
{
  "provider": "manual",
  "schemaVersion": 1,
  "angles": {
    "selected_angle": {
      "angle_id": "<required string>",
      "angle_name": "<required string>",
      "evidence": ["<optional string>"]
    },
    "available_angles": [
      {
        "angle_id": "<required string>",
        "angle_name": "<required string>",
        "summary": "<required string>",
        "evidence": ["<optional string>"],
        "status": "<optional string>"
      }
    ],
    "awareness_angle_matrix": {
      "<optional key>": "<optional value>"
    }
  },
  "offer": {
    "ump": "<required string>",
    "ums": "<required string>",
    "core_promise": "<required string>",
    "value_stack_summary": "<required string>",
    "guarantee_type": "<optional string>",
    "pricing_rationale": "<optional string>",
    "variant_selected": "<optional string>",
    "composite_score": "<optional number>",
    "selected_variant": {
      "<optional key>": "<optional value>"
    },
    "selected_variant_score": {
      "<optional key>": "<optional value>"
    },
    "product_offer_id": "<optional string>",
    "product_offer": {
      "<required key>": "<required value>"
    },
    "approved_claims": ["<optional string>"],
    "forbidden_claims": ["<optional string>"],
    "proof_points": ["<optional string>"]
  },
  "copy": {
    "headline": "<required string>",
    "promise_contract": {
      "loop_question": "<required string>",
      "specific_promise": "<required string>",
      "delivery_test": "<required string>",
      "minimum_delivery": "<required string>"
    },
    "presell_markdown": "<optional string>",
    "sales_page_markdown": "<optional string>",
    "quality_gate_report": {
      "<optional key>": "<optional value>"
    },
    "semantic_gates": {
      "<optional key>": "<optional value>"
    },
    "congruency": {
      "<optional key>": "<optional value>"
    },
    "template_payloads": {
      "<optional key>": "<optional value>"
    }
  },
  "copyContext": {
    "audience_product_markdown": "<required markdown string>",
    "brand_voice_markdown": "<required markdown string>",
    "compliance_markdown": "<required markdown string>",
    "mental_models_markdown": "<required markdown string>",
    "awareness_angle_matrix_markdown": "<required markdown string>"
  },
  "experimentSpecs": {
    "experimentSpecs": [
      {
        "id": "<required string>",
        "name": "<required string>",
        "hypothesis": "<optional string>",
        "metricIds": ["<required string>"],
        "variants": [
          {
            "id": "<required string>",
            "name": "<required string>",
            "description": "<optional string>",
            "channels": ["<required string>"],
            "guardrails": ["<optional string>"]
          }
        ]
      }
    ]
  }
}
```

For the manual path, these sections should be treated as:

- `angles` required
- `offer` required
- `copy` required
- `copyContext` required
- `experimentSpecs` required until we add a manual experiment-spec generator

If any of those sections are missing, the campaign should not be marked ready for external creative generation.


## Minimum System Changes

### 1. Add campaign-scoped loaded creative artifacts

We need new artifact types or an equivalent campaign-scoped storage contract for:

- `campaign_loaded_angles`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `campaign_creative_context`

The first four are source sections.
The fifth is the normalized aggregate packet used by downstream systems.

### 2. Add a loader / ingestion endpoint

We need a backend path that accepts normalized JSON for those sections and writes them to:

- campaign artifacts
- Claude context files
- optionally Gemini file search

Recommended shape:

- `POST /campaigns/{campaign_id}/creative-context/loaded`

The endpoint should:

- validate the JSON payloads
- persist them as artifacts tied to the campaign
- upload each section into the workspace with a stable `doc_key`
- synthesize and persist `campaign_creative_context`

Recommended request body:

```json
{
  "provider": "manual",
  "schemaVersion": 1,
  "angles": {
    "<required key>": "<required value>"
  },
  "offer": {
    "<required key>": "<required value>"
  },
  "copy": {
    "<required key>": "<required value>"
  },
  "copyContext": {
    "<required key>": "<required value>"
  },
  "experimentSpecs": {
    "<required key>": "<required value>"
  }
}
```

### 3. Add new campaign doc keys

We should upload the normalized JSON docs using doc keys like:

- `campaign_loaded_angles`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `campaign_creative_context`

The generated docs should be uploaded the same way current generation docs are uploaded:

- UTF-8 JSON bytes
- filename like `<doc_key>.json`
- `mime_type="text/plain"`

### 4. Update experiment generation or require direct experiment spec loading

The current brief flow still needs `experiment_specs`.

So we need one of these two paths:

1. add a new experiment-spec generator that reads `campaign_loaded_angles`
2. require `experiment_specs` to be loaded directly for external campaigns

The fastest safe path is:

- require `experiment_specs` explicitly

That avoids hidden inference and keeps the brief contract clear.

### 5. Update asset brief generation context selection

The brief generator currently reads Strategy V2 docs.

Update it to branch by provider:

- if provider is `strategy_v2`, keep the current behavior
- if provider is `manual`, read, in this order:

- `campaign_creative_context`
- `campaign_loaded_angles`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `client_canon_compact`
- `client_canon`
- `metric_schema`
- `strategy_sheet:{campaign_id}`
- `experiment_specs:{campaign_id}`

and stop requiring:

- `strategy_v2_stage3`
- `strategy_v2_offer`
- `strategy_v2_copy`
- `strategy_v2_copy_context`

### 6. Update ad copy pack generation context selection

The copy-pack step should use the same campaign-loaded docs instead of Strategy V2 docs.

Update it to branch by provider:

- if provider is `strategy_v2`, keep the current behavior
- if provider is `manual`, read:

- `campaign_creative_context`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `client_canon_compact`
- `client_canon`
- `metric_schema`
- `experiment_specs:{campaign_id}`
- `asset_briefs:{campaign_id}`

### 7. Replace the readiness gate

Do not replace readiness globally.

Branch by provider:

- if provider is `strategy_v2`
  - keep the current launch-context readiness behavior
- if provider is `manual`
  - readiness means:
    - valid external delivery
    - valid loaded creative context
    - valid experiment specs


## Important Constraint

If we only have:

- a custom angle doc
- a custom offer doc

that is still **not enough** for the current creative path.

We also need either:

- a loaded copy doc and a loaded copy-context doc

or:

- a new explicit preprocessing step that transforms the custom angle + offer + brand context into those missing copy artifacts

The clean recommendation is:

- require all four loaded docs explicitly

That is safer and much easier to reason about.


## Recommended Formats

The source documents can originate as:

- Google Docs
- Markdown
- PDF
- operator-authored notes

But they should **not** be consumed directly by the creative pipeline.

They should be normalized into structured JSON first.

### 1. `campaign_loaded_angles`

This should be JSON.

Required shape:

```json
{
  "selected_angle": {
    "angle_id": "<required string>",
    "angle_name": "<required string>",
    "evidence": ["<optional string>", "<optional string>"]
  },
  "available_angles": [
    {
      "angle_id": "<required string>",
      "angle_name": "<required string>",
      "summary": "<required string>",
      "evidence": ["<optional string>", "<optional string>"],
      "status": "<optional string>"
    }
  ],
  "awareness_angle_matrix": {
    "<optional object>": "<optional value>"
  }
}
```

Minimum requirement for downstream use:

- `selected_angle.angle_id`
- `selected_angle.angle_name`

### 2. `campaign_loaded_offer`

This should be JSON.

Recommended shape:

```json
{
  "ump": "<required string>",
  "ums": "<required string>",
  "core_promise": "<required string>",
  "value_stack_summary": "<required string>",
  "guarantee_type": "<optional string>",
  "pricing_rationale": "<optional string>",
  "selected_variant": {
    "<optional object>": "<optional value>"
  },
  "product_offer": {
    "<required object>": "<required value>"
  },
  "approved_claims": ["<string>", "<string>"],
  "forbidden_claims": ["<string>", "<string>"],
  "proof_points": ["<string>", "<string>"]
}
```

Minimum requirement for downstream use:

- enough approved offer facts to ground copy safely

### 3. `campaign_loaded_copy`

This should be JSON.

Recommended shape:

```json
{
  "headline": "<required string>",
  "promise_contract": {
    "<required object>": "<required value>"
  },
  "presell_markdown": "<optional string>",
  "sales_page_markdown": "<optional string>",
  "quality_gate_report": {
    "<optional object>": "<optional value>"
  },
  "semantic_gates": {
    "<optional object>": "<optional value>"
  },
  "congruency": {
    "<optional object>": "<optional value>"
  },
  "template_payloads": {
    "<optional object>": "<optional value>"
  }
}
```

For ads-only external flow, the practical minimum is:

- `headline`
- `promise_contract`

For fuller compatibility with the current Strategy V2 downstream packet, include:

- `presell_markdown`
- `sales_page_markdown`
- `template_payloads`

### 4. `campaign_loaded_copy_context`

This should be JSON and should mirror the current `CopyContextFiles` structure.

Required shape:

```json
{
  "audience_product_markdown": "<required markdown string>",
  "brand_voice_markdown": "<required markdown string>",
  "compliance_markdown": "<required markdown string>",
  "mental_models_markdown": "<required markdown string>",
  "awareness_angle_matrix_markdown": "<required markdown string>"
}
```

This is the strictest document shape in the current system.
If this document is missing, the copy path will not be well grounded.

### 5. `campaign_creative_context`

This should be the normalized aggregate packet.

Recommended shape:

```json
{
  "selected_angle": {
    "angle_id": "<required string>",
    "angle_name": "<required string>",
    "evidence": ["<optional string>"]
  },
  "offer": {
    "<required object>": "<required value>"
  },
  "copy": {
    "<required object>": "<required value>"
  },
  "copy_context": {
    "<required object>": "<required value>"
  },
  "awareness_angle_matrix": {
    "<optional object>": "<optional value>"
  },
  "brand_context": {
    "<optional object>": "<optional value>"
  },
  "generation_inputs": {
    "<optional object>": "<optional value>"
  },
  "provenance": {
    "source": "loaded_campaign_context"
  }
}
```

This is the object downstream code should conceptually read.

### 6. `experiment_specs:{campaign_id}`

If we do not build a new experiment-spec generator from loaded angles immediately, this must be loaded directly.

It should match the current experiment spec shape:

```json
{
  "experimentSpecs": [
    {
      "id": "<required string>",
      "name": "<required string>",
      "hypothesis": "<optional string>",
      "metricIds": ["<required string>"],
      "variants": [
        {
          "id": "<required string>",
          "name": "<required string>",
          "description": "<optional string>",
          "channels": ["<required string>"],
          "guardrails": ["<optional string>"]
        }
      ]
    }
  ]
}
```


## Where These Docs Need To Live

For the system to work cleanly, each normalized document should exist in two places:

### 1. As a persisted campaign artifact

This gives us:

- history
- approvals
- explicit campaign-level provenance
- deterministic reload behavior

### 2. As a ready Claude context file

This gives the generator prompt layer the documents it already knows how to consume.

That means the normalized payloads should be uploaded through the same context-file path the system uses today.


## The Minimal Working Set

If the goal is "get external creative generation working now," the minimum safe input set is:

- `CampaignDeliveryConfig` with validated external URLs
- `client_canon` / brand context
- `metric_schema`
- `campaign_loaded_angles`
- `campaign_loaded_offer`
- `campaign_loaded_copy`
- `campaign_loaded_copy_context`
- `experiment_specs:{campaign_id}`

Without that set, the external flow is either under-specified or will depend on hidden inference.



## How Valid Creatives Should Be Produced

### Step 1: Validate external delivery

The system validates that the external URLs are real, reachable, public URLs and that the required pages exist.

Output:

- a valid campaign delivery config
- a destination map:
  - `pre-sales -> preSalesUrl`
  - `sales -> salesUrl`
  - optionally `checkout -> checkoutUrl`
  - optionally `thank-you -> thankYouUrl`

### Step 2: Load campaign creative context

The operator loads the campaign’s approved:

- angles
- offer facts
- copywriting
- constraints

Output:

- a campaign-scoped creative context packet
- this becomes the source of truth for brief generation and copy generation

### Step 3: Generate asset briefs

The asset-brief generator uses:

- loaded campaign angles
- loaded offer facts
- loaded copy context
- campaign channels and asset types
- destination types derived from the external flow

It should create briefs that say:

- which angle is being expressed
- which hook is being explored
- which destination type the asset is for
  - `pre-sales`
  - `sales`
  - optionally `checkout`
  - optionally `thank-you`
- which delivery mode applies
  - `external_urls`

Important:

- these briefs should be campaign-scoped
- they should not require `funnelId`
- they should not assume Strategy V2 artifacts exist

### Step 4: Generate ad copy packs

The copy-pack step uses:

- the asset brief
- loaded offer facts
- loaded copywriting
- loaded guardrails
- loaded angle context
- brand/product context

It produces:

- Meta primary text
- Meta headline
- Meta description
- CTA
- claims guardrails

Important:

- this step must treat the loaded campaign docs as the source of truth
- it must not require `strategy_v2_stage3`, `strategy_v2_offer`, `strategy_v2_copy`, or `strategy_v2_copy_context`

### Step 5: Generate creatives

The creative generation step uses:

- the asset brief
- the copy pack
- the selected swipe / visual source system
- loaded campaign constraints
- destination type

This produces:

- image or video creatives
- asset metadata tying the creative back to:
  - asset brief
  - requirement index
  - angle
  - destination type
  - campaign delivery config

At this stage, the creative is valid because:

- the message came from approved loaded inputs
- the creative is labeled with the right destination type
- the campaign delivery config is valid

### Step 6: Prepare Meta specs

The Meta prep step combines:

- generated creative assets
- generated Meta copy pack
- external destination map

For each creative, the system resolves:

- `pre-sales` creatives -> `preSalesUrl`
- `sales` creatives -> `salesUrl`
- optional destination types -> matching URL if configured

It then writes the resolved URL into the Meta creative spec.

This is where the external URL becomes part of the ad that Meta will publish.

### Step 7: Publish to Meta

Publish only needs:

- valid prepared Meta creative specs
- valid prepared Meta ad set specs
- Meta account configuration
- final publish plan validation

At this point, the creative strategy work should already be complete.
Publish should not care whether the inputs originally came from Strategy V2 or from loaded campaign context.
It should only care that the campaign has valid prepared specs.


## What Must Be True For This To Work Cleanly

We need one rule:

**External campaigns must have a first-class campaign creative context that is independent from Strategy V2.**

That means:

- no Strategy V2 launch gate for this path
- no Strategy V2 doc-key dependency for brief generation
- no Strategy V2 doc-key dependency for copy-pack generation
- no Strategy V2-specific artifact lookup in downstream creative execution

Instead, downstream systems should read from a generic campaign context layer.


## Recommended Source Of Truth

For this external-loaded flow, the source of truth should be:

### Canonical delivery source

- `CampaignDeliveryConfig`

### Canonical creative source

- a new campaign-level loaded creative context artifact or record

That loaded creative context should be the place where we store:

- approved angles
- approved offer facts
- approved copy inputs
- campaign messaging guardrails
- operator-selected active message set


## What Needs To Change In The Current System

Today, the codebase is still coupled to Strategy V2 in the creative path.

### Current coupling that must be removed

Asset brief generation currently selects Strategy V2 context docs such as:

- `strategy_v2_stage3`
- `strategy_v2_offer`
- `strategy_v2_copy`
- `strategy_v2_copy_context`

Ad copy pack generation also explicitly expects Strategy V2 context artifacts in the workspace.

So for the external-loaded flow, we need to replace that dependency with loaded campaign inputs.

### Required product change

Add a new campaign-scoped creative context for externally managed campaigns.

The system should support loading:

- angles
- offer facts
- copywriting
- constraints

directly into that context.

### Required execution change

Make both of these steps read from the loaded campaign context:

1. asset brief generation
2. ad copy pack generation

### Required gating change

Replace "Strategy V2 launch context readiness" with "campaign creative context readiness" for this path.

That readiness check should confirm:

- external URLs are valid
- loaded angles exist
- loaded offer facts exist
- loaded copy inputs exist
- required brand / constraint context exists


## Proposed Readiness Contract

An external campaign is downstream-ready when all of the following are true:

### Delivery readiness

- delivery mode is `external_urls`
- required URLs are present
- URL validation succeeded

### Creative-context readiness

- at least one approved angle is loaded
- at least one active campaign angle is selected
- approved offer facts are loaded
- approved copy inputs are loaded
- claims / legal guardrails are loaded
- brand / product context is available

### Generation readiness

- campaign channels are set
- asset brief types are set
- experiment specs or equivalent generation inputs exist


## Minimal Data Model Direction

We do not need to overcomplicate this.

At minimum, the system needs a campaign-level record or artifact like:

- `CampaignCreativeContext`

with payload sections like:

- `angles`
- `offer`
- `copy`
- `brandContext`
- `constraints`
- `selection`

Then downstream flows read from that object instead of Strategy V2 artifacts.


## What "Valid Creative" Means In This Flow

A creative is valid for an external campaign when:

- the destination type is known
- the destination URL is valid for that type
- the message comes from approved loaded angles and copy inputs
- the asset obeys loaded claims and brand guardrails
- the Meta spec points to the correct resolved external URL


## Scope Boundary

This plan is only about replacing the upstream creative-input dependency.

It does **not** require:

- regenerating Strategy V2
- synthesizing angles inside MOS
- using Strategy V2 as the canonical source for external campaigns

It **does** require:

- a way to load creative inputs into the campaign
- a way to mark those inputs approved and active
- downstream generators that consume those loaded inputs directly


## Practical Build Order

1. Define the new campaign creative context schema for loaded external campaigns.
2. Add a way to persist loaded angles, offer facts, copy inputs, and constraints into that context.
3. Add a new readiness check for external-loaded campaigns.
4. Update asset brief generation to use loaded campaign context instead of Strategy V2 docs.
5. Update ad copy pack generation to use loaded campaign context instead of Strategy V2 docs.
6. Keep the existing external destination mapping for Meta review and publish.
7. Validate that prepared Meta specs use the correct external URLs by destination type.


## Bottom Line

Adding an external URL only gives the system a destination map.

To produce valid creatives, the system also needs a loaded campaign creative context containing approved:

- angles
- offer facts
- copywriting
- constraints

For this flow, those inputs must be loaded directly into the campaign and treated as the source of truth.
They should not depend on Strategy V2.


## Current Code Touchpoints

These are the main places where the current implementation is still tied to Strategy V2 or external delivery state:

- asset brief generation context selection:
  - `mos/backend/app/temporal/activities/experiment_activities.py`
- ad copy pack context selection:
  - `mos/backend/app/temporal/activities/asset_activities.py`
- external delivery validation:
  - `mos/backend/app/services/campaign_delivery.py`
- external destination resolution:
  - `mos/backend/app/services/campaign_destinations.py`
- current launch-context gate:
  - `mos/backend/app/services/campaign_launch_context.py`
- Meta review setup and destination URL materialization:
  - `mos/backend/app/routers/campaigns.py`
- Meta publish validation:
  - `mos/backend/app/routers/meta_ads.py`
