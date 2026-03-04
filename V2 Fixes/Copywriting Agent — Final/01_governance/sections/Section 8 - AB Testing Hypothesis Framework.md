# Section 8: A/B Testing Hypothesis Framework
## Agent Operating Rules for Generating Testable Variants

**Brand context:** The Honest Herbalist Handbook | $49 digital herbal reference | DTC health/wellness
**Audience:** Women 25-55, safety-conscious, anti-hype, "crunchy but not anti-science," Stage 5 market sophistication
**Brand voice anchor:** No hype. No woo. No fearmongering. Honest, safety-first, natural-first but not reckless.

**Scope:** This document governs how the agent formulates hypotheses, categorizes tests, prioritizes testing order, and generates variant pairs. It does not govern test execution mechanics, traffic allocation, or statistical analysis. For live test architecture and sequencing, see the Experimental Test Plan.

---

## SUBSECTION A: HYPOTHESIS TEMPLATE

Every variant pair the agent produces must include a completed version of this template. No variant ships without it.

```
TEST NAME: [Descriptive — e.g., "Presell Headline: Safety-First vs. Curiosity-Gap"]

VARIABLE:
  - Element: [headline | hook | proof type | CTA | guarantee framing | section order |
              testimonial selection | agitation level | value stack | email subject line]
  - Specific change: [Exactly what differs between control and variant. Name both versions.
                       E.g., "Control leads with ecosystem-broken framing (B3). Variant leads
                       with identity callout framing (B6)."]

HYPOTHESIS: "We believe [specific change] will [improve / decrease] [metric] because
[reasoning grounded in the belief chain, awareness level, behavioral science principle,
or historical A/B pattern from Subsection D]."

TEST TYPE: [messaging | structural | format | audience]

SUCCESS METRIC:
  - Primary: [The single metric that determines the winner — CTR, conversion rate,
              scroll-to-CTA rate, email open rate, etc.]
  - Secondary: [Metrics monitored for unintended effects — e.g., "If CTR rises but
                downstream conversion drops, the hook is attracting misaligned traffic."]

LEARNING OUTCOME:
  - If variant wins: [What this tells us about the audience + where to apply the insight]
  - If control wins: [What this tells us about the audience + where to apply the insight]
  - If no significant difference: [What this tells us + which variable to test next]
```

### Template Rules

1. **LEARNING OUTCOME is mandatory.** A variant pair without all three learning outcome branches (win, lose, tie) is rejected. Every test must teach something regardless of result.
2. **The HYPOTHESIS must cite a specific reasoning source.** Acceptable sources: a belief from the B1-B8 chain (Subsection A of Section 1), an awareness level (Subsection A, Table 1.1), a behavioral science principle (Subsection E), or a historical A/B pattern (Subsection D). "We think this might work better" is not a hypothesis.
3. **The VARIABLE must name both versions explicitly.** "Testing a new headline" is insufficient. "Control: benefit-led headline targeting B5. Variant: proof-loaded headline targeting B5 using the specificity principle (Subsection E, #3)" is sufficient.
4. **One template per variant pair.** If a brief requests four variants, that produces two completed templates (A vs. B, C vs. D), not one template covering all four.

---

## SUBSECTION B: TEST TYPE TAXONOMY

Four test types. Every test the agent creates must be classified as exactly one type. Mixing types within a single variant pair is prohibited.

| Test Type | What Changes | What Stays Constant | Example for This Product | What You Learn |
|---|---|---|---|---|
| **Messaging** | The claim, angle, or framing. The words and the argument change. | Page structure, section order, format, traffic source, CTA position. | Presell headline A: "You have been Googling herb dosages at 2am. That is an ecosystem problem, not a knowledge problem." vs. Presell headline B: "She gave her toddler St. John's Wort without knowing it interacts with his medication. Nothing she read warned her." | Which psychological entry point -- systemic frustration (B3) vs. specific safety consequence (B2) -- produces higher click-through for this audience. |
| **Structural** | The order, presence, or position of page sections. The content stays the same; where it appears changes. | All copy, messaging, format, traffic source. | Sales page A: Mechanism section (B5) before social proof block. Sales page B: Social proof block before mechanism section (B5). | Whether this audience needs to understand the system before trusting peer validation, or whether peer validation must come first to earn attention for the mechanism explanation. |
| **Format** | The medium or presentation. Same message, different delivery vehicle. | Core argument, section order, traffic source. | Sales page delivered as text-based long-form (control) vs. sales page delivered as video sales letter with identical script. | Whether this audience -- which skews mobile and skeptical of hype -- converts better reading or watching. References Subsection D finding: text outperforms VSL on mobile in health/wellness. |
| **Audience** | The traffic segment. Same page shown to different people. | All copy, structure, format. Everything on the page is identical. | Same sales page shown to (A) cold Meta traffic from interest targeting vs. (B) email nurture subscribers who completed the 5-email sequence. | Whether the sales page works across awareness levels or requires separate versions for cold vs. warm traffic. Informs whether to build awareness-specific page variants. |

### Taxonomy Enforcement Rule

**One type per test.** If a variant pair changes both the headline messaging AND the section order, it is two tests collapsed into one. The agent must either (a) split it into two separate tests or (b) reject the brief and request clarification on which variable to isolate. Check: Can you name exactly one row from the table above that this test falls into? If no, split the test.

---

## SUBSECTION C: PRIORITIZATION FRAMEWORK

Not all tests deliver equal learning per dollar spent. The agent assigns a priority level to every test it proposes.

| Priority | Criteria | Examples for This Product | Expected Impact |
|---|---|---|---|
| **P1 -- Test First** | High-impact elements with high uncertainty. These elements are seen by every visitor and have no existing performance data. Changes here affect the largest percentage of conversions. | Presell advertorial headline. Sales page hero section (headline + subhead). Primary CTA copy and position. Ad hook archetypes (first impression for cold traffic). | 10-50% conversion lift potential. These are the elements where a single win can double downstream revenue. |
| **P2 -- Test Second** | Important elements where a hypothesis exists but no data confirms it. Moderate visitor exposure. These tests refine the funnel after P1 winners are established. | Proof structure on the sales page (testimonial placement, expert endorsement position). Guarantee framing (positive vs. validation-challenge framing). Offer stack presentation (value anchor comparison type). Email sequence belief order (B1-B2 first vs. B3 first for warm subscribers). | 5-20% conversion lift potential. These optimize the persuasion architecture after the entry point is validated. |
| **P3 -- Test Third** | Refinements of P1 and P2 winners. Smaller expected effect sizes. These tests squeeze more performance from elements that already work. | CTA button copy variations within the winning framing direction. Microcopy near the guarantee. FAQ section ordering. Testimonial selection within the winning proof structure. Subject line variations within the winning email hook archetype. | 2-10% conversion lift potential. Incremental gains. Only worthwhile after P1 and P2 questions are settled. |
| **P4 -- Test Only If Idle** | Low-impact elements or elements where the expected effect is near zero. Running these tests consumes traffic that could validate higher-priority questions. | Footer copy. Image selection (unless hero image, which is P1). Minor layout spacing. Social media share button placement. | Less than 2% expected impact. Test only when all P1-P3 questions are answered and traffic is sufficient for continued experimentation. |

### Prioritization Rules

1. **At least one P1 test must be running (or have a validated winner) before the agent proposes any P2 test.** Check: Has every P1 element been tested at least once? If no, the next proposed test must be P1.
2. **P3 tests require a P1 or P2 winner as their starting control.** A P3 test refines something that already won. If the element being refined has never been tested, it is a P1 or P2 test, not P3.
3. **If traffic is limited, run only P1 tests.** The agent must flag when projected traffic volume is insufficient to reach statistical significance on a P2 or lower test within a reasonable timeframe (4 weeks maximum).

---

## SUBSECTION D: VARIANT GENERATION RULES

These are operating rules. The agent follows every rule for every variant pair. Each rule produces a clear yes/no when checked.

### Rule 1: One Hypothesis Per Variant Pair

Each A/B pair tests exactly one hypothesis. If a brief requests four variants, the agent produces two hypothesis pairs (A vs. B tests hypothesis 1, C vs. D tests hypothesis 2). The agent does not produce four unrelated variants and call it "testing."

**Check:** Can you state the single hypothesis this pair tests in one sentence? If the sentence contains "and," it is likely two hypotheses. Split.

### Rule 2: Variants Must Be Meaningfully Different

The Section 7 Meaningful Differentiation Standard applies. Two variants are meaningfully different only if they differ on at least two of these four dimensions:

- Different archetype or framing approach
- Different psychological entry angle (problem vs. solution vs. identity vs. mechanism)
- Different belief targeted from the B1-B8 chain
- Different emotional register (clinical/data-driven vs. personal/empathetic vs. provocative/challenging)

Synonym swaps, word-order changes, and slight tonal shifts do not qualify as meaningful differentiation.

**Check:** Name the two dimensions on which the variants differ. If you cannot name two, the variants are not different enough to test. Rewrite the challenger.

### Rule 3: Tag Every Variant

Each variant the agent produces must include these metadata tags:

- **Hypothesis ID:** A sequential identifier (e.g., H-001) linking the variant to its completed hypothesis template from Subsection A.
- **Test type:** One of the four types from Subsection B.
- **What specifically differs from the control:** A plain-language description readable without comparing the two versions side-by-side.
- **Informing principle:** Which principle from the foundational docs informs this variant. Acceptable sources: Subsection A (structural principles), Subsection D (historical A/B patterns), Subsection E (behavioral science principles), Section 3 (voice/tone rules), Section 5 (awareness routing).

**Check:** Are all four tags present and filled with specific references? If any tag says "general best practice" or is blank, revise.

### Rule 4: Control Definition

Every test must define which version is the control and which is the challenger. The control is always the version closest to the current best-performing approach. If no performance data exists, the control is the version that follows existing foundational doc rules most closely.

**Check:** Is the control explicitly labeled? Is there a one-sentence rationale for why it is the control? If no, add both.

### Rule 5: Sample Size Flag

The agent must include a sample size note when generating any variant pair. Format: "This test requires approximately [X] visitors per variant to detect a [Y]% relative difference in [primary metric] at 95% confidence." If the estimated traffic over 4 weeks is below the required sample, the agent flags the test as "insufficient traffic risk" and recommends either (a) testing a higher-impact variable where a larger effect size is expected or (b) extending the test window.

**Check:** Does the variant pair include a sample size note? If no, add it.

### Rule 6: Belief Chain Alignment

Both the control and the variant must independently follow the belief sequencing rules from Subsection A of Section 1. A variant can change HOW a belief is presented (different proof, different framing, different emotional register, different agitation level). A variant cannot SKIP a belief in the chain or violate the Foundation Gate (B1 + B2 must both be established before B3).

**Check:** Map both the control and the variant against the B1-B8 chain. Does each version address every required belief in sequence for its page type? If either version skips a belief or violates the Foundation Gate, reject and revise.

### Rule 7: Compliance Gate

Both the control and the variant must independently pass the Section 4 Pre-Submission Compliance Checklist (Subsection F). A variant that tests a more aggressive claim, a stronger agitation beat, or an edgier hook still must clear every compliance item. There is no "we will fix compliance after the test" exception.

**Check:** Has the Section 4 checklist been run against both versions independently? Do both pass? If either fails, revise the failing version before the test ships.

---

## WORKED EXAMPLES

### Example 1: Messaging Test -- Presell Advertorial Headline

```
TEST NAME: Presell Headline — Ecosystem Blame vs. Safety Consequence

VARIABLE:
  - Element: Presell advertorial headline
  - Specific change:
    Control: "You have read the blog posts. You have joined the Facebook groups.
    You still do not know if chamomile is safe for your four-year-old."
    (Ecosystem-frustration framing. Targets B3: the info ecosystem is broken.
    Agitation Level 2: Specify.)

    Variant: "The mom who mixed St. John's Wort with her kid's medication did
    everything right — except trust the wrong source."
    (Safety-consequence framing. Targets B2: natural does not equal safe.
    Agitation Level 4: Consequence. Immediately followed by efficacy bridge
    per Subsection A, Section 3.2 rules.)

HYPOTHESIS: "We believe the safety-consequence headline (variant) will improve
click-through rate to the sales page because the identifiable victim effect
(Subsection E, #8) generates stronger empathy and curiosity than abstract
frustration — and Subsection D historical patterns show proof-loaded headlines
with specific scenarios consistently outperform generalized benefit headlines
in health/wellness."

TEST TYPE: Messaging

SUCCESS METRIC:
  - Primary: Click-through rate (presell to sales page)
  - Secondary: Scroll depth on the presell (are readers engaging with the full
    article or bouncing after the headline?); downstream sales page conversion
    rate (does the headline attract aligned or misaligned traffic?)

LEARNING OUTCOME:
  - If variant wins: This audience responds more to specific, story-driven safety
    scenarios than to abstract ecosystem-frustration framing at first impression.
    Apply identifiable-victim openings to ad hooks and email subject lines.
    Update Subsection D with this finding.
  - If control wins: Abstract frustration framing is the safer entry point.
    The safety-consequence headline may trigger the fear-control response
    (Subsection A, Section 3.1) rather than the danger-control response.
    Reserve Level 4 agitation for mid-article placement only, not headlines.
  - If no significant difference: The headline is not the conversion bottleneck
    for the presell. Move to testing the presell's ecosystem-indictment section
    (the core B3 argument) or the CTA language. Both framings work equally well
    as entry points — use whichever aligns better with the upstream ad hook.

TAGS:
  - Hypothesis ID: H-001
  - Test type: Messaging
  - Difference: Control uses Level 2 ecosystem-frustration framing (B3).
    Variant uses Level 4 safety-consequence framing (B2) with identifiable
    victim structure.
  - Informing principle: Identifiable Victim Effect (Subsection E, #8),
    proof-loaded headline pattern (Subsection D, Headline Patterns #4),
    Agitation Calibration Rules (Subsection A, Section 3.2)

PRIORITY: P1 (headline is the highest-leverage single element; no existing
performance data)

SAMPLE SIZE NOTE: Requires approximately 1,000 visitors per variant to detect
a 15% relative difference in CTR at 95% confidence. At $0.50 CPC, this test
requires approximately $1,000 total ad spend over 7-14 days.

BELIEF CHAIN CHECK: Control follows B1/B2 (implied) -> B3 (explicit). Variant
follows B2 (explicit) -> B3 (implied). Both satisfy the Foundation Gate because
the presell body establishes B1 within the first 120 words. Pass.

COMPLIANCE CHECK: Both versions scanned against Section 4 Subsection C banned
phrases. No disease claims, no prohibited language, no personal-attribute
targeting. The variant's safety scenario names a real herb-drug interaction
but does not claim the handbook treats or prevents it. Pass.
```

### Example 2: Structural Test -- Proof Placement on the Sales Page

```
TEST NAME: Sales Page — Proof Before Mechanism vs. Proof After Mechanism

VARIABLE:
  - Element: Section order on the sales page
  - Specific change:
    Control: Current sales page structure per Subsection A, Section 4.3 —
    Mechanism section (The Honest System, B5) appears before the Social
    Proof Block.

    Variant: Social Proof Block (3 specific testimonials) moved above the
    Mechanism section. Reader sees peer validation before the system
    explanation.

HYPOTHESIS: "We believe placing social proof before the mechanism section
(variant) will improve scroll-to-CTA rate because this audience — Stage 5
market sophistication, high skepticism — uses peer validation as a
credibility filter before investing attention in a product explanation.
The social proof cascade principle (Subsection E, #6) recommends layering
proof types in sequence, and Subsection D (Structural Patterns, finding
on testimonial placement) shows distributed proof outperforms bottom-stacked
proof. Moving the first proof block earlier tests whether earlier = better."

TEST TYPE: Structural

SUCCESS METRIC:
  - Primary: Scroll depth to first CTA (do more readers reach the buying
    decision point?)
  - Secondary: Conversion rate (does earlier proof improve or reduce purchase
    rate?); time on page (are readers engaging more or less with the mechanism
    section when it follows proof?)

LEARNING OUTCOME:
  - If variant wins: This audience needs social validation before they will
    invest attention in understanding a mechanism. Restructure all long-form
    pages to lead with proof. Test moving expert credibility signals
    (practitioner endorsements) even earlier — above the headline subhead.
  - If control wins: This audience needs to understand the system before they
    find testimonials credible. The mechanism section earns the right for proof
    to land. Keep the current section order. This aligns with the cognitive
    load principle (Subsection E, #5) — proof without context is noise.
  - If no significant difference: Section order between proof and mechanism is
    not a bottleneck. The sections themselves may need improvement. Move to a
    P2 messaging test on the mechanism section content (how B5 is presented).

TAGS:
  - Hypothesis ID: H-002
  - Test type: Structural
  - Difference: Control places mechanism (B5) before social proof. Variant
    places social proof before mechanism (B5). All copy is identical; only
    position changes.
  - Informing principle: Social Proof Cascade (Subsection E, #6), distributed
    testimonial placement pattern (Subsection D, Structural Patterns),
    Stage 5 market sophistication requiring credibility-first sequencing

PRIORITY: P2 (important hypothesis, but the headline and hero section — P1 —
must be validated first before optimizing mid-page section order)

SAMPLE SIZE NOTE: Requires approximately 800 visitors per variant to detect
a 20% relative difference in scroll-to-CTA rate at 95% confidence. If the
sales page receives traffic from both the presell and email, segment results
by traffic source to avoid confounding.

BELIEF CHAIN CHECK: Both versions present beliefs B3 through B8 in the
required sequence. The structural change moves the social proof block but
does not skip or reorder any belief. Each belief is still introduced once in
its correct position in the chain. Pass.

COMPLIANCE CHECK: Both versions use identical copy. If the control passes
Section 4, the variant passes automatically because only section position
changed, not content. Verified: Pass.
```

---

## QUICK-REFERENCE COMPLIANCE CHECKLIST FOR VARIANT PAIRS

Before any variant pair leaves the agent, confirm every item:

- [ ] Hypothesis template from Subsection A is complete with all fields filled
- [ ] All three LEARNING OUTCOME branches are present and specific
- [ ] HYPOTHESIS cites a specific reasoning source (belief chain, awareness level, behavioral principle, or historical pattern)
- [ ] Test type is classified as exactly one type from Subsection B
- [ ] No mixed variables within a single pair
- [ ] Priority level assigned per Subsection C criteria
- [ ] At least one active P1 test exists before proposing P2 or lower
- [ ] Variants are meaningfully different on at least 2 of 4 differentiation dimensions (Rule 2)
- [ ] All four metadata tags present (Rule 3)
- [ ] Control explicitly labeled with rationale (Rule 4)
- [ ] Sample size note included (Rule 5)
- [ ] Both versions independently satisfy belief chain sequencing (Rule 6)
- [ ] Both versions independently pass Section 4 compliance checklist (Rule 7)

---

*Document version: 1.0 | Created: 2026-02-19 | Section 8 of Copywriting Agent Implementation Plan | For use by: Copywriting agent | Not for external distribution*
