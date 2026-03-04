# Promise Contract System

## What a Promise Contract Is

A Promise Contract is the binding specification between a headline and its page body. Every headline opens an information gap -- an open loop that the reader's brain demands to close. The Promise Contract is the formal declaration of what the page body must deliver to close that loop.

Without a Promise Contract, a headline is an open loop with no guarantee of closure. The reader clicks expecting specific information. If the body does not deliver it, the result is a trust violation: the headline made a promise the page did not keep.

The Promise Contract converts "payable" from a vague construction intent into a concrete, testable gate. It is created at headline-writing time and verified after the page body is written.

**Core principle:** A headline without a Promise Contract is incomplete and cannot be shipped to a page writer.

---

## The 4 Fields

Every Promise Contract contains exactly four fields:

### 1. LOOP_QUESTION

The single, obvious, instant question the reader's brain asks after reading the headline. This should be expressible in one or two words: *What?* *Which?* *Why?*

If you cannot state the loop question in one or two words, the headline's open loop is unclear and needs rework.

**Examples:**
- "The most dangerous thing missing from 90% of herb guides" --> Loop question: **What is it?**
- "After reviewing 300 herbs, one safety problem showed up in every guide" --> Loop question: **What problem?**

### 2. SPECIFIC_PROMISE

The concrete description of what information or content the reader expects to find on the page after clicking the headline. This must be specific, not vague.

**Wrong:** "Useful information about dosing"
**Right:** "Specific physiological consequences of incorrect herbal dosing"

To extract this field, answer: "If the reader clicked this headline, what specific information or content would she expect to find on the page?"

### 3. DELIVERY_TEST

A falsifiable boolean test that starts with "The body must contain..." This test converts the SPECIFIC_PROMISE into a concrete assertion that someone reading only the body text (without the headline) can determine as pass or fail.

**Quality standard:** Two different writers reading the body must agree on whether the DELIVERY_TEST is satisfied. If reasonable people could disagree, the test is too vague.

**Wrong:** "The reader learns something useful" (not falsifiable, not specific)
**Right:** "The body must contain at least one named physiological consequence of incorrect herbal dosing" (concrete, falsifiable, two writers would agree)

### 4. MINIMUM_DELIVERY

Using the page-type template (Section 2 of the page structure), this field identifies:
- Which template section must **begin** paying off the promise
- Which template section must **complete** the payoff

**Critical rule:** The promise must begin being paid off BEFORE the structural pivot to the product or solution category. If the promise payoff only arrives after the product introduction, the reader experiences the preceding content as bait.

---

## How to Extract a Promise Contract from a Headline (Step 4.5 Procedure)

This step is mandatory for every headline produced by the headline engine. Execute it immediately after writing each headline in Step 4.

### Extraction Sequence

**For each headline:**

1. **State the LOOP_QUESTION.** Already defined during headline construction (Step 4, item 1). Write it as a one-word or two-word question.

2. **Define the SPECIFIC_PROMISE.** Answer: "If the reader clicked this headline, what specific information or content would she expect to find on the page?" Write the answer as a concrete description.

3. **Write the DELIVERY_TEST.** Convert the SPECIFIC_PROMISE into a falsifiable boolean starting with "The body must contain..." Make it specific enough that pass/fail determination requires no subjective judgment.

4. **Set the MINIMUM_DELIVERY.** Using the page-type template, identify which section must begin paying the promise and which must complete it. Verify the payoff begins before the product/solution pivot.

### The Red Flag Test

After extracting the contract, run this check:

**Does the SPECIFIC_PROMISE describe a different article than the one the page-type template would produce?**

If yes, you have a structural mismatch. Three options:

1. **The headline is wrong for this page type.** Pick a different headline from the HookBank whose promise aligns with the template's natural output.
2. **The page body needs a structural modification.** Plan that modification explicitly before drafting -- do not hope it works out.
3. **The headline's open loop needs reframing.** Adjust the loop so its promise aligns with what the page can actually deliver.

A headline that opens a loop the page cannot close is a trust violation. The Promise Contract catches this BEFORE the page is written, not after.

### Promise Contract Quality Rules

1. Every headline must have a PROMISE_CONTRACT. This is not optional metadata -- it is a structural requirement.
2. The DELIVERY_TEST must be concrete enough that two different writers would agree on pass/fail.
3. If the DELIVERY_TEST cannot be written as a concrete, falsifiable assertion, the headline has a structural problem -- the open loop is too vague or the page type cannot accommodate the promised content.

---

## How the Promise Contract Governs Body Copy Writing

The Promise Contract is the bridge between headline and body. Once a headline is selected for a page, its Promise Contract becomes the body writer's primary specification.

### Governing Rules

1. **The body writer receives the Promise Contract as a binding input.** It is not a suggestion -- it is a delivery requirement.

2. **The DELIVERY_TEST is the minimum bar.** The body must satisfy it. A body that is well-written but fails the DELIVERY_TEST is a failed body, regardless of other qualities.

3. **The MINIMUM_DELIVERY field dictates pacing.** The promise must begin being paid off in the specified template section, not later. If the contract says "begin payoff in Section 2," the body writer cannot defer the promise to Section 4.

4. **The promise must be paid before the pivot.** In advertorial templates, the promise must be substantially delivered before Section 4 (the pivot to the solution category). In sales page templates, before Section 3 (the offer introduction). If the reader encounters the product before the promise is paid, the page reads as bait-and-switch.

5. **The LOOP_QUESTION shapes the lead.** The first 100-200 words of body copy should make the reader feel the loop question more intensely, not begin answering it. The answer comes at the MINIMUM_DELIVERY point.

---

## How the Congruency Scorer Enforces the Promise Contract (PC1-PC4 Tests)

The headline-body congruency scorer includes four Promise Contract tests that verify the body delivers what the headline promised.

### PC1: Promise Presence

**Test:** Does the body contain content that addresses the SPECIFIC_PROMISE?

**What it checks:** The body must contain identifiable content that maps to what the headline promised. If the headline promises "the one number your herb guide doesn't give you" and the body never mentions a specific number or quantitative element, PC1 fails.

**Failure means:** The body ignores the headline's promise entirely.

### PC2: Delivery Test Satisfaction (HARD GATE)

**Test:** Does the body satisfy the DELIVERY_TEST extracted in Step 4.5?

**What it checks:** The concrete, falsifiable boolean test. "The body must contain at least one named physiological consequence of incorrect herbal dosing" -- does it? Pass or fail, no partial credit.

**PC2 is a hard gate.** A body that fails PC2 is rejected regardless of all other scores. This is the non-negotiable enforcement mechanism of the Promise Contract system. See the PC2 Hard Gate Rule below for details.

**Failure means:** The headline made a specific promise and the body did not deliver it. This is a trust violation.

### PC3: Delivery Timing

**Test:** Does the promise payoff begin at or before the MINIMUM_DELIVERY section?

**What it checks:** The promise is not deferred past the specified template section. If the contract says payoff must begin in Section 2, and the first relevant content appears in Section 4, PC3 fails.

**Failure means:** The promise is technically present but arrives too late -- after the reader has already encountered the product pitch, causing a bait-and-switch experience.

### PC4: Claim Ceiling Compliance

**Test:** Does the body stay within the claim ceiling set by the headline?

**What it checks:** The headline sets an upper bound on what the page can claim. If the headline promises "what most guides get wrong about drug interactions," the body cannot escalate to "cure your disease" or make claims the headline did not open the door to.

**Failure means:** The body overshoots the headline, making claims the reader was not primed for. This triggers skepticism and breaks trust.

---

## The PC2 Hard Gate Rule

PC2 (Delivery Test Satisfaction) operates as an absolute gate in the congruency scoring system.

### How It Works

- If PC2 fails, the body receives a **DISQUALIFIED** status regardless of scores on all other dimensions.
- No amount of good writing, emotional resonance, or structural quality compensates for a failed delivery test.
- The body is rejected and must be revised until PC2 passes.

### Why It Exists

The entire Promise Contract system exists to solve one problem: headlines that open loops the body never closes. This is the most common trust violation in direct response copy. The reader clicks expecting X, reads 2,000 words, and never gets X.

PC2 is the enforcement mechanism. It converts "you should deliver what you promised" from a principle into a hard gate that cannot be overridden.

### Interaction with Other Gates

PC2 operates independently of Brand & Compliance hard gates (BC1-BC3). A body can be:
- **DISQUALIFIED by BC gates** -- contains banned words or prohibited claims
- **DISQUALIFIED by PC2** -- fails to deliver the headline's promise
- **DISQUALIFIED by both** -- both violations present

Each gate operates independently. Passing one does not compensate for failing another.

---

## Common Failure Modes

### Failure Mode 1: Vague Promise ("The reader learns something useful")

**Symptom:** The DELIVERY_TEST cannot be written as a concrete assertion. The SPECIFIC_PROMISE is too broad to test.

**Root cause:** The headline's open loop is vague. It creates general curiosity but does not specify what information the reader will receive.

**Fix:** Sharpen the headline's open loop. The loop must promise a specific type of information, not a general feeling of usefulness.

### Failure Mode 2: Unpayable Promise (headline promises content the page type cannot deliver)

**Symptom:** The Red Flag Test fires -- the SPECIFIC_PROMISE describes an article that the page-type template does not produce.

**Root cause:** Mismatch between headline ambition and page-type structure. Common when headline writers do not reference the template before writing.

**Fix:** Either change the headline to align with the template, or plan an explicit structural modification to the template to accommodate the promise.

### Failure Mode 3: Late Delivery (promise payoff arrives after the product pivot)

**Symptom:** PC3 fails. The promised content exists in the body but appears after the product has been introduced.

**Root cause:** The body writer treated the promise as secondary to the sales structure, deferring the payoff to "get to the product faster."

**Fix:** Restructure the body so the promise payoff precedes the pivot. The promise is not an obstacle to the sale -- it is the credibility foundation that makes the sale possible.

### Failure Mode 4: Ceiling Breach (body claims exceed what the headline opened)

**Symptom:** PC4 fails. The body makes claims the headline did not prime the reader for.

**Root cause:** The body writer escalated beyond the headline's scope, often because the product has benefits the headline did not reference.

**Fix:** The headline sets the claim ceiling. If additional claims need to appear, they must be introduced gradually and subordinated to the headline's primary promise. Or, select a different headline that opens a wider scope.

### Failure Mode 5: Missing Contract (headline shipped without a Promise Contract)

**Symptom:** The page writer has no DELIVERY_TEST to work against. The body is written based on general page-type structure alone, with no specific promise to fulfill.

**Root cause:** Step 4.5 was skipped during headline generation.

**Fix:** Step 4.5 is mandatory. A headline without a Promise Contract is incomplete and must not be passed to a page writer. If a headline arrives without a contract, extract one before writing the body.

### Failure Mode 6: Split Loop (headline opens two competing loops)

**Symptom:** The LOOP_QUESTION cannot be stated in one or two words because there are multiple possible questions. The SPECIFIC_PROMISE becomes ambiguous -- the reader could expect either of two different articles.

**Root cause:** The headline tried to do too much, opening two curiosity gaps instead of one.

**Fix:** Pick the stronger loop and kill the other. One headline, one loop, one promise, one contract.

---

## Integration Points

The Promise Contract system connects to three other systems:

1. **Headline Engine (Step 4.5):** Where the contract is created. Every headline must have a contract before it can be shipped.

2. **Message-Match Enforcement (WORKFLOW.md Section 7):** Message-match is headline-to-headline continuity across the conversion path. The Promise Contract is headline-to-body continuity within a single page. These are complementary: a page can pass message-match (headline extends the upstream promise) and still fail promise delivery (the body never pays what the headline promised).

3. **Self-Evaluation Checklist (WORKFLOW.md Section 12, Promise Integrity block):** The checklist includes five Promise Contract verification items:
   - Has a PROMISE_CONTRACT been extracted?
   - Is the DELIVERY_TEST concrete and falsifiable?
   - Does the DELIVERY_TEST describe content the page-type template can accommodate?
   - Is the promise paid off BEFORE the structural pivot?
   - Does the headline set a claim ceiling the page can support?

---

*The Promise Contract system is the enforcement mechanism that ensures every headline's implicit promise is delivered by the page body. It converts copy quality from a subjective judgment into a testable specification. No headline ships without a contract. No body ships without passing PC2.*
