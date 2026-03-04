# Headline Writing Engine — Execution Flow

## What This Is

This is the step-by-step execution sequence the copywriting agent follows when writing headlines. It is NOT a replacement for WORKFLOW.md — it is the operating procedure that ensures WORKFLOW.md is actually used correctly.

The previous failure mode: generating headlines with raw prompts that ignored the awareness-level routing (S5), the page-type calibration (WORKFLOW.md Section 4), the archetype system (Section 3), and the message-match chain (Section 7). This produced 150 generic fear hooks that all sounded the same and didn't match any real page function.

---

## Required Inputs

Before writing a single headline, the agent must have ALL of the following:

| Input | Source | What It Provides |
|-------|--------|-----------------|
| **Awareness level** | Task brief or S5 routing table | Which of the 5 levels this reader is at |
| **Page type** | Task brief | Listicle, advertorial, or sales page |
| **Angle** | Task brief or angle engine | The specific angle being used (e.g., "dosage", "drug interactions") |
| **Angle framing for this awareness level** | `shared/awareness-angle-matrix.md` | How this angle frames at this specific awareness level |
| **S5 copy construction rules** | Section 5.2 | Lead strategy, headline formula, section emphasis, proof approach, agitation ceiling for this level |
| **Page-type specs** | WORKFLOW.md Section 4 | Word count, tone, structure, CTA alignment for this page type |
| **Angle-specific VOC data** | Offer agent / VOC synthesizer | High-quality voice-of-customer quotes, phrases, and language patterns specific to this angle — the reader's actual words about this problem, their fears, their private behaviors, their frustrations. This is the raw material for emotional triggers and relevance signals. |
| **Upstream headline** (if applicable) | Task brief | The ad headline or presale headline that precedes this page — for message-match |

**If any input is missing, STOP and request it.** Do not generate headlines without a confirmed awareness level and page type.

**Note on VOC data:** The offer agent provides angle-specific VOC as a standard output. This is not optional flavor text — it is primary source material. The reader's own language is always more emotionally precise than anything the copywriter invents. Mine the VOC for: exact phrases she uses to describe the problem, private behaviors she admits to, identity language ("I'm the kind of person who..."), and emotional confessions. These become the raw inputs for the Emotional Trigger Rule in Step 4.

---

## Step 1: Load Context (Before Writing Anything)

Load and internalize — do not skim, do not summarize, actually read:

1. **S5 Section 5.2** — the per-level copy construction rules for the confirmed awareness level
2. **WORKFLOW.md Section 4** — the page-type calibration spec for the confirmed page type
3. **WORKFLOW.md Section 3** — the archetype table, filtered to archetypes that match BOTH the awareness level AND the page type
4. **`shared/awareness-angle-matrix.md`** — the angle framing entry for this angle × awareness level
5. **`shared/audience-product.md`** — the audience and product details
6. **`shared/brand-voice.md`** — banned words, voice rules, emotional registers
7. **Angle-specific VOC data** — the voice-of-customer quotes, phrases, and language patterns from the offer agent for this angle

Extract and hold in working memory:

```
WORKING_LEVEL: [e.g., "Problem-Aware"]
PAGE_TYPE: [e.g., "Advertorial"]
ANGLE: [e.g., "dosage"]

FROM S5:
  - Headline formula: [e.g., "Problem-crystallization. Articulates the problem better than the reader can."]
  - Lead strategy: [e.g., "First 100 words must name the specific problem clearly and validate it."]
  - Agitation ceiling: [e.g., "Level 3 of 5"]
  - What to avoid: [e.g., "Do not skip the solution-category step and jump straight to the product."]
  - Agent directive: [e.g., "Prove you understand their problem better than anyone else does."]

FROM WORKFLOW.MD SECTION 4:
  - Word count: [e.g., "10-18 words"]
  - Tone: [e.g., "Third-person journalistic or first-person discovery. Must pass 'would a magazine print this?' test."]
  - Primary Laws: [e.g., "Law 1 (Open Loop), Law 3 (Unique Mechanism), Law 6 (Credibility)"]
  - Best archetypes: [e.g., "Contrarian Claim, Expert Insight, Story/Anecdote"]

FROM AWARENESS-ANGLE-MATRIX:
  - Frame: [e.g., "Educational. Names the problem directly: most herb guides don't include dosing amounts."]
  - Headline direction: [e.g., "Problem-crystallization — articulates the problem better than the reader can."]
  - Entry emotion: [e.g., "Vague anxiety — she knows something is off but can't name it"]
  - Exit belief: [e.g., "I need a reference that includes real amounts, not just herb names."]

FROM VOC DATA (angle-specific):
  - Key phrases: [e.g., "I just eyeball the dropper and hope it's close enough", "every website says something different"]
  - Private behaviors: [e.g., "Googling the same herb at midnight", "giving kids chamomile without knowing the right amount"]
  - Identity language: [e.g., "I'm careful about what my family puts in their bodies"]
  - Emotional confessions: [e.g., "I wasted so much time and mental energy to research these things"]
```

---

## Step 2: Select Archetypes

From the archetype table (WORKFLOW.md Section 3), identify which archetypes are valid for this awareness level × page type combination.

**Rules:**
- Only use archetypes whose "Best Awareness Level" column includes the WORKING_LEVEL
- Only use archetypes whose "Best Page Type" column includes the PAGE_TYPE
- If generating a HookBank (10+ headlines), must use at least 4 different archetypes
- No single archetype may exceed 30% of the bank
- At least 1 headline must use archetype 5 (Safety Warning) or 9 (Expert Insight)

**Write down the valid archetypes before generating:**
```
Valid archetypes for [WORKING_LEVEL] + [PAGE_TYPE]:
  - #X: [Name] — [why it fits]
  - #Y: [Name] — [why it fits]
  - ...
```

---

## Step 3: Select Formulas

From the 30 headline formulas (WORKFLOW.md Section 9), identify which formulas match the WORKING_LEVEL.

**Rules:**
- Only use formulas whose "Best Awareness Level" column includes the WORKING_LEVEL
- Only use formulas whose "Best Page Type" column includes the PAGE_TYPE
- Select 5-8 formulas to use as structural starting points

**Write down the selected formulas before generating.**

---

## Step 4: Write Headlines

Now — and ONLY now — write headlines.

### The Open Loop Prime Directive

This is the #1 structural requirement of every headline this engine produces. It is not one of several laws. It is THE law. Everything else — emotional triggers, archetypes, formulas, page-type calibration — is built on top of this foundation.

**Every headline must create an open loop so clear that the reader's brain completes the question in one word: *What?* or *Which?* or *Why?***

That's the test. Read the headline, and ask: what is the single, obvious, instant question the reader cannot help but ask? If you can state that question in one or two words, the loop works. If you need a paragraph to explain why it's an open loop, it's not one.

**How it works:**

The open loop is an incomplete piece of information that the reader's brain treats as an unresolved need. The anterior cingulate cortex detects the gap. Dopaminergic salience networks fire. The reader experiences a pull that feels like mild discomfort — they MUST resolve it. The only way to resolve it is to keep reading.

**The clarity standard:**

| Headline | Loop question | Verdict |
|----------|--------------|---------|
| "The most dangerous thing missing from 90% of herb guides" | What is it? | ✓ CLEAR |
| "After reviewing 300 herbs, one safety problem showed up in every guide" | What problem? | ✓ CLEAR |
| "She eyeballed her kids' elderberry dose for two years. Then she measured it." | ...what happened? Is it "what happened when she measured?" or "was she way off?" | ✗ UNCLEAR — multiple possible loops, none instant |
| "5 Herbal dosing mistakes that quietly change what the herb does to your body" | Which 5? What does it change? | ✗ SPLIT — two loops competing, neither dominant |

**Rules:**

1. **One loop per headline.** Not two. Not a loop and a half. One clean gap that the reader's brain locks onto instantly. If you have two potential loops, pick the stronger one and kill the other.

2. **The loop must be answerable by the page content.** An open loop the page can't close is a trust violation. The loop promises specific information. The page must deliver it.

3. **The loop must be front-loaded.** The reader should hit the gap within the first 8 words. If the open loop is buried at the end of an 18-word headline, most readers never reach it.

4. **The loop must create genuine information hunger, not confusion.** "The thing about herbs that nobody understands" is vague — the reader doesn't know what kind of information they're missing. "The one number your herb guide doesn't give you" is specific — the reader knows EXACTLY what type of information they need and that they don't have it.

5. **If you have to explain why it's an open loop, it's not an open loop.** This is the kill test. Every headline must pass it. No exceptions.

**The open loop is the engine that pulls the reader into the page. The emotional trigger is what makes them care. The archetype is the frame. The formula is the structure. But without the loop, nothing else matters — because the reader never gets past the headline.**

---

### The Emotional Trigger Rule (Punch in the Gut)

Every headline must land an emotional hit. Not hype. Not fear-porn. A gut-level recognition moment — the reader feels *caught*. She reads it and her stomach drops half an inch because she knows this is about her, right now, and she can't look away.

**How to engineer the punch:**

1. **Name the private behavior she hasn't said out loud.** Not the problem in general — the specific thing she does at 10pm that she'd be embarrassed to admit. "Googling the same herb dose for the third time." "Eyeballing a dropper and hoping it's close enough." "Giving her kid chamomile tea and quietly wondering if it's too much."

2. **Use concrete sensory detail, not abstract emotion words.** Don't write "feeling anxious about dosing." Write "staring at the dropper wondering if 15 drops or 25 drops is right for a 40-pound kid." The image does the emotional work. The reader's own memory fills in the feeling.

3. **Hit the identity nerve.** She sees herself as careful, responsible, research-oriented. The punch comes from the gap between that identity and what she's actually doing — guessing. The headline surfaces that gap without shaming her. It says "you're doing this thing" and she thinks "...yeah, I am."

4. **Test:** Read the headline and ask — does this make the reader's breath catch, even slightly? Does she feel *seen* in a way that's uncomfortable but not hostile? If the headline is informational but emotionally flat, it fails this test. Rewrite until it lands.

**What the punch is NOT:**
- Catastrophizing ("Your child could be in danger!")
- Guilt-tripping ("You're a bad parent if...")
- Vague emotional words ("scary," "terrifying," "alarming")
- Manufactured urgency that doesn't exist

The punch respects the reader. It earns the emotional response by being *specific and true*, not by being loud.

### Core Directives

These three directives govern every headline this engine produces. They are not suggestions. They are the quality standard.

**Directive 1: Leverage real emotional levers.**
Pain, fear, identity loss, shame, and frustration are legitimate copywriting tools — use them. The reader arrived with these emotions already active. The headline's job is to name them precisely, not avoid them. A headline that is informational but emotionally inert is a failed headline. Every headline must pull on at least one of these levers:
- **Pain** — the ongoing daily cost of the problem (guessing, second-guessing, contradictory info)
- **Fear** — what could go wrong if she keeps operating without the right information
- **Identity loss** — the gap between who she thinks she is (careful, informed) and what she's actually doing (winging it)
- **Shame** — the private behavior she wouldn't post about publicly (Googling the same thing for the fifth time, not knowing basic dosing for herbs she gives her kids daily)
- **Frustration** — the system that has failed her (conflicting sources, incomplete guides, garbage info online)

Pick the lever that fits the angle and the awareness level. Do not water it down. Respect the agitation ceiling from S5, but within that ceiling, hit hard.

**Directive 2: Write like a top-performing advertorial or VSL headline.**
The output must feel like it belongs on a page that converts — short, punchy, high clarity. Not academic. Not corporate. Not "content marketing." These are direct response headlines that happen to live on editorial-framed pages. They should read like the best-performing native ad headlines and VSL hooks in the health/wellness space — the ones with real CTRs, not the ones copywriters put in their portfolio to look clever. Specifically:
- Favor short words over long words
- Favor concrete over abstract
- Favor one sharp idea over two decent ideas
- Favor the reader's language (from VOC) over the copywriter's language
- If it sounds like it was written by a copywriter, rewrite it until it sounds like it was said by the reader's frustrated inner voice

**Directive 3: No clickbait without DR structure.**
Every headline must have real direct response architecture underneath it. A curiosity gap without a payable promise is clickbait. A fear hook without a relevance signal is fearmongering. A punchy phrase without an implicit promise is a bumper sticker. The 3-component anatomy (pattern interrupt + relevance signal + implicit promise) is non-negotiable — but the anatomy must be loaded with emotional weight, not just structural correctness. A headline can pass every structural check and still be dead on arrival if it doesn't make the reader *feel* something. Structure is the skeleton. Emotion is the muscle. You need both.

---

**For each headline, follow this construction sequence:**

1. **Start with the open loop.** Before anything else, define the single gap this headline opens. Write it as a one-word question: *What?* *Which?* *Why?* If you can't state the loop question in one or two words, stop and rethink. The loop is the spine of the headline — everything else wraps around it.
2. **Quick payability check.** Can the page type (from Section 2 template) actually deliver what this open loop promises? If the headline promises physiological information but the advertorial template produces a belief-chain funnel with no room for that content, the loop is unpayable for this page type. Either modify the headline or plan a body modification to accommodate the promise. Do not proceed with an unpayable loop.
3. **Pick an archetype** from the valid list (Step 2)
4. **Pick a formula** from the selected list (Step 3) as the structural starting point
5. **Apply the angle framing** from the awareness-angle-matrix — use the frame and headline_direction to shape the content
6. **Apply the emotional trigger** — identify the private behavior, concrete detail, or identity-gap that delivers the gut punch for this angle
7. **Build the 3-component anatomy around the loop:**
   - Pattern interrupt — what stops the reader? (Must carry emotional weight, not just novelty)
   - Relevance signal — what tells them "this is for me"? (Must match awareness level per S5)
   - Implicit promise — the open loop IS the implicit promise. The reader continues because the loop demands resolution.
8. **Check against S5 constraints:**
   - Does it follow the headline formula for this awareness level?
   - Does it respect the agitation ceiling?
   - Does it avoid the "what to avoid" items?
   - Does it serve the agent directive?
9. **Check against page-type specs:**
   - Word count within range?
   - Tone matches? (Editorial for listicle, journalistic for advertorial, direct for sales page)
   - "Would a magazine print this?" test (advertorial only)
10. **Check which Laws are demonstrated** — must follow at least 3 of 7
11. **Final loop clarity test.** Read the finished headline one more time. State the loop question in one word. If you hesitate, rewrite.

**Tag each headline as you write it:**
```
HEADLINE: [text]
ARCHETYPE: [# and name]
FORMULA: [# and name]
AWARENESS LEVEL: [level]
LAWS: [list]
ENTRY EMOTION: [from angle matrix]
EXIT BELIEF: [from angle matrix]
PROMISE_CONTRACT:
  LOOP_QUESTION: [the one-word question from step 1]
  SPECIFIC_PROMISE: [what information/content the reader expects to find on the page]
  DELIVERY_TEST: [falsifiable boolean starting with "The body must contain..."]
  MINIMUM_DELIVERY: [which Section 2 template section must begin paying, which must complete]
```

---

## Step 4.5: Extract Promise Contract

For every headline written in Step 4, extract its Promise Contract. This step is mandatory. A headline without a Promise Contract is incomplete and cannot be shipped to a page writer.

**For each headline:**

1. **LOOP_QUESTION** — already defined in Step 4, item 1.

2. **SPECIFIC_PROMISE** — answer the question: "If the reader clicked this headline, what specific information or content would she expect to find on the page?" Write the answer as a concrete description. Not "useful information about dosing" — but "specific physiological consequences of incorrect herbal dosing."

3. **DELIVERY_TEST** — convert the SPECIFIC_PROMISE into a falsifiable boolean test that starts with "The body must contain..." This test must be specific enough that someone reading only the body text (without the headline) can determine pass or fail.

4. **MINIMUM_DELIVERY** — using the Section 2 template for this page type, identify which section must begin paying off the promise and which section must complete it. The promise must begin being paid off BEFORE the structural pivot to the product or solution category.

**The Red Flag Test:**

If the SPECIFIC_PROMISE describes a different article than the one the Section 2 template would produce, STOP. Either:
- The headline is wrong for this page type — pick a different headline from the HookBank
- The page body needs a structural modification to accommodate the promise — plan that modification before drafting
- The headline's open loop needs to be reframed so its promise aligns with what the page can deliver

A headline that opens a loop the page cannot close is a trust violation. The Promise Contract catches this BEFORE the page is written, not after.

**Promise Contract Quality Rules:**

1. Every headline must have a PROMISE_CONTRACT. Not optional metadata — a structural requirement.
2. The DELIVERY_TEST must be concrete enough that two different writers would agree on whether the body satisfies it. "The reader learns something useful" fails. "The body must contain at least one named physiological consequence of incorrect herbal dosing" passes.
3. If the DELIVERY_TEST cannot be written as a concrete, falsifiable assertion, the headline has a structural problem — the open loop is too vague or the page type cannot accommodate the promised content.

---

## Step 5: HookBank Differentiation (When Delivering 5+ Headlines)

Run the differentiation check (WORKFLOW.md Section 8):

- [ ] Every headline differs from every other on at least 2 of 4 dimensions (archetype, entry angle, belief targeted, emotional register)?
- [ ] At least 4 different archetypes used?
- [ ] At least 3 different beliefs from B1-B8?
- [ ] At least 3 different emotional registers (clinical, empathetic, provocative)?
- [ ] At least 1 Safety Warning or Expert Insight archetype included?

If any threshold is not met, replace headlines until all pass.

---

## Step 6: Quality Gate (Optional — Scorer)

If the deterministic scorer is being used:
1. Run `headline_scorer_v2.py` with correct `--page-type` flag
2. Hard gate check (BC1, BC2, BC3) — any failure = rejected
3. If score < target tier, use fix_hints to revise
4. The scorer is a secondary check, not the primary quality control — Steps 1-6 are the primary quality control

---

## What This Engine Does NOT Do

- **Does not generate headlines without loading context first.** No "give me 25 headlines" without confirmed awareness level, page type, and angle.
- **Does not treat all page types the same.** An advertorial headline is not a sales page headline is not a listicle headline.
- **Does not treat all awareness levels the same.** A problem-aware headline is structurally and tonally different from a product-aware headline.
- **Does not optimize for a scorer at the expense of strategic fit.** A headline that scores 90% but targets the wrong awareness level is worse than a headline that scores 75% but nails the reader's state.
- **Does not generate in bulk without differentiation.** 50 headlines that all sound the same is 1 headline repeated 50 times.
- **Does not ship headlines without a Promise Contract.** A headline without a testable DELIVERY_TEST is incomplete. The Promise Contract is what connects the headline to the page body — without it, the headline is an open loop with no guarantee of closure.

---

## Quick Reference: The Professional DR Marketer's Mental Model

Before writing any headline, the DR marketer asks herself 5 questions:

1. **Who is reading this?** → awareness level (S5)
2. **Where are they reading it?** → page type (WORKFLOW.md Section 4)
3. **What do they already believe?** → entry emotion (awareness-angle-matrix)
4. **What must they believe after?** → exit belief (awareness-angle-matrix)
5. **What's the one thing I'm saying?** → angle framing (awareness-angle-matrix)

The headline is the answer to all 5 simultaneously.
