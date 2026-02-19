# Funnel Page AI (Non-Technical Overview)

This document explains, in plain language, how MOS uses AI to create and update funnel pages.

## The Primitives

- **AI agent**: the “writer + editor” that can create a page draft for you.
- **Tools**: the agent’s approved actions (load your product info, generate images, save a draft, etc.).
- **Workflows**: the step-by-step ways the agent uses tools to get a job done.

## What This Agent Is For

This agent helps you turn a prompt like “make this page more persuasive” into a saved **draft** of a funnel page in MOS.

It is designed to:

- use your saved **product/offer** info instead of inventing details
- follow your **brand** (logo/colors) when that data exists
- keep “template pages” structurally intact (it edits inside the template instead of rebuilding the whole thing)

## The Two Things It Does (Workflows)

### 1) Draft a Page (Words + Structure)

Goal: produce a coherent page draft that fits your funnel and the page type you’re editing.

What happens:

1. The agent loads the funnel/page it’s working on and (if it exists) the most recent draft as a starting point.
2. It loads product and offer context (so pricing/options/claims match what’s configured).
3. If you have brand documents saved for the workspace, it pulls those in and treats them as “source of truth”.
4. It writes or edits the page draft:
   - In “template mode” (Sales PDP, Pre-sales listicle), it keeps the template’s building blocks and only edits the content/config inside them.
   - In non-template mode, it’s freer to create a page layout from scratch.
5. It runs checks so the output won’t break the editor or runtime (and it errors rather than guessing when key requirements are missing).

What you get:

- a short `assistantMessage` summary (for chat UI)
- a full page draft (the structured page content MOS uses to render/edit)

### 2) Make the Draft Visually Complete (Images + Brand Consistency)

Goal: ensure the draft has usable images and brand consistency, then save it.

What happens:

1. The agent applies “cleanup” rules that make drafts consistent and usable:
   - ensures your brand logo shows up where expected (when available)
   - nudges product images and icon prompts into a consistent style
   - enforces template-specific requirements (for example, some Sales PDP fields must exist)
2. If image generation is enabled, it looks for every image slot that needs a real asset and decides:
   - use stock imagery (Unsplash) when that’s appropriate
   - generate a custom image when stock won’t fit
3. It generates the needed image assets (up to a hard cap per page), fills the page with the resulting asset ids, and records what happened.
4. It saves the result as a new draft version in MOS.

What you get:

- a saved draft version (so the page is ready for review)
- a list of generated images (or errors, if image generation fails)

## The Agent’s Tools (In Plain Language)

Think of tools as the agent’s “approved buttons” it can press. In MOS, the tool-based version of this agent uses tools that map to actions like:

- Load “what page are we editing?” and “what’s the starting point?” (`context.load_funnel`)
- Load “what are we selling and how is checkout configured?” (`context.load_product_offer`)
- Load brand style tokens (logo id, colors, etc.) (`context.load_design_tokens`)
- Load saved brand docs that should override guesswork (`context.load_brand_docs`)
- Write or revise the page draft (`draft.generate_page`)
- Apply consistency rules (brand logo placement, product image handling, template-specific fixes) (`draft.apply_overrides`)
- Validate the result before saving (fail fast with clear errors) (`draft.validate`)
- Find every image slot that needs to be filled (`images.plan`)
- Generate/fetch images and attach them to the draft (`images.generate`)
- Save the draft version and record what happened (`draft.persist_version`)

## Guardrails You’ll Notice

- **It refuses to guess** when critical data is missing (for example: missing product config for checkout on Sales PDP).
- **It limits image generation per page** (to avoid runaway generations).
- **It treats brand docs and image attachments as model-dependent**:
  - some features require a model that supports them (and the system errors if you try to use them with an incompatible model)
- **It won’t “make up” attachment ids**: if you reference an attached image, it must be a real asset MOS can load.

## A Few Practical Examples

- If you ask for “a Sales PDP page”:
  - the agent will keep the Sales PDP template structure and edit the content inside it, instead of redesigning the whole page.
- If the page has many missing images:
  - the agent will plan them all, but it will refuse to generate more than the allowed cap for a single page.
- If you attach reference images:
  - the agent can place them as-is or use them as inspiration for new images, but it will error if the attachment can’t be loaded as a real image asset.

## Where This Lives (Code Pointers)

- Core generator (legacy “one-shot” implementation): `mos/backend/app/services/funnel_ai.py`
- Tool-based agent orchestration: `mos/backend/app/agent/funnel_objectives.py`
- Tool implementations: `mos/backend/app/agent/funnel_tools.py`
