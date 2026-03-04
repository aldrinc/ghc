# Headline Engineering System

## Workflow Metadata

| Field | Value |
|-------|-------|
| **Workflow ID** | `headline-engineering` |
| **Replaces** | Section 7 (Hook Construction Framework) |
| **Shared context required** | `brand-voice.md`, `compliance.md`, `audience-product.md` |
| **Eval** | `eval/headline_scorer_v2.py` (deterministic, 28 tests, 40 pts), `eval/headline_qa_loop.py` (LLM auto-fix) |
| **Input schema** | `schema/input.json` |
| **Output schema** | `schema/output.json` |
| **Reference files** | `reference/dr-headline-engine.md`, `reference/100-greatest-analysis.md`, `reference/platform-adaptation.md` |
| **Cross-references** | Section 1 (awareness levels, B1-B8 belief chain, agitation calibration), Section 3 (brand voice, banned words, emotional register map), Section 4 (FDA compliance, prohibited claims, banned phrases), Section 5 (traffic source routing, per-level copy rules) |
| **Conflict resolution** | Section 4 (compliance) > Section 3 (voice) > this document |

---

## 1. Hook Anatomy (3 Required Components)

Every headline produced under this brand contains exactly three components. If any component is missing, the headline fails the construction check and must be rewritten.

### Component 1: Pattern Interrupt

The element that stops the scroll. This is the first cognitive disruption -- it breaks the reader's default state (scrolling, skimming, deleting) by introducing something unexpected enough to pause on.

**Neuroscience basis:** The pattern interrupt exploits the **orienting response** -- a reflexive attentional shift toward novel or survival-relevant stimuli. This is mediated by the locus coeruleus-norepinephrine system, which floods the cortex with norepinephrine when novelty or threat is detected, producing heightened alertness and focus. The prospect's reticular activating system (RAS) is filtering out roughly 99% of incoming stimuli; the headline must pass through this filter by triggering either threat detection or reward prediction.

For this brand, the interrupt must operate within the anti-hype register.

**Approved interrupt mechanisms:**
- A specific, counterintuitive claim grounded in evidence ("Most chamomile tea is brewed wrong for sleep")
- A concrete, vivid detail that creates instant imagery ("The herb sitting in your spice rack that interacts with blood thinners")
- A calm contradiction of popular belief ("Elderberry is not for every immune situation")
- A question the reader's mind answers involuntarily ("Do you know which three herbs in your cabinet have real drug interactions?")

**Banned interrupt mechanisms:** Shock language, catastrophizing, ALL CAPS words, emoji-as-interrupt, fabricated statistics, conspiracy framing. Permanently disqualified per Section 3 anti-patterns and Section 4 compliance rules.

### Component 2: Relevance Signal

The element that tells the reader "this is for me." Without a relevance signal, the pattern interrupt captures attention that immediately dissipates. The relevance signal anchors the interrupt to the reader's identity, situation, or felt problem.

**Neuroscience basis:** The relevance signal activates the **default mode network** -- the brain's self-referential processing circuits. When the reader's mind maps the content to their own identity or situation, engagement deepens from surface attention to personal involvement.

**Approved relevance mechanisms:**
- Identity marker ("If you keep herbs at home but second-guess every dose...")
- Situation specificity ("You have searched three different websites for the same herb and gotten three different answers")
- Problem naming at the reader's awareness level (per Section 5.2 lead strategy rules)

**Rule:** The relevance signal must match the awareness level of the target audience. An Unaware audience gets identity or emotional-state signals. A Problem-Aware audience gets situation-specific signals. A Product-Aware audience gets product-referencing signals. Mismatch between relevance signal and awareness level is a construction failure.

### Component 3: Implicit Promise

The element that tells the reader what continuing gives them. This is the forward pull -- it answers the subconscious question "Why should I keep reading?" without making an explicit claim.

**Neuroscience basis:** The implicit promise creates a **curiosity gap** that activates the brain's opioid-seeking circuits (Loewenstein's information-gap theory). The brain treats unresolved information gaps similarly to unresolved physical needs, driving the prospect to continue reading to resolve the tension.

**Approved promise mechanisms:**
- A benefit framed as information ("...and the one safety check that changes how you use it")
- A curiosity gap with payoff potential ("...but there is one thing most herbal guides leave out")
- A mechanism tease ("...until you understand how it actually interacts with your body")
- A resolution signal ("Here is how to know for certain")

**Rule:** The implicit promise must be payable. If the hook promises information, the copy must deliver that information. If it opens a curiosity gap, the copy must close it. An implicit promise that goes unpaid is a trust violation and is banned under Section 3 anti-pattern #12.

**Enforcement:** The Promise Contract (HEADLINE-ENGINE.md Step 4.5) is the enforcement mechanism for this rule. Every headline ships with a DELIVERY_TEST — a concrete, falsifiable specification of what the page body must contain to pay off the implicit promise. The contract is created at headline-writing time and verified after the page body is written using the headline-body congruency scorer. This converts "payable" from a construction intent into a testable gate.

### The Construction Formula

```
[Pattern Interrupt] + [Relevance Signal] + [Implicit Promise]
```

The three components may appear in any order and may be woven into a single sentence or spread across two to three sentences. The formula is a checklist, not a sentence template. All three must be verifiable in the finished headline.

### Brand-Calibrated Examples

**All three in one sentence:**
"If you use herbs with your family but still Google every dose at midnight, this reference changes that."
- Interrupt: "Google every dose at midnight" -- vivid, specific.
- Relevance: "use herbs with your family."
- Promise: "this reference changes that."

**Spread across two sentences:**
"Most herbal guides skip the part where things go wrong. This one starts there."
- Interrupt: "skip the part where things go wrong."
- Relevance: implied -- the reader who worries about safety.
- Promise: "This one starts there" -- the resource that addresses what others avoid.

**Question-led:**
"Do you actually know which herbs in your kitchen interact with common medications?"
- Interrupt: the question itself, forcing internal response.
- Relevance: "herbs in your kitchen" -- identity of a home herbalist.
- Promise: implied -- continue and you will find out.

---

## 2. The 7 Laws of Headline Engineering

These seven laws govern every headline decision. A headline that violates any law is weakened; a headline that follows all seven is exceptional. At minimum, every headline must demonstrably follow at least 3 of the 7 laws.

### Law 1: Open Loop Engineering (PRIME DIRECTIVE)

**Status:** This is not one of seven equal laws. This is the prime directive. Every headline must create an open loop. The other six laws are applied on top of this foundation. A headline that follows Laws 2-7 perfectly but has no open loop is a failed headline — the reader never gets past it.

**Principle:** Create cognitive tension via a single, clear, instantly obvious information gap. The headline opens a loop that the reader's brain demands to close. The reader should be able to state the loop as a one-word question: *What?* *Which?* *Why?*

**The clarity standard:** If you need a paragraph to explain why the headline has an open loop, it doesn't have one. The loop must be so obvious that any reader feels it instantly — no interpretation required, no mental gymnastics, no "well, the loop is sort of about..."

**Why it works:** Loewenstein's information-gap theory demonstrates that the brain treats unresolved information gaps similarly to unresolved physical needs. The anterior cingulate cortex detects the gap, and dopaminergic salience networks fire not from reward but from information-seeking motivation. The reader feels compelled to continue.

**Brand-calibrated examples:**

"The most dangerous thing missing from 90% of herb guides"
- Loop: What is it? (One word. Instant. Irresistible.)

"After reviewing 300 herbs, one safety problem showed up in almost every guide on the market"
- Loop: What problem? (Two words. Crystal clear.)

"The reason you can't find a straight answer on herbal dosing has nothing to do with the herbs"
- Loop: Then what? (The negation creates the gap — it ISN'T the obvious thing, so what IS it?)

**Loop quality test:**
| Loop Question | Verdict |
|---------------|---------|
| "What?" / "Which?" / "Why?" | ✓ PASS — one-word question, instant gap |
| "What happened? Was she way off? How bad was it?" | ✗ FAIL — multiple possible questions, no single clear gap |
| "Hmm, I guess the loop is about..." | ✗ FAIL — if you have to guess, there's no loop |

**Rules:**
1. One loop per headline. Not two competing loops. One clean gap.
2. The loop must be answerable by the page content (unpaid curiosity = trust violation).
3. The loop should be front-loaded — the gap should land within the first 8 words.
4. The loop must create information hunger, not confusion. Specific > vague.
5. Do not use "They don't want you to know" conspiracy framing (Section 3 ban).
6. Do not fabricate the gap -- the withheld information must be real and worth knowing.

### Law 2: Pain Naming

**Principle:** Name the wound before offering the bandage. Call out the struggle, name the enemy, validate the conflict. The reader must feel recognized before they will listen.

**Why it works:** Pain naming activates the anterior insula (anticipated negative outcomes) and amygdala (threat tagging), creating aversive motivation -- the drive to escape a negative state. This is neurochemically distinct from and generally stronger than the drive to approach a positive one. Critically, pain naming also externalizes blame, relieving the prospect of shame. Shame shuts down buying behavior; blame-shifting opens it up.

**Brand-calibrated example:**
"You want to use herbs for your family. But every source you find contradicts the last one."
- Names the pain precisely: contradictory information, not ignorance.
- Validates the struggle without blaming the reader.

**What NOT to do:**
- Do not agitate above level 3 on the Section 1 agitation scale.
- Do not name specific diseases or imply diagnosis (Section 4 violation).
- Do not catastrophize -- the tone is protective concern, not alarm.
- Do not shame the reader for their current behavior.

### Law 3: Unique Mechanism Promise

**Principle:** Promise a result they have never heard said this way before. Add a mechanism to make it novel and credible. The mechanism answers "why will this work when other things haven't?"

**Why it works:** The left-hemisphere interpreter compulsively constructs causal narratives. When you provide a mechanism, the brain seizes on it with something close to relief. The "aha" moment triggers a dopamine release in the nucleus accumbens (the "eureka effect"), creating a positive association with the explanation itself. The mechanism must hit the plausibility window -- novel enough to feel like a genuine insight, logical enough to pass analytical scrutiny.

**Brand-calibrated example:**
"Why most herb-drug interaction charts are missing the 3 factors that actually determine your risk."
- The mechanism: "3 factors that actually determine your risk" -- novel, specific, credible.
- Implies existing resources are incomplete, positioning this one as superior.

**What NOT to do:**
- Do not promise health outcomes or cures (Section 4: structure/function claims only).
- Do not use "miracle," "breakthrough," or "revolutionary" (Section 3 banned words).
- Do not make the mechanism so complex it overwhelms working memory.

### Law 4: Specificity Creates Trust

**Principle:** Concrete numbers, unusual numbers, descriptors, and timeframes outperform vague claims in every split test. Specificity signals insider knowledge and activates the brain's evidence-evaluation circuits.

**Why it works:** The dorsolateral prefrontal cortex processes specific claims as evidence, while vague claims are processed as opinion and discounted. Unusual numbers (e.g., "143 herbs" rather than "over 100 herbs") are more believable because they imply precision measurement rather than estimation. Specificity also creates vividness, which triggers the vividness bias -- concrete, imageable information disproportionately influences judgment.

**Brand-calibrated example:**
"300+ herbs. Safety flags for every one. Dosing references you can actually trust. One book, $49."
- Every element is concrete: 300+, every one, one book, $49.
- No vague claims; every promise is verifiable.

**What NOT to do:**
- Do not fabricate or inflate numbers.
- Do not use round numbers when exact numbers are available (exact > round).
- Do not stack too many numbers in one headline (cognitive overload).

### Law 5: Simplicity Is Persuasion

**Principle:** Short words, short phrases, linear structure, no multi-clause sentences. The headline must be understood in a single pass. If the reader has to re-read it, you have lost them.

**Why it works:** Working memory holds approximately 4 chunks of information simultaneously (Cowan, 2001). Multi-clause headlines exceed this capacity, forcing re-reading and triggering the dorsal anterior cingulate cortex's conflict-monitoring function -- which can halt the engagement sequence. Simple structures also favor System 1 processing (fast, automatic), which is where initial engagement decisions are made.

**Brand-calibrated example:**
"This one starts there." (5 words, one idea, instant comprehension.)

**What NOT to do:**
- Do not use semicolons, em-dashes connecting independent clauses, or nested subordinate clauses.
- Do not pack multiple claims into one headline.
- Do not use jargon, Latin terms, or technical vocabulary the audience does not already know.
- Do not write headlines that require context to understand.

### Law 6: Credibility Signals

**Principle:** Reference sources, real events, measurable outcomes, or personal experiences. Ground every claim so the reader's analytical brain has something to hold onto.

**Why it works:** Authority-mediated cognitive offloading -- the brain reduces its own analytical processing when credible signals are present (Klucharev et al., 2008). Expert opinions modulate activity in the ventral striatum (reward processing), making endorsed options feel more rewarding at a neurological level. Credibility signals prevent the dorsolateral prefrontal cortex from flagging the headline as unsubstantiated, which would trigger skepticism and disengagement.

**Brand-calibrated example:**
"After reviewing over 300 herbs through the lens of published safety research, here is what we found most guides get wrong."
- Credibility signals: "300 herbs," "published safety research," "we found."
- Positions the author as rigorous researcher, not guru.

**What NOT to do:**
- Do not inflate or fabricate credentials (Section 3, B2 rules).
- Do not use "leading expert" or "world-renowned" language.
- Do not reference studies that do not exist.
- Do not use testimonials that imply health outcomes without required disclaimers (Section 4).

### Law 7: Time Compression

**Principle:** Shorter timeframes create stronger desire. When a result can be framed within a compressed timeline, it becomes more compelling because the brain overweights near-term outcomes.

**Why it works:** Temporal discounting -- the brain has two competing valuation systems. The prefrontal/deliberative system values long-term outcomes rationally. The limbic/immediate system (ventral striatum, amygdala) dramatically overweights present-tense gains and losses. Compressed timeframes shift the decision from the deliberative system to the immediate system, where urgency overrides hesitation.

**Brand-calibrated example:**
"The 5-minute safety check to run before giving any herb to your child."
- Time compression: "5-minute" makes it feel immediately actionable.
- The reader can imagine doing this today.

**What NOT to do:**
- Do not compress timelines dishonestly (Section 4: no false timeframe claims).
- Do not promise health transformations within timeframes ("Cure X in 7 days" -- Section 4 violation).
- For this brand, time compression applies to information access and safety checks, not health outcomes.

---

## 3. Headline Archetypes

Nine archetypes calibrated to the brand's anti-hype positioning, the audience's trust-first psychology, and Section 4 compliance constraints. When generating a HookBank, the agent must use at least 4 different archetypes and allocate no more than 30% of hooks to any single archetype.

| # | Archetype | Description | Best Awareness Level | Best Platform | Best Page Type | Primary Laws | Example (Brand Voice) | When NOT to Use |
|---|-----------|-------------|---------------------|---------------|----------------|-------------|----------------------|-----------------|
| 1 | **Problem Callout** | Names the reader's specific frustration with precision. Crystallizes a felt but unarticulated problem. | Problem-Aware | Meta primary text, Presell headline | Listicle, Advertorial | Law 2 (Pain Naming), Law 4 (Specificity) | "You want to use herbs for your family. But every source you find contradicts the last one." | Not for Most-Aware (they know the problem; restating it stalls the sale). Not if problem naming requires naming a disease (Section 4). |
| 2 | **Identity Callout** | Calls out who the reader is, not what they suffer from. Makes them feel recognized before any claim. | Unaware, Problem-Aware | TikTok, Meta video/reel, Email subject line | Listicle, Advertorial | Law 2 (Pain Naming), Law 5 (Simplicity) | "You are the person your friends text when their kid has a fever and they want a natural option first." | Not for Product-Aware or Most-Aware (too indirect). No banned identity labels ("warrior," "goddess," "queen," "mama," "babe"). |
| 3 | **Contrarian Claim** | Challenges a widely held belief within the herbal/wellness community. Differentiates by positioning the brand as more honest than the consensus. | Solution-Aware, Problem-Aware | Meta primary text, YouTube organic, Presell headline | Advertorial | Law 1 (Open Loop), Law 3 (Unique Mechanism), Law 6 (Credibility) | "Elderberry is one of the most popular immune herbs. It is also one of the most misunderstood in terms of when not to use it." | Must be substantiated by referenced research. No conspiracy framing. |
| 4 | **Curiosity Gap** | Opens an information gap the reader wants closed. Withholds a specific detail that pulls the reader forward. | Problem-Aware, Solution-Aware | Meta primary text, Email subject line, TikTok | Listicle, Advertorial | Law 1 (Open Loop), Law 4 (Specificity) | "There is one herb in almost every kitchen spice rack that has a real, documented interaction with blood thinners." | Not for Most-Aware (they want the offer, not a tease). Gap must be closeable in body copy. |
| 5 | **Safety Warning** | Leads with a specific, factual safety concern about common herbal use. Unique to this brand's safety-first positioning. | Problem-Aware, Solution-Aware | Meta primary text, YouTube pre-roll, Email subject line | Advertorial, Sales Page | Law 2 (Pain Naming), Law 4 (Specificity), Law 6 (Credibility) | "If you take any prescription medication and use herbal supplements, there is a short list of interactions worth checking before your next dose." | Not above agitation level 3. No specific diseases. No catastrophizing. Not for Unaware audiences. |
| 6 | **Social Proof Lead** | Opens with a credible, specific proof element -- reader count, testimonial snippet, or verifiable outcome. | Product-Aware, Most-Aware | Meta retargeting, Email, Sales page headline | Sales Page | Law 4 (Specificity), Law 6 (Credibility) | "Over 12,000 women use this as their go-to reference before reaching for any herb. Here is why." | No fabricated numbers. No testimonials implying health outcomes without disclaimers. Not for Unaware audiences. |
| 7 | **Story/Anecdote** | Opens with a specific, relatable moment or scene. Pulls the reader into a narrative before any claim or product mention. | Unaware, Problem-Aware | TikTok, Meta video/reel, Presell headline, YouTube organic | Advertorial | Law 1 (Open Loop), Law 2 (Pain Naming), Law 5 (Simplicity) | "Last month a reader emailed us: 'I almost gave my toddler an herb that interacts with his prescription. I had no idea.' That is exactly why this book exists." | Not for Most-Aware. No fabricated anecdotes. No fearmongered medical emergencies. |
| 8 | **Direct Benefit** | Leads with the concrete outcome or utility the reader gains. No buildup, no indirection. | Product-Aware, Most-Aware | Meta retargeting, Email, Sales page headline | Sales Page | Law 4 (Specificity), Law 5 (Simplicity), Law 7 (Time Compression) | "300+ herbs. Safety flags for every one. Dosing references you can actually trust. One book, $49." | Not for Unaware or Problem-Aware. Do not overstate benefits -- the product is a reference book, not a health transformation tool. |
| 9 | **Expert Insight** | Leverages the author's credentials, research process, or professional experience. Positions the brand as knowledgeable guide, not hype merchant. | Solution-Aware, Product-Aware | YouTube organic, Presell headline, Meta primary text, Email | Advertorial, Sales Page | Law 3 (Unique Mechanism), Law 6 (Credibility) | "After reviewing over 300 herbs through the lens of published safety research, here is what we found most guides get wrong." | No inflated credentials. No guru framing. Not for Unaware audiences. |

### Archetype Selection Rules

1. Every HookBank of 10+ hooks must contain at least 4 different archetypes.
2. No single archetype may exceed 30% of the total bank.
3. The archetype must match the target awareness level. Deploying an archetype outside its designated level is a construction failure unless the agent documents a specific strategic rationale.
4. Archetypes 5 (Safety Warning) and 9 (Expert Insight) are high-trust archetypes unique to this brand's positioning. At least one of these two must appear in every HookBank of 10+ hooks.

---

## 4. Headline-to-Page-Type Calibration

Each page type has distinct headline requirements driven by the reader's entry state, the page's persuasion job, and platform compliance rules. The headline must be calibrated to the page type before delivery.

### Presell Listicle Headlines

| Parameter | Spec |
|-----------|------|
| **Word count** | 8-14 words |
| **Structure** | Number + curiosity/specificity |
| **Tone** | Editorial, content-native. Must read as a magazine or blog headline, not an ad. |
| **CTA alignment** | Headline opens curiosity that the list items partially satisfy and the final CTA fully resolves. |
| **Primary Laws** | Law 1 (Open Loop), Law 4 (Specificity), Law 5 (Simplicity) |
| **Best archetypes** | Curiosity Gap, Problem Callout, Safety Warning |

**Example:** "7 Herbs in Your Kitchen Cabinet With Documented Drug Interactions" (11 words, number + specificity + curiosity)

**Calibration rules:**
- The number in the headline must match the number of list items on the page.
- The headline must tease content worth scanning, not promise a product.
- Do not reveal the full mechanism -- the listicle teases; the next page explains.
- No price, bonuses, or guarantee language.

### Presell Advertorial Headlines

| Parameter | Spec |
|-----------|------|
| **Word count** | 10-18 words |
| **Structure** | News/discovery angle |
| **Tone** | Third-person journalistic or first-person discovery. Must pass the "would a magazine print this?" test. |
| **CTA alignment** | Headline establishes the editorial frame; the mechanism reveal in the body delivers on it. |
| **Primary Laws** | Law 1 (Open Loop), Law 3 (Unique Mechanism), Law 6 (Credibility) |
| **Best archetypes** | Contrarian Claim, Expert Insight, Story/Anecdote |

**Example:** "New Safety Review Reveals What Most Herbal Guides Get Wrong About Drug Interactions" (14 words, news/discovery angle, editorial tone)

**Calibration rules:**
- Must read as content, not pitch. If it reads like an ad headline, it fails as an advertorial.
- Do not name the product in the headline (product introduction happens after mechanism reveal, typically not before word 600).
- Include a byline/source line if the format supports it.
- The headline sets the editorial frame -- everything below must sustain that frame.

### Sales Page Headlines

| Parameter | Spec |
|-----------|------|
| **Word count** | 8-20 words (headline alone); full stack may total 30-50 words |
| **Structure** | Biggest promise or transformation. Can use pre-head + headline + sub-head stack (see Section 5). |
| **Tone** | Direct, specific, promise-forward. Can be more assertive than presell headlines but must remain within brand voice. |
| **CTA alignment** | Headline makes the core promise; the page structure delivers proof, offer, and risk reversal to support it. |
| **Primary Laws** | Law 3 (Unique Mechanism), Law 4 (Specificity), Law 6 (Credibility), Law 7 (Time Compression) |
| **Best archetypes** | Direct Benefit, Social Proof Lead, Expert Insight, Safety Warning |

**Example:** "The Only Herbal Reference That Tells You When NOT to Use an Herb -- and Why" (15 words, biggest differentiator, direct promise)

**Calibration rules:**
- The headline sets the claim ceiling for the entire page. Nothing below it can exceed what the headline promises.
- If the reader arrives from a presell, the headline must reference what they just learned.
- If from an ad, the headline must match the ad's promise.
- If from direct traffic, lead with the product's core differentiator.
- One clear idea per headline. Do not stack multiple claims.

---

## 5. Pre-head + Headline + Sub-head Stack Construction

Sales pages (and occasionally advertorials) use a three-part headline stack. Each element has a distinct job and distinct constraints.

### Stack Components

**Pre-head (5-8 words)**
- Job: Audience callout or context setter. Tells the right reader "stop here."
- Format: Smaller font, above the main headline. Often a different color or style.
- Psychological function: Activates the relevance signal before the main promise hits.
- Example: "For Women Who Use Herbs at Home"
- Example: "Finally: A Reference You Can Trust"
- Example: "Attention: Home Herbalists"

**Headline (8-20 words)**
- Job: Core promise or pattern interrupt. The single most important claim on the page.
- Format: Largest font on the page. The first element that draws the eye.
- Psychological function: Delivers the pattern interrupt and implicit promise simultaneously.
- Example: "The Only Herbal Reference That Flags Every Known Safety Concern Before You Use It"
- Example: "Stop Guessing. Start Knowing Exactly What Each Herb Does -- and When to Avoid It."

**Sub-head (15-25 words)**
- Job: Mechanism hint or proof element. Supports the headline's promise with a credibility signal or specificity.
- Format: Smaller than the headline, larger than body copy. Immediately below the headline.
- Psychological function: Engages the dorsolateral prefrontal cortex (analytical processing) to validate the emotional response triggered by the headline. Prevents the "too good to be true" dismissal.
- Example: "300+ herbs reviewed through published safety research. Dosing guidelines, interaction warnings, and contraindications -- all in one place."
- Example: "Based on a review of 300+ herbs, their documented interactions, dosing ranges, and the safety data most guides leave out."

### When to Use Each Stack Configuration

| Configuration | When to Use | Example |
|---------------|-------------|---------|
| **1-part (headline only)** | Presell listicles, email subject lines, Meta ads, TikTok text overlays. When space is constrained or the context provides its own pre-framing. | "7 Herbs in Your Kitchen With Documented Drug Interactions" |
| **2-part (headline + sub-head)** | Advertorial headlines, YouTube thumbnails with descriptions, presell pages with warm traffic. When the headline needs one layer of support but the audience is already partly framed. | **Headline:** "What Most Herbal Guides Get Wrong About Drug Interactions" / **Sub-head:** "A new safety review of 300+ herbs reveals the gaps -- and what to do about them." |
| **3-part (pre-head + headline + sub-head)** | Sales page headlines, high-ticket offer pages, cold-traffic landing pages. When the reader arrives without context and needs audience targeting, core promise, and credibility in the first visual scan. | **Pre-head:** "For Women Who Use Herbs at Home" / **Headline:** "The Only Herbal Reference That Tells You When NOT to Use an Herb" / **Sub-head:** "300+ herbs. Safety flags. Dosing references. Interaction warnings. All reviewed through published research." |

### Stack Construction Rules

1. **No component repeats another.** The pre-head, headline, and sub-head must each deliver unique information. If the pre-head says "For Home Herbalists" and the headline says "A Guide for Home Herbalists," the stack fails.
2. **Headline carries the weight.** If the reader sees only the headline (because they skip the pre-head and sub-head), the headline must still work as a standalone.
3. **Sub-head cannot introduce claims the headline does not support.** The sub-head amplifies or proves the headline's promise. It does not make a new, unrelated claim.
4. **Pre-head is optional but the headline is never optional.** The agent may recommend omitting the pre-head or sub-head, but must always deliver the headline.
5. **Visual hierarchy must match information hierarchy.** Pre-head = context (smallest). Headline = promise (largest). Sub-head = proof (medium). If these are inverted visually, the stack fails.

---

## 6. Platform-Specific Adaptation

Platform adaptation rules are maintained in the reference file `reference/platform-adaptation.md`. The following is the adaptation process that governs how the agent applies those rules.

### Adaptation Process

The agent follows this sequence when adapting a headline concept across platforms:

1. **Write the headline at full length** with all three anatomy components clearly articulated.
2. **Identify the target platform** from the brief.
3. **Apply the character/time constraint.** If the full headline does not fit, prioritize: pattern interrupt first, relevance signal second, implicit promise third.
4. **Check the compliance notes** for the target platform against Section 4.
5. **Verify the adapted headline still passes the three-component anatomy check.** If a component was cut for space, it must appear immediately after the fold, in the preview text, or in the first seconds of body copy.
6. **Verify page-type calibration.** The adapted headline must still meet the word count, tone, and structural requirements for its page type (Section 4 of this document).
7. **Run the self-evaluation checklist** (Section 12) on the adapted version.

### Platform Summary Table

Full platform specifications, character limits, compliance notes, and brand-specific adaptation guidance are in `reference/platform-adaptation.md`. The platforms covered are:

- Meta primary text (125-character above-fold constraint)
- Meta video/reel (1-3 second hook window)
- TikTok (1-2 second hook, 150-character overlay limit)
- YouTube pre-roll (5-second skip window)
- YouTube organic (15-30 second hook runway)
- Email subject line + preview text (40-60 character subject, ~90 character preview)
- Presell headline (message match mandatory)
- Sales page headline (claim ceiling principle)

---

## 7. Message-Match Enforcement

Message match is the principle that every headline in the conversion path must extend, answer, or confirm the promise made by the headline that preceded it. A mismatch at any transition point causes the reader's brain to re-evaluate relevance, breaking the engagement state and causing bounces.

**Scope note:** Message-match is **headline-to-headline** — it ensures continuity across the ad → presale → sales page chain. A separate system, the **Promise Contract** (HEADLINE-ENGINE.md Step 4.5), handles **headline-to-body** — it ensures the page body delivers what the headline promised. These are complementary systems. A page can pass message-match (headline extends the upstream promise) and still fail promise delivery (the body never pays off what the headline opened).

### The Headline Chain

```
Ad headline → Presale headline → Sales page headline
```

Each link in the chain must pass a message-match verification.

### Transition 1: Ad Headline to Presale Headline

The presale headline must feel like the natural continuation of the ad hook that sent the reader there.

**Mechanical verification process:**
1. Extract the implicit promise from the ad headline.
2. Identify the specific information, mechanism, or benefit that was promised or teased.
3. Verify that the presale headline references, extends, or answers that promise.
4. If the presale headline introduces a completely new topic or angle not present in the ad, it fails message match.

**Example -- PASS:**
- Ad: "The herb in your spice rack that interacts with blood thinners"
- Presale: "7 Common Kitchen Herbs With Documented Drug Interactions (Number 3 Surprises Most People)"
- Match: The presale extends the ad's promise (herb-drug interactions) and expands it (7 herbs, not just one).

**Example -- FAIL:**
- Ad: "The herb in your spice rack that interacts with blood thinners"
- Presale: "Why Every Mom Needs a Reliable Herbal Reference"
- Mismatch: The ad promised specific interaction information. The presale shifted to a generic product pitch. The reader expected to learn about the herb. They got a sales angle instead.

### Transition 2: Presale Headline to Sales Page Headline

The sales page headline must confirm relevance and create pull to scroll. If the reader arrives from a presell, the headline must reference what they just learned.

**Mechanical verification process:**
1. Extract the presale's core frame (what the reader now believes or is curious about).
2. Identify the specific mechanism, category, or problem that was established.
3. Verify that the sales page headline acknowledges that frame and advances it toward the offer.
4. If the sales page headline ignores the presale's frame and starts from scratch, it fails message match.

**Example -- PASS:**
- Presale: Advertorial establishing that most herb-drug interaction charts miss 3 critical factors.
- Sales page: "The Only Herbal Reference That Covers All Three Factors Most Interaction Charts Miss"
- Match: Directly references the presale's mechanism ("three factors").

**Example -- FAIL:**
- Presale: Advertorial establishing herb-drug interaction risks.
- Sales page: "Discover 300+ Healing Herbs for Your Family"
- Mismatch: The presale framed safety concerns. The sales page pivoted to a different benefit (discovery/healing). The reader's safety-oriented mindset encounters an irrelevant promise.

### Message-Match Rules

1. The presale headline must reference the ad's promise within the first 14 words.
2. The sales page headline must reference the presale's core frame within the first 20 words.
3. If the ad uses a specific number, the presale must reference that number or explicitly expand on it.
4. If the presale establishes a "named enemy" (a hidden cause, a misunderstood mechanism), the sales page headline must acknowledge that enemy.
5. Message mismatch is flagged as a critical error in the self-evaluation checklist and in eval/headline_scorer.py.

---

## 8. HookBank Construction and Differentiation

### The Four Dimensions of Differentiation

Two hooks are meaningfully different when they diverge on at least 2 of these 4 dimensions:

**Dimension 1: Archetype.** The hooks use different archetypes from the Section 3 table. A Problem Callout and a Contrarian Claim are different archetypes even if they address the same topic.

**Dimension 2: Entry Angle.** The hooks enter through different psychological frames:
- Problem entry: leads with what is wrong ("You cannot find consistent dosing information")
- Solution entry: leads with what exists to fix it ("A reference that flags every known interaction")
- Identity entry: leads with who the reader is ("You are careful about what your family puts in their bodies")

Two hooks using the same archetype but different entry angles are meaningfully different on this dimension.

**Dimension 3: Belief Targeted.** The hooks address different beliefs from the B1-B8 chain defined in Section 1. A hook targeting B2 ("natural does not mean safe") and a hook targeting B3 ("the info ecosystem is broken") are meaningfully different on this dimension.

**Dimension 4: Emotional Register.** The hooks operate in different registers from the Section 3 emotional register map:
- Clinical: data-forward, evidence-referencing, measured
- Empathetic: warm, validating, protective
- Provocative: challenging, contrarian, direct (not aggressive)

### What Does NOT Count as Meaningfully Different

- **Synonym swaps.** Replacing "confused" with "overwhelmed" without changing archetype, angle, belief, or register.
- **Word reordering.** Moving the same components into a different sentence order without changing meaning.
- **Additions or deletions that preserve the core claim.** Adding a modifier ("really confused" vs. "confused") does not create a new hook.
- **Tonal micro-shifts within the same register.** Slightly warmer or slightly cooler versions of the same empathetic hook are not different hooks.
- **Platform-only reformats.** A Meta-adapted version and a TikTok-adapted version of the same hook concept count as one hook.

### Minimum Differentiation Standard for HookBank Output

| Requirement | Minimum Threshold |
|-------------|-------------------|
| Pairwise differentiation | Every hook must differ from every other hook on at least 2 of 4 dimensions. |
| Archetype coverage | At least 4 different archetypes. |
| Belief coverage | At least 3 different beliefs from the B1-B8 chain. |
| Register coverage | At least 3 different emotional registers. |
| Brand-specific archetype inclusion | At least 1 hook must use archetype 5 (Safety Warning) or archetype 9 (Expert Insight) per bank of 10+ hooks. |

### HookBank Tagging Requirement

Every hook delivered in a HookBank must be tagged with metadata:

```
HOOK: [The hook text]
ARCHETYPE: [Number and name from archetype table]
BELIEF TARGETED: [B1-B8 identifier]
EMOTIONAL REGISTER: [Clinical / Empathetic / Provocative]
TARGET AWARENESS LEVEL: [Unaware / Problem-Aware / Solution-Aware / Product-Aware / Most-Aware]
LAWS DEMONSTRATED: [List of laws by number]
PAGE TYPE: [Listicle / Advertorial / Sales Page / Ad / Email]
```

The agent runs the differentiation check after generating the full bank. If the bank fails any threshold, the agent must replace hooks until all thresholds are met. The differentiation check is a delivery gate.

---

## 9. 30 Headline Formulas (Brand-Adapted)

Each formula from the DR Headline Engine is adapted for The Honest Herbalist Handbook. Full formula templates and additional examples are in `reference/dr-headline-engine.md`.

| # | Formula | Template | Brand Example | Best Awareness Level | Best Page Type |
|---|---------|----------|---------------|---------------------|----------------|
| 1 | **Mechanism Mystery** | "The [hidden/little-known] [mechanism] behind [desired outcome]" | "The Little-Known Interaction Factor Behind Most Herbal Side Effects" | Solution-Aware | Advertorial |
| 2 | **Pain Mirror** | "[Specific pain statement] -- [validation + hint of resolution]" | "You Have Googled the Same Herb Three Times and Gotten Three Different Answers -- Here Is Why" | Problem-Aware | Listicle, Advertorial |
| 3 | **Forbidden Fix** | "The [unexpected/counterintuitive] [solution] that [authority figures] [overlook/dismiss]" | "The Safety-First Approach to Herbs That Most Wellness Influencers Skip Entirely" | Solution-Aware | Advertorial |
| 4 | **Time-Compression Promise** | "[Achieve outcome] in [compressed timeframe] [with/using mechanism]" | "How to Check Any Herb for Drug Interactions in Under 2 Minutes" | Product-Aware | Listicle, Sales Page |
| 5 | **Inside Leak** | "What [credible insiders] [know/do] about [topic] that [audience] [doesn't/don't]" | "What Trained Herbalists Check Before Recommending Any Herb -- and What Most Books Leave Out" | Solution-Aware | Advertorial |
| 6 | **Hidden Enemy** | "The [invisible/overlooked] [cause/factor] [sabotaging/undermining] your [desired outcome]" | "The Overlooked Factor in Your Herbal Routine That Could Undermine Your Prescriptions" | Problem-Aware | Advertorial |
| 7 | **Transformation Snapshot** | "From [before state] to [after state] [with/using mechanism]" | "From Guessing at Doses to Knowing Exactly What Is Safe -- for Every Herb in Your Cabinet" | Product-Aware | Sales Page |
| 8 | **Simple Switch** | "The [simple/one] [change/switch] that [transforms outcome]" | "The One Change That Turns Your Herb Collection From Risky Guesswork Into a Trusted Resource" | Solution-Aware | Advertorial, Sales Page |
| 9 | **Selective Call-Out** | "[Specific audience segment]: [relevant message]" | "Home Herbalists Who Use Herbs With Their Kids: Read This Before Your Next Dose" | Problem-Aware | Listicle, Ad |
| 10 | **Advanced Call-Out** | "For [experienced audience] who [specific sophisticated behavior]" | "For Women Who Already Use Herbs Daily -- but Still Wonder About Interactions" | Solution-Aware | Advertorial, Sales Page |
| 11 | **Shame Trigger** | "Are you [common mistake] without [knowing consequence]?" | "Are You Combining Herbs and Prescriptions Without Checking This One Thing?" | Problem-Aware | Ad, Listicle |
| 12 | **Social Proof Magnet** | "[Number] [people] [already doing/using] [solution] -- [here is why]" | "Over 12,000 Women Use This as Their Go-To Herb Reference -- Here Is Why" | Product-Aware, Most-Aware | Sales Page |
| 13 | **Reverse Logic** | "Why [counterintuitive opposite] is actually [better/true]" | "Why Knowing When NOT to Use an Herb Is More Important Than Knowing When to Use It" | Solution-Aware | Advertorial |
| 14 | **Vulnerable Confession** | "I [made this mistake/didn't know this] until [discovery]" | "I Gave My Daughter an Herb Without Checking Interactions -- Here Is What I Learned" | Unaware, Problem-Aware | Advertorial, TikTok |
| 15 | **Imminent Threat** | "[Urgent framing] about [specific risk] you need to [know/check] [now/today]" | "If You Use Herbal Supplements With Any Prescription, Check This List Before Your Next Dose" | Problem-Aware | Ad, Email |
| 16 | **Aspiration Frame** | "[Imagine/picture] [desired future state] -- [mechanism that makes it possible]" | "Imagine Reaching for Any Herb and Knowing Exactly Whether It Is Safe for Your Situation" | Solution-Aware | Sales Page |
| 17 | **Emotional Hook** | "[Emotional state] + [shared experience] + [hint of resolution]" | "That Moment When You Realize You Have Been Using an Herb Wrong -- and What to Do Next" | Problem-Aware | Ad, Advertorial |
| 18 | **ROI Frame** | "[Investment] → [return in concrete terms]" | "One $49 Reference vs. a Lifetime of Guessing at Herb Safety" | Most-Aware | Sales Page |
| 19 | **Extreme Specificity** | "[Precise number] [specific items] for [specific outcome]" | "143 Herb-Drug Interactions Documented in One Reference -- Organized by Medication Type" | Product-Aware | Sales Page, Listicle |
| 20 | **Mechanism Reveal** | "Here is exactly [how/why] [mechanism] [works/fails]" | "Here Is Exactly Why Your Chamomile Tea Isn't Helping You Sleep" | Solution-Aware | Advertorial |
| 21 | **Contradiction Hook** | "[Accepted belief] is [wrong/incomplete] -- [here is what is actually true]" | "Everything You Have Read About Elderberry Dosing Is Missing One Critical Detail" | Solution-Aware | Advertorial |
| 22 | **Niche Spotlight** | "Specifically for [narrow audience] who [specific behavior/situation]" | "Specifically for Moms Who Give Their Kids Herbal Remedies Alongside Prescriptions" | Problem-Aware | Listicle, Ad |
| 23 | **New Paradigm** | "Forget [old approach] -- [new framework] [changes everything]" | "Forget Googling Every Herb Individually -- One Reference Covers Every Safety Question" | Solution-Aware | Sales Page |
| 24 | **Mini Case Study** | "[Person/reader] [discovered/experienced] [specific result] [when/after doing specific thing]" | "One Reader Found 3 Interactions in Her Daily Herb Routine She Never Knew Existed" | Problem-Aware | Advertorial |
| 25 | **Identity Shift** | "Stop being [old identity] -- start being [new identity]" | "Stop Being the Mom Who Guesses -- Start Being the One Who Knows" | Solution-Aware | Sales Page |
| 26 | **System Headline** | "The [name/number]-[step/part] system for [achieving outcome]" | "The 3-Step Safety Check for Every Herb You Give Your Family" | Solution-Aware, Product-Aware | Advertorial, Sales Page |
| 27 | **Opportunity Gap** | "[Opportunity] is [available/possible] -- but only if [condition]" | "Safe, Confident Herbal Use Is Possible -- but Only If You Know What to Check First" | Solution-Aware | Advertorial |
| 28 | **Prediction** | "[Emerging trend/fact] means [specific consequence] for [audience]" | "The Growing List of Herb-Drug Interactions Means Every Home Herbalist Needs This" | Problem-Aware | Advertorial, Ad |
| 29 | **Quick Win** | "The [fastest/easiest] way to [specific small outcome]" | "The Fastest Way to Check if an Herb Is Safe With Your Current Medications" | Product-Aware | Listicle, Ad |
| 30 | **Reality Check** | "[Common assumption] vs. [what the evidence actually shows]" | "What You Think You Know About Herbal Dosing vs. What the Published Research Says" | Solution-Aware | Advertorial |

---

## 10. Bullet-to-Headline Conversion System

Six conversion formulas for transforming product bullet points or fascinations into full headlines. Each formula targets a different psychological entry point.

### Conversion 1: "How to" to Instructional Headline

**Bullet type:** Feature or benefit stated as "how to [do thing]."
**Conversion:** Elevate the "how to" into a headline that promises specific, actionable instruction.
**Template:** "How to [Specific Action] [Without/Before/In Timeframe] [Negative Consequence/Additional Benefit]"

**Example:**
- Bullet: "How to check herb-drug interactions"
- Headline: "How to Check Any Herb for Drug Interactions in Under 2 Minutes -- Without a Pharmacology Degree"

### Conversion 2: "Secret" to Mechanism Mystery

**Bullet type:** Hidden or little-known information framed as a "secret."
**Conversion:** Transform the secret into a mechanism mystery that creates an open loop.
**Template:** "The [Adjective] [Mechanism/Factor] Behind [Outcome] That [Authority/Majority] [Overlooks]"

**Example:**
- Bullet: "The secret to proper chamomile dosing"
- Headline: "The Overlooked Brewing Factor That Determines Whether Your Chamomile Actually Works for Sleep"

### Conversion 3: "What never" to Contrarian Hook

**Bullet type:** Information framed as "what [authority/most people] never [tell you/consider]."
**Conversion:** Transform into a contrarian claim that challenges conventional wisdom.
**Template:** "Why [Accepted Practice/Belief] Is [Wrong/Incomplete] -- and What [Credible Source] [Found/Recommends] Instead"

**Example:**
- Bullet: "What your naturopath never tells you about herb timing"
- Headline: "Why Taking Herbs 'With Food' Is Not Always the Right Answer -- and What Timing Actually Matters"

### Conversion 4: Specific Question to Emotional Tension

**Bullet type:** A question that surfaces an emotional concern.
**Conversion:** Amplify the emotional stakes and make the question feel urgent and personal.
**Template:** "Do You [Know/Check/Realize] [Specific Concern] [Before/When/Every Time] You [Common Action]?"

**Example:**
- Bullet: "Is your favorite herb safe with your medication?"
- Headline: "Do You Check for Interactions Every Time You Reach for an Herb -- or Are You Just Hoping for the Best?"

### Conversion 5: "Warning" to Fear-Based (Compliance-Safe)

**Bullet type:** A caution or warning about common practice.
**Conversion:** Frame the warning with protective urgency (not catastrophizing) within compliance boundaries.
**Template:** "If You [Common Behavior], [Specific Risk/Concern] Is Worth [Checking/Knowing] [Before/Now]"

**Example:**
- Bullet: "Warning about combining echinacea with immunosuppressants"
- Headline: "If You Take Immunosuppressants and Use Echinacea, Here Is What the Interaction Data Shows"

### Conversion 6: "Single most" to Authority Frame

**Bullet type:** A superlative claim about the most important, most dangerous, or most overlooked item.
**Conversion:** Frame the superlative within an authority/credibility container.
**Template:** "The Single Most [Important/Overlooked/Dangerous] [Item] in [Context] -- According to [Credible Source/Evidence]"

**Example:**
- Bullet: "The single most overlooked herb-drug interaction"
- Headline: "The Single Most Overlooked Herb-Drug Interaction in Published Safety Research -- and Why It Matters If You Take Blood Thinners"

---

## 11. Headline Testing Protocol

### Core Testing Rules

1. **Test one variable at a time.** When testing headlines, change only the headline. Keep the ad creative, audience targeting, page content, and all other variables constant. Otherwise, results are unattributable.

2. **Test on cold traffic.** Warm audiences (retargeting, email lists) already have affinity. Their response to headlines reflects relationship, not headline quality. Test headline performance on cold traffic for clean signal.

3. **Radical contrast, not micro-variations.** Test headlines that are fundamentally different -- different archetypes, different entry angles, different psychological frames. Testing "confused" vs. "overwhelmed" wastes budget. Testing a Problem Callout vs. a Curiosity Gap vs. a Social Proof Lead generates actionable insight.

4. **Track downstream metrics, not just CTR.** A headline that generates high click-through but low conversion is a message-match failure, not a headline success. Evaluate headlines on:
   - Click-through rate (initial engagement)
   - Bounce rate on destination page (message-match quality)
   - Read depth / time on page (relevance quality)
   - Conversion rate (promise payoff quality)
   - Cost per acquisition (net effectiveness)

### Categories to Test

| Category | What to Vary | Example Contrast |
|----------|-------------|------------------|
| **Archetype** | Test different psychological entry points | Problem Callout vs. Curiosity Gap vs. Social Proof Lead |
| **Awareness framing** | Test different awareness-level targeting | Problem-Aware headline vs. Solution-Aware headline on the same audience |
| **Specificity level** | Test specific vs. broad claims | "7 herbs with drug interactions" vs. "Common herbs with hidden risks" |
| **Emotional register** | Test clinical vs. empathetic vs. provocative | Data-forward vs. warm/validating vs. challenging/direct |
| **Mechanism inclusion** | Test mechanism-present vs. mechanism-absent | "The 3 factors behind herb-drug risk" vs. "What you need to know about herb safety" |
| **Length** | Test short-punchy vs. longer-detailed | 8-word headline vs. 18-word headline |

### What Matters Most

In order of impact on performance (based on DR testing consensus):
1. **Archetype / psychological frame** -- the biggest lever. Different archetypes often produce 2-5x performance differences.
2. **Specificity level** -- specific outperforms vague nearly universally.
3. **Awareness-level match** -- mismatched awareness is the most common cause of low CTR.
4. **Emotional register** -- can produce 30-100% performance swings depending on audience segment.
5. **Word-level variations** -- smallest impact. Test this last, if at all.

---

## 12. Self-Evaluation Checklist

The agent runs this checklist before delivering any headline. Every item must pass. If any item fails, the headline must be revised before delivery.

### Anatomy Check
- [ ] Does the headline contain a clear **pattern interrupt**?
- [ ] Does the headline contain a clear **relevance signal** matched to the target awareness level?
- [ ] Does the headline contain a clear **implicit promise** that is payable in the body copy?

### Law Compliance
- [ ] Does the headline demonstrably follow at least **3 of the 7 Laws**?
- [ ] Which laws does it follow? (List by number and name.)
- [ ] Does it violate any law's "What NOT to do" constraints?

### Awareness-Level Match
- [ ] Is the target awareness level identified?
- [ ] Does the headline's archetype match the target awareness level (per the archetype table)?
- [ ] Would a reader at this awareness level understand and respond to this headline?

### Page-Type Calibration
- [ ] Does the headline meet the word count range for its page type?
- [ ] Does the headline match the tone requirements for its page type?
- [ ] Does the headline align with the CTA structure of its page type?

### Compliance Gate (Hard Pass/Fail)
- [ ] Does the headline contain any **banned words** from the Section 3 list?
- [ ] Does the headline make any **disease claims** or imply diagnosis? (Section 4 violation)
- [ ] Does the headline use any **prohibited phrases** from Section 4 Subsection C?
- [ ] Does the headline use conspiracy framing, catastrophizing, or ALL CAPS words?
- [ ] If using a testimonial, does it avoid implying health outcomes without disclaimers?

### Promise Integrity (Promise Contract)
- [ ] Has a **PROMISE_CONTRACT** been extracted for this headline (HEADLINE-ENGINE.md Step 4.5)?
- [ ] Is the **DELIVERY_TEST** concrete and falsifiable (starts with "The body must contain...")?
- [ ] Does the DELIVERY_TEST describe content that the **page-type template** (Section 2) can structurally accommodate within Sections 1-2?
- [ ] Is the promise paid off **BEFORE** the structural pivot to solution/product (advertorial Section 4, sales page Section 3)?
- [ ] Does the headline set a **claim ceiling** that the page content can support?

### Message Match (When Applicable)
- [ ] If this headline follows an upstream headline (ad or presale), does it **reference or extend** that headline's promise?
- [ ] If this headline precedes a downstream page, does it set up a promise the next page can **confirm**?

### HookBank Differentiation (When Delivering Multiple Headlines)
- [ ] Does this headline differ from every other headline in the bank on at least **2 of 4 dimensions**?
- [ ] Does the full bank meet the archetype coverage minimum (4+ archetypes)?
- [ ] Does the full bank meet the belief coverage minimum (3+ beliefs from B1-B8)?
- [ ] Does the full bank meet the register coverage minimum (3+ registers)?
- [ ] Does the bank include at least 1 Safety Warning or Expert Insight archetype?

---

## 13. Quality Gate

Two evaluation tools enforce headline quality. Both live in `eval/`:

- **`headline_scorer_v2.py`** — Deterministic scorer. 28 tests, 40 points, 4 cognitive-science dimensions. Zero LLM inference. Runs instantly.
- **`headline_qa_loop.py`** — LLM-powered auto-fix pipeline. Scores → identifies failures → LLM rewrites → rescores → up to 3 iterations. Only outputs A/S tier headlines to the human.

### Scoring Dimensions (v2)

| Dimension | Tests | Points | What It Measures |
|-----------|-------|--------|-----------------|
| **Information Architecture** | 6 | 10 | HOW the headline is built: word count, readability, cognitive load, passive voice, compound structures, front-loading |
| **Psychological Triggers** | 9 | 12 | WHAT psychological mechanisms activate: curiosity gaps, loss framing, identity activation, reader-directness, pattern interrupts, emotional arousal, forward pull, novelty, narrative hooks |
| **Credibility & Specificity** | 6 | 8 | WHETHER a smart reader would believe this: specificity, numbers, mechanism hints, credibility signals, concrete nouns, power word density |
| **Brand & Compliance** | 7 | 10 | WHETHER the headline is safe to publish: banned words, disease claims, prohibited phrases, brand voice, personal-attribute targeting, vague hype, time compression safety |

**Total: 28 tests, 40 points.**

### Hard Gate (DISQUALIFIED)

Brand & Compliance tests BC1 (banned words), BC2 (disease claims), and BC3 (prohibited phrases) are **hard gates**. Failure on any one = DISQUALIFIED (0%, no tier). The headline is rejected with zero override. All other tests are still reported for diagnostic use by the QA loop.

### Composite Score Tiers

| Tier | Score Range | Status |
|------|------------|--------|
| S | 90-100% | Exceptional. Ship immediately. |
| A | 80-89% | Strong. Ship with confidence. |
| B | 70-79% | Acceptable. Ship, but note areas for improvement. |
| C | 60-69% | Below standard. Revise before shipping. |
| D | Below 60% | Reject. Fundamental rework required. |
| DISQUALIFIED | 0% | Hard gate failure. Banned word, disease claim, or prohibited phrase detected. |

### Page-Type Calibration in Scoring

The scorer adjusts word-count targets per page type:

| Page Type | Word Count Target | Headline Purpose | Key Calibration |
|-----------|-------------------|------------------|-----------------|
| **Listicle** | 8-14 words | Editorial hook, content-native, curiosity + number | No product, no price, no sales language. Think magazine headline. |
| **Advertorial** | 10-18 words | News/discovery angle, journalistic frame | No product name in headline. Must pass "would a magazine print this?" test. |
| **Sales Page** | 8-20 words | Biggest promise, core differentiator, claim ceiling | Sets claim ceiling for entire page. Direct and assertive but brand-voice governed. |
| **Email** | 4-9 words | Subject line, curiosity/identity hook | Short, friend-to-friend tone. Lowercase-friendly. |
| **Ad** | 5-15 words | Scroll-stopper, 2-3 second hook window | Pattern interrupt first, within platform character limits. |

### QA Loop Pipeline

When headlines score below the target tier (default: A, 80%+):

1. **Score** the headline deterministically with `headline_scorer_v2.py`
2. **Analyze** failures — each test provides a `fix_hint` for the LLM (e.g., "Add a concrete noun like an herb name")
3. **LLM rewrites** — receives failures + fix_hints + page-type-specific calibration context + brand rules. Does NOT receive scoring code, word lists, or thresholds.
4. **Rescore** the rewrite deterministically
5. **Repeat** up to 3 iterations
6. **Regression protection** — the best-scoring iteration wins, not necessarily the last one
7. **Gate** — only headlines reaching A tier or above are output to the human

### Quality Gate Sequence

1. Run `headline_scorer_v2.py` with `--page-type` flag set correctly.
2. If Brand & Compliance hard gate fails → DISQUALIFIED. Stop.
3. If composite ≥ target tier → PASS. Ship.
4. If composite < target tier → run `headline_qa_loop.py` for LLM-assisted fixes.
5. After QA loop: if best iteration ≥ target tier → PASS. Ship the best version.
6. If QA loop exhausts iterations without reaching target tier → FAIL. Report to human with diagnostic detail.
7. If delivering a HookBank, run batch mode and check diversity thresholds post-QA.

---

*End of Headline Engineering System. This document governs all headline construction decisions. The agent must apply the three-component anatomy check (Section 1) to every headline, follow at least 3 of the 7 Laws (Section 2), select archetypes within the diversification rules (Section 3), calibrate to the target page type (Section 4), construct headline stacks correctly (Section 5), adapt to platform constraints (Section 6), enforce message match across the conversion path (Section 7), verify differentiation before shipping any HookBank (Section 8), leverage the 30 formulas and 6 conversion methods for generation (Sections 9-10), follow the testing protocol for optimization (Section 11), run the self-evaluation checklist before delivery (Section 12), and pass the quality gate before any headline ships (Section 13). No headline is delivered without passing all checks.*
