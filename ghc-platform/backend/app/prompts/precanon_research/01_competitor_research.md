
---

### **🔍 Master Competitor / Market Analysis Prompt**

You are an advanced research agent with **full web access** and the ability to systematically explore and summarize online data.

Your task is to perform a **deep competitor and market analysis** for the following product/service idea:

**Idea:** {{BUSINESS_CONTEXT}}  
**Structured context JSON:** {{BUSINESS_CONTEXT_JSON}}
**Category / niche (if you had to label it):** {{CATEGORY_NICHE}}

---

## **1\. Understand and Formalize the Idea**

1. Extract and write down:

   * The **core job-to-be-done** for the user.

   * The **primary ICP(s)** (ideal customer profiles).

   * The **solution type** (SaaS tool / platform / service / marketplace / content / hybrid).

   * The **monetization model** (subscription, usage-based, one-time, retainer, rev-share, etc.).

   * The **differentiating factors** (what would make this different if it existed at scale).

2. From this, define:

   * **Primary niche**: a concise phrase for the exact market this idea would sit in.

   * **Adjacent / similar niches** worth exploring:

     * Same ICP, different solution.

     * Same solution pattern, different ICP.

     * Upstream/downstream tools/services touching the same workflow.

Keep this definition visible and use it as a filter for all later steps.

---

## **2\. Discover Competitors (Direct \+ Adjacent)**

Your goal is to discover **as many battle-tested competitors as possible**. There is **no maximum list size**; continue until additional search passes return only insignificant or duplicate results.

For discovery:

* Use combinations of:

  * Niche keywords, problem statements, and ICP phrases.

  * “Alternatives to X / competitors to X” style searches when you find strong players.

  * “Best tools/services for \[job-to-be-done\]” lists, review sites, and comparison pages.

* Consider both:

  * **Direct competitors**: solving the same core problem for the same ICP, via a similar solution type.

  * **Adjacent competitors**:

    * Same ICP but different type of solution tackling a similar problem.

    * Same solution type but solving a closely related problem in the same workflow.

For each potential competitor you discover, record:

* **Name**

* **Website URL**

* **Type** (direct / adjacent)

* **Short description** of what they do and who they serve.

At this stage, **do not yet filter by success**—just collect candidates.

---

## **3\. Validate “Battle-Tested” Competitors Only**

Now filter the candidate list for **validated, battle-tested businesses**. Exclude non-serious or non-validated players.

Use evidence such as:

* **Traffic / usage**:

  * Estimated monthly visits (e.g., from tools like Similarweb-type sources, Semrush-like tools, etc.).

  * Growth or decline trend if visible.

* **Company maturity**:

  * Years in operation (based on earliest public traces: website history, press, announcements).

  * Funding (if applicable: e.g., from Crunchbase-type databases).

  * Team size (e.g., approximate employees from LinkedIn-style data).

* **Commercial proof**:

  * Visible pricing page or sales motion.

  * Customer logos, testimonials, case studies, or notable clients.

  * Partnerships, integrations, app store listings, or marketplace presence.

* **Market visibility**:

  * Mentions in credible lists, reviews, or “top X tools” articles.

  * Presence in relevant directories / platforms.

**Validation rule:**

* Include only companies where there is **clear evidence of non-trivial traction** (e.g., meaningful traffic, funding, team size, or visible customer base).

* Explicitly **exclude**:

  * Very new products with no visible traction.

  * Hobby projects with negligible presence.

  * Obvious dead/abandoned products.

Document **why** each selected competitor passes the “battle-tested” bar in 1–2 bullet points.

---

## **4\. Assess Success & “Are They Likely Making Money?”**

For each validated competitor, estimate whether they are **likely generating meaningful revenue** and how strong they are relative to others.

Use a combination of:

* **Traffic / reach**:

  * Estimated monthly website visits.

  * Traffic trend (growing / stable / declining).

* **Monetization strength**:

  * Clarity of their pricing and offer (is it geared to serious buyers?).

  * Presence of enterprise/annual plans, upsells, add-ons.

* **Funding & team scale**:

  * Funding stage and amount (bootstrapped with visible scale is also a strong signal).

  * Team size and hiring activity.

* **Customer base & positioning**:

  * Number and quality of customer logos.

  * Testimonials, case studies, and verticals.

* **Market penetration proxies**:

  * Review counts and ratings on relevant platforms (G2, Capterra, Trustpilot, app stores, etc.).

  * Brand search volume if available.

For each competitor, provide:

1. A **success assessment**:

   * Overall qualitative label:

     * e.g., **“Dominant”, “Strong”, “Moderate”, “Niche but solid”, “Weak/uncertain”**.

   * A **short justification** (2–4 sentences) referencing concrete signals.

2. A **binary/graded money-making verdict**:

   * e.g., **“Very likely making substantial revenue”**, **“Likely making modest but real revenue”**, **“Unclear / marginal”**.

   * Explain which signals drive this conclusion.

Where possible, also compute or infer a **composite success score** (e.g., 0–100) combining:

* Traffic level

* Growth trend

* Funding/team maturity

* Market visibility

* Evidence of paying customers

Explain briefly how you’re weighting these factors.

---

## **Output format (critical)**

Return **only** the following tagged blocks:

```
<SUMMARY>...concise summary of the findings (bounded)</SUMMARY>
<CONTENT>...full detailed write-up with competitor list, validation signals, and assessments...</CONTENT>
```

---

## **5\. Rank Competitors by Success**

Produce a **ranked list** of competitors from strongest to weakest **based on actual performance**, not just brand recognition.

* Use the composite score and qualitative judgment.

* Break ties with:

  * Market penetration proxies.

  * Longevity and durability.

  * Depth of product (breadth of features, integrations, ecosystem).

Output:

1. A **ranked narrative list** (bulleted or numbered) with:

   * Rank

   * Name

   * One-line description

   * Success label (Dominant / Strong / etc.)

   * Money-making verdict

2. Then a **structured table** (see next section).

---

## **6\. Output a Detailed Competitor Table (No Max Size)**

Create a **comprehensive table** including **all validated competitors you found**. There is **no maximum list size**; include as many as you can validate as meaningful.

Use columns such as (expand if helpful):

* **Rank**

* **Company name**

* **Website**

* **Type** (direct / adjacent)

* **Primary ICP**

* **Core value proposition (short)**

* **Estimated monthly traffic** (with source if possible)

* **Traffic trend** (growing / stable / declining)

* **Funding info** (raised amount \+ stage, or “bootstrapped / unknown”)

* **Approx. team size**

* **Evidence of traction** (1–3 bullet points)

* **Success label** (Dominant / Strong / Moderate / Niche but solid / Weak-uncertain)

* **Money-making verdict** (with 3–7 word justification)

* **Composite success score** (0–100, if used)

* **Geography / primary markets**

* **Primary acquisition channels** (inferred: SEO / paid ads / outbound / partnerships / PLG, etc.)

* **Facebook Page URL** (if exists, the comapny's Facebook page URL)

Make sure the table is **machine-usable** (e.g., Markdown table or clearly structured so it can be exported to a spreadsheet).

---

## **7\. Map Websites, Landing Pages, and Funnels**

For each **top-tier competitor** (e.g., top 10–20 by rank), analyze their **online presence and marketing funnels**.

1. **Core assets:**

   * Main website URL.

   * Key navigation sections (e.g., Product, Solutions, Pricing, Resources, Blog).

2. **Critical landing pages** (collect URLs wherever possible):

   * **Home page**

   * **Pricing page**

   * **Primary product/feature landers**

   * **ICP- or vertical-specific landers** (e.g., “for agencies”, “for SaaS”, “for e-commerce”)

   * **Campaign/offer landers**:

     * Free trial / demo / waitlist pages

     * Webinar / lead magnet landers

     * Comparison pages (e.g., “vs. \[competitor\]”)

   * **Onboarding / signup flow start pages**

3. For each key lander, briefly describe:

   * The **primary CTA** (e.g., “Start free trial”, “Book a demo”).

   * The **core angle** of the copy (e.g., time savings, revenue growth, simplicity, AI, etc.).

   * Any notable **social proof elements** (logos, stats, reviews).

   * Any **pricing / packaging hints** visible.

Output this as:

* A **table** of competitors vs. key landers (with URLs).

* Short bullet-point summaries of **standout patterns** in positioning, offers, and funnels across competitors.

---

## **8\. Synthesize Strategic Insights**

Finally, based on the entire analysis:

1. Summarize:

   * Who the **top 3–5 competitors** are and why.

   * Which niches / ICPs appear **over-served** vs **under-served**.

   * Which **business models and acquisition strategies** dominate the space.

2. Identify:

   * **Gaps** in the market where a new entrant like {{your idea}} could differentiate.

   * Potential **red flags** (e.g., hyper-competition, heavy commoditization, huge incumbents).

3. Provide **actionable recommendations** for:

   * Positioning.

   * Pricing model.

   * Feature focus.

   * Go-to-market angle to avoid direct feature-comparison wars.

---

### **Instructions for the Agent**

* **Use the web extensively** and iterate across multiple search queries.

* **Do NOT impose any arbitrary maximum on the number of competitors.** Stop only when:

  * Searches start returning duplicates and marginal players, and

  * You have already covered the meaningful, battle-tested companies.

* Be explicit about **uncertainty** when data is missing or approximate.

* Keep all outputs in **clear, structured formats** (lists \+ tables) so they can be reused in spreadsheets or other tools.
