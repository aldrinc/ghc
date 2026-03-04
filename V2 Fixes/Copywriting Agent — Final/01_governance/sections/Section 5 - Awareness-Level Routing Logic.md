# Section 5: Awareness-Level Routing Logic

## Operational Specification for The Honest Herbalist Handbook Copywriting Agent

---

## 5.1 Traffic Source to Awareness Level Routing Table

Each traffic source carries an implied awareness level based on what the visitor knows before they arrive. The agent must treat these defaults as starting positions, then check override conditions before loading copy rules.

| Traffic Source | Default Awareness Level | Rationale | Override Conditions |
|---|---|---|---|
| Cold Meta ad (interest targeting) | **Problem-Aware** | Interest targeting (herbalism, natural health) confirms they have the problem and seek solutions, but they do not know this product exists. | Downgrade to Unaware if targeting is broad lifestyle-only (e.g., "yoga moms") with no health-problem signal. |
| Cold Meta ad (lookalike) | **Problem-Aware** | Lookalikes mirror existing buyers who originally had the problem. They share demographics and behavior patterns but have zero product exposure. | Upgrade to Solution-Aware if the lookalike seed is built from email subscribers who consumed educational content. |
| Meta retargeting (visited sales page) | **Solution-Aware** | They have seen the product and its category. They know a book-based herbal reference is an option. They did not buy. | Upgrade to Product-Aware if pixel data shows they scrolled past 60% of the sales page or spent more than 90 seconds. |
| Meta retargeting (added to cart) | **Product-Aware** | Cart addition signals they evaluated the product and found it viable. Something stalled the final decision. | Upgrade to Most-Aware if the cart event is less than 24 hours old and they have opened a prior email. |
| TikTok organic (viral/discovery) | **Unaware** | Discovery-feed viewers did not search for anything. They are scrolling entertainment. No problem frame exists yet. | Upgrade to Problem-Aware if the video is a stitch or reply to a health-topic creator, since the viewer chose that context. |
| TikTok paid ad | **Unaware to Problem-Aware** | Paid TikTok uses interest signals but the platform behavior is passive scrolling. Default to the lower edge. | Default to Problem-Aware if the ad group targets herbal remedy or natural medicine interest clusters specifically. |
| YouTube pre-roll ad | **Unaware** | Pre-roll is interruptive. The viewer did not choose this content. Assume no awareness frame. | Upgrade to Problem-Aware if the ad is placed contextually on herbalism or natural health channels via topic targeting. |
| YouTube organic (search-intent) | **Solution-Aware** | The viewer searched a query like "best herbal remedy reference" or "how to use herbs safely." They know the solution category. | Upgrade to Product-Aware if the search query contains the product name or brand name. |
| Google Search (branded query) | **Most-Aware** | They typed the product or brand name. They know who we are and are looking for the transaction point. | Downgrade to Product-Aware if the query adds comparison modifiers like "vs," "review," or "worth it." |
| Google Search (non-branded: "herbal remedy book") | **Solution-Aware** | They know the category (books about herbal remedies) but not this specific product. | Downgrade to Problem-Aware if the query is purely informational (e.g., "are herbal remedies safe for kids"). |
| Email list (opted in from lead magnet) | **Solution-Aware** | They exchanged their email for educational content. They know the solution category. They have not evaluated this product yet. | Upgrade to Product-Aware if they have opened 3 or more emails in the nurture sequence, indicating sustained engagement with our content. |
| Email list (purchased previous product) | **Most-Aware** | They bought from us before. They trust the brand. They need only a reason to buy this specific product now. | Downgrade to Product-Aware if the previous purchase was more than 12 months ago or in a different product category. |
| Affiliate/partner referral | **Solution-Aware** | The affiliate pre-framed the solution category but the visitor has not evaluated this product directly. Trust is borrowed from the affiliate, not earned by us. | Upgrade to Product-Aware if the affiliate's content included a detailed review or walkthrough of the product. |
| Direct traffic (typed URL / bookmark) | **Product-Aware** | They have the URL, which means prior exposure. They know the product exists and are returning deliberately. | Upgrade to Most-Aware if a returning-visitor cookie is present and their previous session exceeded 2 minutes on the sales page. |
| Blog/SEO organic | **Problem-Aware** | They searched a problem-level query and landed on educational content. They know they have a problem. They do not yet know our product. | Upgrade to Solution-Aware if the blog post they landed on explicitly mentions the product category (reference books, herbal guides). |

---

## 5.2 Per-Awareness-Level Copy Construction Rules

### Level 1: Unaware

| Rule Category | Specification |
|---|---|
| **Lead strategy** | The first 100 words must open with a vivid, emotionally recognizable scene or identity statement that does not mention herbs, remedies, or books. Lead with who they are, not what we sell. Example direction: a moment of parental worry, a kitchen-table decision, a late-night search spiral. |
| **Headline formula** | Identity-first or story-first. The headline names the reader or names a feeling. It never names the product or the solution category. Structural principle: "If you have ever [universal emotional moment], this matters." |
| **Section emphasis** | 60% of space goes to world-building and problem crystallization. 25% to bridge (connecting their feeling to the solution category). 15% to product introduction and CTA. |
| **Proof approach** | Lead with narrative proof: a single relatable story or testimonial that mirrors the reader's internal experience. No clinical citations yet. Social proof limited to identity-matching ("Thousands of moms like you..."). |
| **CTA approach** | Soft CTA only. Language: "See what this looks like" or "Learn more." Never "Buy now." One CTA, placed only at the end. |
| **Word count implication** | Longer. 800-1,200 words for a presell; 150-250 words for an ad. The reader needs more context because they have none. |
| **Agitation ceiling** | Level 2 of 5 on the Subsection A agitation scale. Acknowledge discomfort; do not amplify fear. Never invoke danger to children or medical emergencies at this stage. |
| **What to avoid** | Do not lead with the product. Do not cite studies. Do not use jargon (adaptogens, tinctures, contraindications). Do not assume they want an herbal book. |
| **Agent directive** | Make the reader feel recognized before they learn anything about the product. |

### Level 2: Problem-Aware

| Rule Category | Specification |
|---|---|
| **Lead strategy** | The first 100 words must name the specific problem clearly and validate it. "You already know something is off" is too vague. "You want to use natural remedies for your family but you are not sure which ones are actually safe" is precise. |
| **Headline formula** | Problem-crystallization. The headline articulates the problem better than the reader can. Structural principle: "The real reason [problem persists] is [surprising but credible root cause]." |
| **Section emphasis** | 40% problem crystallization with specifics. 30% solution-category education (why a reference book solves this class of problem). 20% product introduction. 10% CTA. |
| **Proof approach** | Lead with "situation proof": testimonials or data points that validate the problem is real and widespread. Introduce one credibility marker (author qualification or a single study) when bridging to the solution. |
| **CTA approach** | Transitional CTA. Language: "See how this works" or "Find out if this is right for you." One primary CTA after the product introduction; one optional secondary CTA mid-page if copy exceeds 600 words. |
| **Word count implication** | Medium-long. 600-900 words for presell; 100-180 words for ad. Less world-building needed, but the bridge from problem to solution category must be thorough. |
| **Agitation ceiling** | Level 3 of 5. Name real consequences of inaction (using the wrong herb, relying on unverified internet advice) but do not catastrophize. |
| **What to avoid** | Do not skip the solution-category step and jump straight to the product. Do not assume they know that a book is the right format. Do not use competitor-bashing; this audience distrusts hype. |
| **Agent directive** | Prove you understand their problem better than anyone else does, then show them the category of solution before showing the product. |

### Level 3: Solution-Aware

| Rule Category | Specification |
|---|---|
| **Lead strategy** | The first 100 words must acknowledge they already know the solution category (herbal reference resources) and immediately differentiate this product's mechanism. "You have seen the herbal guides. Here is what none of them tell you about safety." |
| **Headline formula** | Differentiation-first. The headline draws a line between this product and the category norm. Structural principle: "[Solution category] exists everywhere. This is the first one that [unique mechanism]." |
| **Section emphasis** | 20% problem recap (brief, validating). 40% mechanism and differentiator. 25% proof and credibility. 15% CTA and risk reversal. |
| **Proof approach** | Lead with mechanism proof: explain *how* the book is structured differently (safety-first framework, contraindication flags, dosage specificity). Follow with author credentials and 2-3 testimonials that specifically praise the differentiator, not just the outcome. |
| **CTA approach** | Direct CTA. Language: "Get the Handbook" or "Start using it today." Primary CTA after the proof section; secondary CTA after the mechanism section. Two CTA placements maximum. |
| **Word count implication** | Medium. 500-800 words for a sales page entry; 80-140 words for ad. The reader does not need to be convinced a book is the right format; they need to be convinced *this* book is. |
| **Agitation ceiling** | Level 3 of 5. Agitation targets the inadequacy of alternatives, not the original problem. "The problem with most herbal guides is..." not "Your family is at risk." |
| **What to avoid** | Do not re-explain why herbal remedies matter; they already know. Do not make unsubstantiated superiority claims. Do not use "unlike the competition" language; use "here is what we include that you will not find elsewhere." |
| **Agent directive** | Make the unique mechanism so clear that the reader could explain it to someone else in one sentence. |

### Level 4: Product-Aware

| Rule Category | Specification |
|---|---|
| **Lead strategy** | The first 100 words must address the specific hesitation keeping them from buying. They know the product. They have not acted. Open with the objection, not the pitch. "You have seen the Handbook. You are probably wondering if it is really different from the free information you can find online." |
| **Headline formula** | Objection-resolution or decisive proof. Structural principle: "Here is the one thing you still need to know about [product] before you decide." |
| **Section emphasis** | 10% problem/solution recap (one paragraph maximum). 30% objection handling (price, format, differentiation from free resources). 35% concentrated proof (testimonials, specifics, credentials). 25% CTA with risk reversal and urgency. |
| **Proof approach** | Lead with outcome proof: specific testimonials describing results. Include at least one "skeptic-converted" testimonial. Stack proof: testimonial, then credential, then content sample, then guarantee. |
| **CTA approach** | Assertive CTA. Language: "Get your copy now" or "Join [X] women who already have theirs." CTA appears 2-3 times. Include risk reversal language adjacent to every CTA instance. |
| **Word count implication** | Shorter. 400-600 words for retargeting page; 60-120 words for ad. They have context. Excess copy signals desperation. |
| **Agitation ceiling** | Level 2 of 5. Agitation targets cost of delay, not the original problem. Light only. "Every week without a trusted reference is another week of guessing." |
| **What to avoid** | Do not re-pitch the full mechanism. Do not repeat the sales page. Do not introduce new concepts; resolve existing doubts. Do not increase agitation to force a decision; this audience will recoil from pressure. |
| **Agent directive** | Remove the last obstacle between the reader and the purchase by answering the objection they have not spoken aloud. |

### Level 5: Most-Aware

| Rule Category | Specification |
|---|---|
| **Lead strategy** | The first 100 words must present the offer immediately: product name, price, what they get, and the fastest path to action. No warm-up. No storytelling. |
| **Headline formula** | Offer-forward or urgency-forward. Structural principle: "[Product Name] — [offer detail or time-limited element]. [CTA verb]." |
| **Section emphasis** | 50% offer details (what is included, bonuses, guarantee, price). 30% CTA and transaction mechanics. 20% light social proof (a single testimonial or user count). |
| **Proof approach** | Minimal. One strong testimonial or a social proof number ("12,000 copies sold"). The reader is already convinced. Excess proof introduces doubt at this stage. |
| **CTA approach** | Immediate and dominant. Language: "Get it now," "Buy the Handbook — $49." CTA is the first element after the headline and repeats at page bottom. Button styling takes priority. |
| **Word count implication** | Shortest. 200-400 words for a landing page. 40-80 words for an ad or email. Every word past the offer is friction. |
| **Agitation ceiling** | Level 1 of 5. Minimal to zero agitation. The reader is ready. Agitation at this stage reads as manipulation and will damage trust with this audience. |
| **What to avoid** | Do not re-tell the story. Do not re-explain the mechanism. Do not introduce new objections by trying to preemptively handle them. Do not bury the CTA below the fold. |
| **Agent directive** | Get out of the way and let them buy. |

---

## 5.3 Multi-Touch Awareness Progression Map

### Standard Path

| Touch Point | Awareness Entering | Awareness Leaving | What Must Happen |
|---|---|---|---|
| Cold ad (Meta/TikTok/YouTube) | Unaware or Problem-Aware | Problem-Aware or Solution-Aware | The reader must leave with a named, crystallized problem and curiosity about a specific *type* of solution. They must click through. |
| Presell page (article/advertorial) | Problem-Aware or Solution-Aware | Solution-Aware or Product-Aware | The reader must leave believing that a safety-first herbal reference book is the right solution format AND that this specific book has a credible differentiator. They must click through to the sales page. |
| Sales page | Solution-Aware or Product-Aware | Product-Aware or Most-Aware | The reader must leave with all major objections resolved, sufficient proof to justify the purchase, and a clear understanding of what they receive for $49. They must click the buy button. |
| Checkout page | Most-Aware | Purchase complete | The reader must experience zero friction, see the guarantee restated, and complete payment. Introduce no new decisions. |

### Non-Standard Path: Direct to Sales Page

| Touch Point | Awareness Entering | Awareness Leaving | What Must Happen |
|---|---|---|---|
| Sales page (direct traffic, bookmark, branded search) | Product-Aware or Most-Aware | Most-Aware | The page must surface the offer and CTA within the first viewport. Extended copy below serves lower-awareness visitors who arrived through other means. The top of page handles this path; the middle and bottom handle others. |

### Non-Standard Path: Email to Sales Page

| Touch Point | Awareness Entering | Awareness Leaving | What Must Happen |
|---|---|---|---|
| Email (nurture sequence) | Solution-Aware | Product-Aware | The email must accomplish the bridge from "I know the category" to "I understand this specific product's unique value." The email is the presell. |
| Sales page (from email click) | Product-Aware | Most-Aware | The reader arrives pre-educated. The sales page must resolve remaining objections and present the offer. The reader should not have to scroll past content they already received in the email. Use anchor links or a dedicated landing variant. |

### Non-Standard Path: Retarget to Sales Page

| Touch Point | Awareness Entering | Awareness Leaving | What Must Happen |
|---|---|---|---|
| Retargeting ad (visited page) | Solution-Aware or Product-Aware | Product-Aware | The ad must address the likely reason they left without buying: price uncertainty, trust gap, or distraction. Use objection-resolution copy, not a repeat of the original pitch. |
| Sales page (from retargeting click) | Product-Aware | Most-Aware | Identical to the direct-traffic path. Top of page must surface the offer fast. If using a dedicated retargeting landing page, skip all content above Product-Aware. |

---

## 5.4 Dynamic Routing Decision Tree

The agent executes this sequence before writing any copy asset.

```
STEP 1: IDENTIFY TRAFFIC SOURCE
  └─ Input: The brief or task must specify the traffic source.
  └─ If the traffic source is not specified → STOP. Ask: "What traffic source
     will deliver visitors to this page?"
  └─ If specified → Look up default awareness level in Section 5.1 table.
     Record it as WORKING_LEVEL.

STEP 2: CHECK OVERRIDE CONDITIONS
  └─ Read the Override Conditions column for the identified traffic source.
  └─ For each override condition, evaluate:
       - Is the condition met based on the brief or available data?
       - YES → Adjust WORKING_LEVEL up or down as specified. Log the
         adjustment and reason.
       - NO → WORKING_LEVEL remains unchanged.
  └─ If multiple overrides conflict → Use the LOWER awareness level.
     Rationale: Under-estimating awareness wastes words but does not lose
     the reader. Over-estimating awareness loses the reader entirely.

STEP 3: CHECK FOR MULTI-LEVEL PAGE REQUIREMENT
  └─ Does this page receive traffic from more than one source?
       - YES → Go to Section 5.5 (Cross-Level Conflict Rules) before
         proceeding.
       - NO → Continue.

STEP 4: LOAD PER-LEVEL COPY CONSTRUCTION RULES
  └─ Retrieve the full rule set for WORKING_LEVEL from Section 5.2.
  └─ Load: lead strategy, headline formula, section emphasis, proof
     approach, CTA approach, word count range, agitation ceiling,
     avoidance list, agent directive.

STEP 5: SELECT PAGE-TYPE TEMPLATE
  └─ Cross-reference WORKING_LEVEL with the page type (ad, presell, sales
     page, email, checkout) from Section 2 templates.
  └─ If the page type does not have a template for this awareness level
     → Use the nearest lower-level template and annotate the gap.

STEP 6: VERIFY PROGRESSION FIT
  └─ Using the Multi-Touch Progression Map (Section 5.3), confirm:
       - The entering awareness level matches WORKING_LEVEL.
       - The leaving awareness level is achievable within the word count
         range for this level.
       - The "What Must Happen" requirement is addressable with the loaded
         copy rules.
  └─ If any check fails → Flag the misalignment. Propose a revision to
     the funnel sequence or request a bridging asset.

STEP 7: BEGIN DRAFTING
  └─ Open with the lead strategy for WORKING_LEVEL.
  └─ Apply the headline formula.
  └─ Allocate section space per the section emphasis percentages.
  └─ Do not exceed the agitation ceiling.
  └─ Follow the agent directive as the governing constraint for every
     sentence.
```

---

## 5.5 Cross-Level Conflict Rules

### When a Single Page Must Serve Multiple Awareness Levels

This occurs most commonly on the main sales page, which receives traffic from presell pages (Solution-Aware), retargeting ads (Product-Aware), direct visits (Product-Aware to Most-Aware), and occasionally cold clicks (Problem-Aware).

**Resolution Protocol:**

**Rule 1: Prioritize the highest-volume awareness level for the page structure.**
Identify the traffic source that delivers the most visitors. That source's awareness level dictates the page's lead, headline, and first-screen architecture. For The Honest Herbalist Handbook's main sales page, the highest-volume source is presell traffic (Solution-Aware). Therefore, the page leads at Solution-Aware.

**Rule 2: Serve higher-awareness visitors with early CTA placement and a fast-path.**
Place a clearly visible CTA with product name, price, and buy button within the first viewport. Product-Aware and Most-Aware visitors can act immediately without scrolling. This does not disrupt the Solution-Aware reader because a CTA early on a page reads as confidence, not pressure, when it is a single quiet element rather than the dominant design feature.

**Rule 3: Serve lower-awareness visitors with below-the-fold depth.**
If a meaningful percentage of traffic arrives at Problem-Aware (e.g., from SEO or broad ads), include a collapsible or scroll-depth section below the primary sales argument that recaps the problem and the solution category. Label it contextually (e.g., "New to herbal remedies? Start here.") so higher-awareness visitors skip it without confusion.

**Rule 4: Never write the lead for the lowest awareness level present.**
The lead is the highest-cost real estate on the page. Writing it for Problem-Aware visitors when 70% of traffic is Solution-Aware or higher will lose the majority to provide context for the minority. The minority gets a secondary entry point, not the lead.

### When to Split Into Separate Pages

Split into distinct pages when ALL three of the following conditions are true simultaneously:

1. **The awareness gap is 3 or more levels.** A page serving both Unaware and Product-Aware traffic cannot reconcile their needs with structural layering. The lead that works for one alienates the other.

2. **The lower-awareness segment represents more than 30% of total page traffic.** Below 30%, the below-the-fold depth section in Rule 3 is sufficient. Above 30%, those visitors deserve a page optimized for them.

3. **Conversion data shows the page underperforms for one segment by more than 40% relative to the other.** If Solution-Aware visitors convert at 4% and Problem-Aware visitors at 2.2%, that is a 45% relative underperformance. Split the page.

If any one of the three conditions is false, use a single page with the layering protocol from Rules 1 through 4.

### Priority Hierarchy When Splitting Is Not Feasible

If operational constraints prevent page splitting (budget, tooling, team bandwidth), apply this priority stack:

1. **Most-Aware gets a fast-path CTA** (non-negotiable; these are the easiest conversions to lose).
2. **The dominant traffic source's awareness level controls the lead and headline.**
3. **The secondary awareness level gets a dedicated mid-page section.**
4. **The tertiary awareness level gets a linked-out resource or a single anchor section at page bottom.**
5. **Any awareness level below tertiary is served by a separate asset or not served on this page.**

---

*End of Section 5. This document governs all awareness-level routing decisions. The agent must execute the Decision Tree (5.4) before drafting any copy asset. No copy task begins without a confirmed WORKING_LEVEL.*
