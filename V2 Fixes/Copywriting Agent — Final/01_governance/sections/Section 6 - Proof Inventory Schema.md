# Section 6: Proof Inventory Schema & Sourcing Rules

## Operational Specification for The Honest Herbalist Handbook Copywriting Agent

**Product:** The Honest Herbalist Handbook | $49 digital herbal reference | DTC
**Audience:** Women 25-55, safety-conscious, anti-hype, "crunchy but not anti-science," Stage 5 market sophistication
**Belief chain:** B1 (herbs help) + B2 (natural does not equal safe) = foundation gate --> B3 (ecosystem broken) --> B4 (need system) --> B5 (this system exists) --> B6 (creator qualified) --> B7 (worth $49) + B8 (risk-free)
**Companion docs:** Section 2 (Page-Type Templates), Section 3 (Voice & Tone), Section 4 (Compliance Constraint Layer), Section 5 (Awareness-Level Routing Logic)

---

## Subsection A: Proof Item Schema

Every proof asset in the inventory must be cataloged using the following schema. No proof item enters the working inventory without all required fields populated. Fields marked [REQUIRED] cause rejection if empty. Fields marked [CONDITIONAL] are required only when the stated condition is true.

```
proof_item:
  id: [REQUIRED] String. Format: PROOF-[TYPE_CODE]-[SEQUENTIAL_NUMBER].
      Type codes: TEST (testimonial), DATA (data_point), AUTH (authority_signal),
      CRED (credential), CASE (case_study), MEDIA (media_mention),
      DEMO (demonstration), CERT (certification).
      Example: PROOF-TEST-001

  type: [REQUIRED] Enum. One of:
      testimonial | data_point | authority_signal | credential |
      case_study | media_mention | demonstration | certification

  content: [REQUIRED] String. The verbatim quote, stat, description, or
      asset reference. If the proof is visual (screenshot, badge image),
      describe the asset and link to the file. Maximum 500 characters for
      inline quotes. Longer items must include a truncated pull-quote plus
      a link to the full asset.

  source: [REQUIRED] Object.
      name: String. Who or what produced this proof. Person name, publication
            name, institution name, or internal designation.
      date: Date. When the proof was created or published. Format: YYYY-MM-DD.
      url: String or null. Link to the original source if publicly available.
      relationship: Enum. One of: customer | independent_expert | paid_partner |
                    affiliate | internal | media_outlet | regulatory_body.
                    Determines disclosure requirements per Section 4 Subsection E.

  verification_status: [REQUIRED] Enum. One of:
      verified: Source confirmed, quote approved for use, documentation on file.
      pending: Source identified but confirmation or approval not yet obtained.
      unverified: Cannot confirm origin or accuracy. DO NOT USE in any copy
                  until status changes.
      expired: Was verified but has passed its review_by date without re-verification.

  beliefs_supported: [REQUIRED] Array of B1-B8. Must contain at least one.
      Map to the specific beliefs this proof reinforces. A single proof item
      may support multiple beliefs but must have a primary (listed first).

  objections_handled: [REQUIRED] Array of strings. Common objections this
      proof addresses. Use standardized objection codes:
      OBJ-PRICE ("$49 is too much for a book")
      OBJ-FREE ("I can find this info free online")
      OBJ-TRUST ("How do I know this is credible?")
      OBJ-FORMAT ("I want a physical book / app / course")
      OBJ-RELEVANCE ("Will this cover herbs I actually use?")
      OBJ-SAFETY ("What if I follow advice and something goes wrong?")
      OBJ-EXPERTISE ("Who is the author to tell me about herbs?")
      OBJ-SCIENCE ("Is this evidence-based or just tradition?")
      OBJ-ACTIONABLE ("Will I actually use this or will it sit on my hard drive?")
      Empty array is acceptable only for proof items typed as certification.

  usage_constraints: [REQUIRED] Object.
      can_quote_directly: Boolean. If false, must paraphrase.
      paraphrase_only: Boolean. If true, the exact language cannot appear
                       in any customer-facing asset.
      platform_restrictions: Array of strings or empty. Platforms where this
                             proof CANNOT be used. Values: meta | tiktok |
                             youtube | google_ads | email | sales_page | all.
                             Empty array means no restrictions.
      requires_disclaimer: Boolean. If true, the agent must attach the
                           relevant disclaimer from Section 4 Subsection E
                           whenever this proof is deployed.
      disclaimer_type: [CONDITIONAL: required if requires_disclaimer is true]
                       Enum. One of: testimonial_disclaimer |
                       affiliate_disclosure | educational_disclaimer |
                       typicality_disclosure.
      expiration: Date or null. After this date, proof must be re-verified
                  before use. Null means no expiration.

  strength_rating: [REQUIRED] Object.
      rating: Enum. One of: strong | moderate | weak.
      rationale: String. One sentence explaining why this rating was assigned.
                 Must reference at least one of: source authority, specificity
                 of claim, verifiability, emotional resonance, or relevance
                 to target audience.

  best_used_in: [REQUIRED] Array of strings. Page/asset types where this
      proof is most effective. Values: presell | sales_page_hero |
      sales_page_mechanism | sales_page_social_proof | sales_page_value_stack |
      sales_page_faq | checkout | upsell | downsell | email_nurture |
      email_presale | email_cart_abandon | ad_meta | ad_tiktok | ad_youtube.
```

### Schema Validation Rules

The agent runs these checks before any proof item is added to the working inventory:

1. If `verification_status` is `unverified` or `expired`, the item is excluded from all copy drafts. No exceptions.
2. If `source.relationship` is `paid_partner` or `affiliate`, then `usage_constraints.requires_disclaimer` must be `true`. If it is not, reject the item and flag for correction.
3. If `type` is `testimonial` and the `content` references any health outcome (symptom improvement, condition change, medication change), then `usage_constraints.requires_disclaimer` must be `true` and `disclaimer_type` must be `testimonial_disclaimer` AND `typicality_disclosure`. Both are required per Section 4 Subsection B Rule 3.
4. If `beliefs_supported` contains only B7 or B8, `strength_rating.rating` must be `strong`. Weak or moderate proof cannot carry purchase-decision beliefs alone.
5. If `best_used_in` contains any ad platform value (`ad_meta`, `ad_tiktok`, `ad_youtube`), `content` must pass the Section 4 Subsection C Banned Phrase Scan. If any banned phrase is present, reject the item for ad use and restrict `best_used_in` to non-ad placements only.

---

## Subsection B: Proof Type Definitions & Usage Guidelines

| Proof Type | Definition | When to Use | Usage Rules |
|---|---|---|---|
| **Testimonial** | A direct statement from a real reader or user describing their experience with the handbook. Must be attributable to a named or anonymized-with-permission individual. | When the copy needs to demonstrate that real people with similar concerns found value. Most effective in sales page social proof sections (Sec 2 Pos 5), email nurture, and retargeting ads. Deploy when the target belief is B5 (this system works) or B6 (identity match). | 1. Every testimonial used in advertising must comply with FTC Endorsement Guides per Section 4 Subsection B Rule 3. 2. No testimonial may imply a health outcome the advertiser cannot substantiate independently. 3. If the testimonial references a specific health experience, attach both `testimonial_disclaimer` and `typicality_disclosure`. 4. Testimonials from paid partners or affiliates must carry `affiliate_disclosure`. 5. Never fabricate or composite testimonials. Each must trace to one real person. 6. Preferred format: situation + specific action taken with handbook + result expressed in educational or behavioral terms (not clinical terms). Example of compliant testimonial: "I finally felt confident giving my daughter chamomile tea because I could check the age-specific safety flags first." Example of non-compliant testimonial: "This book cured my insomnia." |
| **Data Point** | A specific, verifiable statistic from a named source. Includes research findings, survey results, market data, or usage metrics. | When the copy needs to establish scale, urgency, or credibility through numbers. Most effective in presell ecosystem indictment (B3), sales page mechanism section (B5), and value stack (B7). | 1. Every data point must include its source and date in the `source` field. Data without a traceable origin is rejected. 2. Statistics about herbs or health must come from peer-reviewed research, government databases (NIH, WHO), or named institutional reports. Blog-sourced statistics are rejected. 3. Never present a data point in a way that implies the handbook will produce the stated outcome. Frame as context: "X% of herbal supplement users report uncertainty about dosing" -- not as a promise. 4. Round numbers are acceptable for readability ("nearly 1 in 3" vs. "29.7%") but the precise figure must be on file. 5. Data older than 5 years requires `expired` flag and re-verification. |
| **Authority Signal** | A reference to a recognized institution, framework, or body of knowledge that the handbook aligns with or draws from. NOT a personal credential (see credential type). | When the copy needs to borrow trust from established institutions. Most effective for B2 (natural does not equal safe -- cite pharmacovigilance data) and B5 (this system exists -- reference the methodology's grounding). | 1. Name the institution or framework explicitly. Vague authority ("studies show," "experts agree") is prohibited per brand voice rules (Section 3). 2. Do not imply endorsement unless a formal endorsement exists and is documented. "Referenced in WHO monographs" is factual. "WHO-endorsed" requires proof of endorsement. 3. Never reference FDA in a way that implies FDA approval of herbs or the handbook. See Section 4 Subsection C item 21. 4. UK copy: do not reference individual health professionals as authority per ASA/CAP rules (Section 4 Subsection B Rule 4). |
| **Credential** | A personal qualification, certification, training, or professional experience held by the author or contributor. | When the copy needs to establish the creator's right to publish this work. Primary vehicle for B6 (creator qualified). Deploy in sales page identity bridge (Sec 2 Pos 4), presell system tease, and "about the author" sections. | 1. Every credential must be verifiable. Claimed degrees, certifications, or memberships must have documentation on file. 2. List credentials factually without inflating scope. "Certified herbalist" is acceptable if true. "Leading herbal authority" is a subjective claim requiring substantiation. 3. Do not use medical credentials (MD, RN, PharmD) to imply the handbook is medical advice. Pair any medical credential with the educational disclaimer from Section 4 Subsection E. 4. For this brand, credentials that combine scientific training with herbal practice are rated `strong`. Herbal-only or science-only credentials are rated `moderate` because the audience values the intersection. |
| **Case Study** | A structured narrative showing a specific problem, the handbook's role, and the outcome. Longer and more detailed than a testimonial. | When the copy needs to walk the reader through the handbook's decision-making process in action. Most effective on the sales page mechanism section (B5) and in email nurture sequences (B2-B4 progression). | 1. Case studies must follow the format: Situation --> Decision Point --> How the Handbook Was Used --> Outcome. 2. Outcomes must be framed in educational or behavioral terms, never clinical. "She checked the interaction flag and decided to consult her pharmacist before combining valerian with her sleep medication" -- not "She avoided a dangerous drug interaction." 3. Case studies involving children, pregnancy, or serious health conditions require legal review before use and must carry the educational disclaimer. 4. Each case study must be based on a real user's experience or a clearly marked hypothetical composite labeled as such. |
| **Media Mention** | Coverage, citation, or reference by an external publication, podcast, blog, or media outlet. | When the copy needs third-party validation to overcome skepticism. Most effective for B3 (ecosystem broken -- media coverage of herbal misinformation) and B6 (creator qualified -- press coverage of creator). | 1. Quote only with permission or within fair-use bounds. Link to the original. 2. Do not misrepresent the tone or conclusion of coverage. A passing mention is not a "feature." A mixed review is not an endorsement. 3. Outlet credibility matters for this audience. Wellness publications with scientific credibility (e.g., journals, established health media) are rated `strong`. Lifestyle publications are `moderate`. Influencer blogs are `weak` unless the influencer has documented credentials. 4. Media mentions older than 18 months should be re-verified for continued availability and relevance. |
| **Demonstration** | A sample, excerpt, screenshot, or walkthrough that shows the handbook's content or structure in action. | When the copy needs to make the product tangible. Most effective for B5 (this system exists -- show it), B4 (need a system -- demonstrate what a system looks like), and OBJ-ACTIONABLE. Deploy in sales page mechanism section and "what's inside" section (Sec 2 Pos 3 and 6). | 1. Demonstrations must show real product content, not mockups of content that does not exist. 2. Blur or redact enough to prevent the demonstration from replacing the purchase. Show the framework; do not give away complete entries. 3. Screenshots must be current to the latest product version. Outdated screenshots are flagged `expired`. 4. For this brand, demonstrations are the single highest-trust proof type because they let the skeptical buyer evaluate before committing. Prioritize demonstrations over testimonials for Solution-Aware and Product-Aware readers (Section 5 Levels 3-4). |
| **Certification** | A third-party certification, award, accreditation, or formal recognition granted to the product, the author, or the business. | When the copy needs institutional validation. Effective for B6 (creator qualified) and B8 (risk-free -- e.g., secure payment certifications, satisfaction guarantee badges). | 1. Display the actual badge, seal, or mark if license permits. Text-only references to certifications are rated one level lower than visual badge displays. 2. Certifications must be current. Expired certifications are removed from the inventory entirely, not just flagged. 3. Do not display certifications that imply government approval of herbal health claims (e.g., do not use FDA logos or create the impression of FDA certification). 4. Payment security certifications (SSL, PCI) are used on the checkout page only. |

---

## Subsection C: Proof Selection Logic

The agent follows these six rules in sequence when selecting proof for any copy asset. All six must pass. A proof item that fails any rule is excluded from that specific asset.

### Rule 1: Match Rule (Belief Alignment)

The proof item's `beliefs_supported` array must contain at least one belief that the current copy section is responsible for establishing.

- Cross-reference `beliefs_supported` with the belief assignment in the Section 2 page-type blueprint for the section being drafted.
- If the section is responsible for B5, only proof items where `beliefs_supported` includes B5 are eligible.
- A proof item supporting multiple beliefs may be used in any section responsible for at least one of those beliefs. When this occurs, position the proof so that its primary belief (first in array) aligns with the section's primary job.
- Test: Does this proof item's `beliefs_supported` array intersect with this section's assigned beliefs? YES = pass. NO = exclude.

### Rule 2: Strength Rule (Position-Based Minimum)

Different funnel positions require different proof strength minimums.

| Position | Minimum Strength | Rationale |
|---|---|---|
| Sales page hero (Sec 2 Pos 1) | Strong | First impression. Weak proof here undermines everything below it. |
| Sales page mechanism (Sec 2 Pos 3) | Moderate | Explaining how the system works. Moderate data or demonstrations suffice. |
| Sales page social proof (Sec 2 Pos 5) | Strong | This is the dedicated proof section. Only the best items belong here. |
| Sales page value stack (Sec 2 Pos 8) | Moderate | Price anchoring. Moderate data points and comparisons are sufficient. |
| Sales page FAQ (Sec 2 Pos 11) | Moderate | Objection resolution. A moderate testimonial that addresses the specific objection outperforms a strong testimonial that does not. |
| Presell | Moderate | Editorial frame limits proof density. One moderate proof item is the maximum (Section 2 presell failure mode 4). |
| Checkout | Strong | Decision anxiety is highest. Only strong trust signals (guarantee, security certs, one powerful testimonial). |
| Upsell | Moderate | Post-purchase context. One moderate proof item prevents decision fatigue. |
| Email nurture | Moderate | One proof item per email. Moderate is sufficient within a trust-building sequence. |
| Ads (all platforms) | Strong | Limited space and cold audience. Only the strongest proof competes for attention. |

- Test: Is this proof item's `strength_rating.rating` equal to or higher than the minimum for this position? YES = pass. NO = exclude.

### Rule 3: Variety Rule (Social Proof Cascade)

No two consecutive proof items in the same copy asset may share the same `type`.

- Within the sales page social proof section (Sec 2 Pos 5), sequence proof as: testimonial --> data point or demonstration --> testimonial --> authority signal. Alternate between personal (testimonial, case study) and institutional (data point, authority signal, credential, certification).
- Within email sequences, no two consecutive emails may lead with the same proof type.
- If only one proof type is available for a given belief, the agent must flag the gap and request additional proof sourcing before duplicating types.
- Test: Is this proof item a different `type` from the proof item immediately before it in this asset? YES = pass. NO = reorder or substitute.

### Rule 4: Freshness Rule (Age-Based Preference)

Proof items are ranked by recency. When two items are otherwise equivalent in match, strength, and type diversity, the newer item wins.

| Age of Proof | Status | Action |
|---|---|---|
| 0-6 months | Current | Use freely. |
| 6-12 months | Current with review flag | Usable. Flag for re-verification at next quarterly review. |
| 12-24 months | Aging | Use only if no newer equivalent exists. Must re-verify source accuracy. |
| 24+ months | Stale | Do not use in ads or presell. Usable on sales page and email only if re-verified and the content is explicitly time-independent (e.g., author credentials, historical data). |
| Data points with year-specific figures | Special handling | Any statistic referencing a specific year (e.g., "2024 survey") must be updated or removed once the referenced year is more than 2 calendar years in the past. |

- Test: Is this proof item within the acceptable age range for this asset type? YES = pass. NO = flag for re-verification or exclude.

### Rule 5: Platform Compliance Rule

Before placing any proof item in an asset destined for a specific platform, cross-reference with two sources:

1. The proof item's `usage_constraints.platform_restrictions` array. If the target platform appears in the array, exclude the item.
2. Section 4 compliance rules for the target platform. Run the proof item's `content` through the Section 4 Subsection C Banned Phrase Scan and the Section 4 Subsection F Pre-Submission Compliance Checklist (Testimonial Compliance section).

Specific platform rules for proof:

- **Meta/Instagram:** Testimonials cannot reference personal health attributes or conditions. Proof items implying the reader has a health problem ("Are you tired of...") are rejected per Section 4 Subsection A.
- **TikTok:** No proof claims that discourage professional medical consultation. Testimonials saying "I stopped going to my doctor" are rejected.
- **YouTube/Google Ads:** No unsubstantiated health testimonials. Google enforces the strictest standard: if the testimonial's implied claim cannot be independently substantiated by RCT-level evidence, it is rejected for this platform.
- **Email:** All testimonial disclaimers and affiliate disclosures must be included in the email body, not linked to an external page.

- Test: Does this proof item pass both its own `platform_restrictions` check AND the Section 4 compliance check for the target platform? YES = pass. NO = exclude from this platform.

### Rule 6: Density Guidelines

Each asset type has a maximum proof density. Exceeding density makes copy feel defensive. Falling below it leaves claims unsupported.

| Asset Type | Proof Items (Target) | Proof Items (Maximum) | Placement Logic |
|---|---|---|---|
| **Presell** | 1 | 2 | One embedded proof item in the Ecosystem Indictment section (Sec 2 Pos 3) to validate B3. If a second is used, place it in the System Tease section (Sec 2 Pos 5). Never more than one testimonial in a presell -- it breaks editorial frame. Prefer data points or authority signals. |
| **Sales Page** | 8-12 | 15 | Distribute across sections per the blueprint: 1 in Hero, 1 in Problem Recap, 2 in Mechanism, 3-5 in Social Proof, 1 in Value Stack, 1-2 in FAQ, 1 in P.S. Never cluster more than 3 consecutive proof items without intervening explanatory copy. |
| **Upsell** | 1 | 2 | One proof item in Quick Proof section (Sec 2 Pos 4). Must reference the upsell product specifically, not the core handbook. If a second is used, it goes adjacent to the CTA as a single-line pull quote. |
| **Downsell** | 0-1 | 1 | One proof item maximum. If used, place it between the Reduced Offer and CTA. Downsell copy is 200-400 words -- proof competes with clarity at this length. Omitting proof is acceptable if the downsell relies on the generosity frame. |
| **Email (Nurture)** | 1 | 2 | One proof item per email, embedded in the body as a natural part of the story or argument. Never stack proof items in email. If two are used, separate them with at least 50 words of non-proof copy. |
| **Email (Pre-Sale)** | 1-2 | 3 | One proof item in the value recap section. A second in the urgency section if it reinforces time-sensitivity (e.g., reader count, limited-time bonus). A third only if the email exceeds 250 words. |
| **Email (Cart Abandon)** | 1 | 1 | One proof item: the guarantee restatement or a single strong testimonial. Cart abandonment emails are 100-200 words. More than one proof item adds friction. |
| **Checkout** | 2-3 | 4 | Trust signals adjacent to payment fields (1-2 certification badges). Guarantee restatement below order summary (1 item). One testimonial pull quote near the submit button is optional. All proof must be visual or ultra-concise (under 25 words). |
| **Ad (Meta)** | 1 | 2 | One primary proof element in the ad copy. If a second is used, it must be a different type (e.g., stat in copy + testimonial in creative). Platform character limits naturally enforce density. |
| **Ad (TikTok)** | 1 | 1 | One proof element, delivered verbally or as on-screen text. TikTok's format does not support proof stacking -- it reads as infomercial. |
| **Ad (YouTube)** | 1-2 | 2 | One proof element in the first 15 seconds (hook). One supporting proof element in the body if the ad exceeds 30 seconds. |

- Test: Does the total count of proof items in this asset fall within the target-to-maximum range for this asset type? YES = pass. NO = add or remove proof items until within range.

---

## Subsection D: Starter Proof Inventory

The following 10 items demonstrate the schema in use. All are placeholders. Every item must be replaced with verified proof before any copy is published.

---

**Item 1**

```
id: PROOF-TEST-001
type: testimonial
content: "[PLACEHOLDER -- Replace with actual proof before use] I used to
  second-guess every herb I gave my kids. The safety flags in this handbook
  gave me a clear yes-or-no for the first time."
source:
  name: "[Placeholder: Sarah M., mother of two, verified purchaser]"
  date: 2026-01-15
  url: null
  relationship: customer
verification_status: pending
beliefs_supported: [B5, B2, B6]
objections_handled: [OBJ-SAFETY, OBJ-ACTIONABLE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: true
  disclaimer_type: testimonial_disclaimer
  expiration: 2027-01-15
strength_rating:
  rating: strong
  rationale: "Specific situation (children), specific feature (safety flags),
    emotional resonance with target audience, behavioral outcome not clinical."
best_used_in: [sales_page_social_proof, email_nurture, ad_meta]
```

---

**Item 2**

```
id: PROOF-DATA-001
type: data_point
content: "[PLACEHOLDER -- Replace with actual proof before use] A 2024 NIH-funded
  survey found that 67% of adults who use herbal supplements do not check for
  drug interactions before use."
source:
  name: "[Placeholder: National Institutes of Health / NCCIH survey]"
  date: 2024-06-01
  url: "[Placeholder URL]"
  relationship: independent_expert
verification_status: pending
beliefs_supported: [B2, B3]
objections_handled: [OBJ-FREE, OBJ-SCIENCE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: 2027-06-01
strength_rating:
  rating: strong
  rationale: "Government-sourced, specific percentage, directly validates the
    core B2 belief that natural does not equal safe."
best_used_in: [presell, sales_page_mechanism, email_nurture, ad_youtube]
```

---

**Item 3**

```
id: PROOF-AUTH-001
type: authority_signal
content: "[PLACEHOLDER -- Replace with actual proof before use] The handbook's
  safety-flag system is modeled on the pharmacovigilance frameworks used by
  the WHO Collaborating Centre for International Drug Monitoring."
source:
  name: "[Placeholder: Internal methodology documentation]"
  date: 2025-11-01
  url: null
  relationship: internal
verification_status: pending
beliefs_supported: [B5, B6]
objections_handled: [OBJ-TRUST, OBJ-SCIENCE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: null
strength_rating:
  rating: strong
  rationale: "WHO framework reference carries high institutional authority.
    Directly supports the mechanism claim without overstating."
best_used_in: [sales_page_mechanism, presell, email_nurture]
```

---

**Item 4**

```
id: PROOF-CRED-001
type: credential
content: "[PLACEHOLDER -- Replace with actual proof before use] [Author Name]
  holds a degree in clinical herbalism from [Institution] and completed
  pharmacology training at [University]. She has consulted for [X] years
  on herb-drug interaction safety."
source:
  name: "[Placeholder: Author bio and credential documentation]"
  date: 2025-09-01
  url: null
  relationship: internal
verification_status: pending
beliefs_supported: [B6]
objections_handled: [OBJ-EXPERTISE, OBJ-TRUST, OBJ-SCIENCE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: true
  disclaimer_type: educational_disclaimer
  expiration: null
strength_rating:
  rating: strong
  rationale: "Dual credential (herbal + pharmacological) directly matches the
    audience's desire for 'crunchy but not anti-science.' Verifiable."
best_used_in: [sales_page_social_proof, presell, ad_meta, ad_youtube, email_nurture]
```

---

**Item 5**

```
id: PROOF-CASE-001
type: case_study
content: "[PLACEHOLDER -- Replace with actual proof before use] A reader was
  preparing an elderberry syrup for cold season and looked up the entry. The
  handbook's interaction flag showed elderberry may affect immunosuppressant
  medications. She checked with her pharmacist, who confirmed the concern.
  She adjusted her approach before any issue arose."
source:
  name: "[Placeholder: Beta reader interview, anonymized with permission]"
  date: 2026-01-20
  url: null
  relationship: customer
verification_status: pending
beliefs_supported: [B5, B2, B4]
objections_handled: [OBJ-ACTIONABLE, OBJ-SAFETY, OBJ-FREE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: [ad_meta, ad_tiktok]
  requires_disclaimer: true
  disclaimer_type: testimonial_disclaimer
  expiration: 2027-01-20
strength_rating:
  rating: strong
  rationale: "Specific herb, specific safety feature, specific outcome
    (consulted pharmacist). Demonstrates the system working as intended.
    Behavioral framing avoids clinical claims."
best_used_in: [sales_page_mechanism, sales_page_social_proof, email_nurture]
```

---

**Item 6**

```
id: PROOF-MEDIA-001
type: media_mention
content: "[PLACEHOLDER -- Replace with actual proof before use] Featured in
  [Publication Name]'s roundup of 'Herbal references that take safety
  seriously' -- [Month, Year]."
source:
  name: "[Placeholder: Wellness publication name]"
  date: 2026-02-01
  url: "[Placeholder URL]"
  relationship: media_outlet
verification_status: pending
beliefs_supported: [B6, B5]
objections_handled: [OBJ-TRUST, OBJ-EXPERTISE]
usage_constraints:
  can_quote_directly: false
  paraphrase_only: true
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: 2027-08-01
strength_rating:
  rating: moderate
  rationale: "Third-party validation from wellness media. Rated moderate
    because publication authority is unverified in this placeholder."
best_used_in: [sales_page_social_proof, ad_meta, email_presale]
```

---

**Item 7**

```
id: PROOF-DEMO-001
type: demonstration
content: "[PLACEHOLDER -- Replace with actual proof before use] Screenshot of
  the handbook's chamomile entry showing the safety-flag panel: green flag for
  general adult use, yellow flag for pregnancy (with explanation), red flag
  for interaction with blood thinners. Dosage ranges and preparation methods
  visible. Full entry redacted below the fold."
source:
  name: "Internal: Product screenshot, chamomile entry v2.1"
  date: 2026-02-10
  url: "[Internal asset link]"
  relationship: internal
verification_status: pending
beliefs_supported: [B5, B4, B2]
objections_handled: [OBJ-ACTIONABLE, OBJ-FREE, OBJ-RELEVANCE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: null
strength_rating:
  rating: strong
  rationale: "Direct product demonstration. Highest-trust proof type for this
    audience. Shows the mechanism instead of describing it. Uses a universally
    recognized herb (chamomile) the reader likely has at home."
best_used_in: [sales_page_mechanism, sales_page_social_proof, ad_meta, ad_youtube, email_nurture]
```

---

**Item 8**

```
id: PROOF-CERT-001
type: certification
content: "[PLACEHOLDER -- Replace with actual proof before use] 30-Day
  Money-Back Guarantee badge. Full refund, no questions asked, within 30
  days of purchase."
source:
  name: "Internal: Guarantee policy"
  date: 2026-01-01
  url: null
  relationship: internal
verification_status: verified
beliefs_supported: [B8]
objections_handled: [OBJ-PRICE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: null
strength_rating:
  rating: strong
  rationale: "Direct risk reversal. Addresses the final purchase barrier.
    Visual badge format increases trust per certification type rules."
best_used_in: [sales_page_value_stack, checkout, email_presale, email_cart_abandon]
```

---

**Item 9**

```
id: PROOF-TEST-002
type: testimonial
content: "[PLACEHOLDER -- Replace with actual proof before use] I have three
  shelves of herb books. This is the only one I actually open when I need to
  make a decision. The safety flags changed how I think about dosing."
source:
  name: "[Placeholder: Jessica R., herbalism hobbyist, 8 years]"
  date: 2026-02-05
  url: null
  relationship: customer
verification_status: pending
beliefs_supported: [B5, B7]
objections_handled: [OBJ-FREE, OBJ-ACTIONABLE, OBJ-PRICE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: true
  disclaimer_type: testimonial_disclaimer
  expiration: 2027-02-05
strength_rating:
  rating: strong
  rationale: "Directly addresses OBJ-FREE ('I have other books') and
    OBJ-ACTIONABLE ('the one I actually open'). Specific feature callout
    (safety flags, dosing). Experienced user lends credibility."
best_used_in: [sales_page_social_proof, sales_page_faq, email_presale, ad_meta]
```

---

**Item 10**

```
id: PROOF-DATA-002
type: data_point
content: "[PLACEHOLDER -- Replace with actual proof before use] The handbook
  covers 87 herbs, each with a safety-flag rating, 3 preparation methods,
  dosage ranges by age group, and a contraindication checklist. Total
  reference entries: 400+ pages."
source:
  name: "Internal: Product specifications"
  date: 2026-02-01
  url: null
  relationship: internal
verification_status: pending
beliefs_supported: [B5, B7]
objections_handled: [OBJ-RELEVANCE, OBJ-PRICE, OBJ-ACTIONABLE]
usage_constraints:
  can_quote_directly: true
  paraphrase_only: false
  platform_restrictions: []
  requires_disclaimer: false
  disclaimer_type: null
  expiration: null
strength_rating:
  rating: moderate
  rationale: "Specific product scope data. Rated moderate rather than strong
    because product specifications alone do not prove quality -- they prove
    quantity. Pair with a demonstration or testimonial for full effect."
best_used_in: [sales_page_value_stack, sales_page_mechanism, email_presale, checkout]
```

---

### Starter Inventory Coverage Summary

| Belief | Items Supporting | Gap Assessment |
|---|---|---|
| B1 (herbs help) | 0 direct | GAP: Need at least 1 data point or authority signal validating herbal efficacy within compliant framing. |
| B2 (natural does not equal safe) | PROOF-DATA-001, PROOF-CASE-001, PROOF-DEMO-001, PROOF-TEST-001 | Covered. Strong foundation. |
| B3 (ecosystem broken) | PROOF-DATA-001 | THIN: Need 1-2 additional items -- a media mention about herbal misinformation or a data point about contradictory online advice. |
| B4 (need system) | PROOF-CASE-001, PROOF-DEMO-001 | Adequate. Could strengthen with a data point about information overload. |
| B5 (this system exists) | PROOF-TEST-001, PROOF-AUTH-001, PROOF-CASE-001, PROOF-DEMO-001, PROOF-TEST-002, PROOF-DATA-002 | Covered. Strongest support in inventory. |
| B6 (creator qualified) | PROOF-CRED-001, PROOF-AUTH-001, PROOF-MEDIA-001 | Adequate. Media mention pending verification. |
| B7 (worth $49) | PROOF-TEST-002, PROOF-DATA-002 | THIN: Need 1 price-anchoring data point (cost of naturopath visit, cost of herbal error). |
| B8 (risk-free) | PROOF-CERT-001 | Covered for guarantee. Could add a testimonial referencing the refund policy or ease of return. |

### Objection Coverage Summary

| Objection | Items Addressing | Gap Assessment |
|---|---|---|
| OBJ-PRICE | PROOF-CERT-001, PROOF-TEST-002, PROOF-DATA-002 | Adequate. Strengthen with a price-comparison data point. |
| OBJ-FREE | PROOF-DATA-001, PROOF-CASE-001, PROOF-DEMO-001, PROOF-TEST-002 | Covered. |
| OBJ-TRUST | PROOF-AUTH-001, PROOF-CRED-001, PROOF-MEDIA-001 | Covered. |
| OBJ-FORMAT | 0 direct | GAP: Need 1 testimonial praising the digital format specifically. |
| OBJ-RELEVANCE | PROOF-DEMO-001, PROOF-DATA-002 | Adequate. |
| OBJ-SAFETY | PROOF-TEST-001, PROOF-CASE-001 | Covered. |
| OBJ-EXPERTISE | PROOF-CRED-001, PROOF-MEDIA-001 | Covered. |
| OBJ-SCIENCE | PROOF-DATA-001, PROOF-AUTH-001, PROOF-CRED-001 | Covered. |
| OBJ-ACTIONABLE | PROOF-TEST-001, PROOF-CASE-001, PROOF-DEMO-001, PROOF-TEST-002, PROOF-DATA-002 | Covered. Strongest support in inventory. |

---

*Document version: 1.0 | Section 6 of Copywriting Agent Implementation Plan | Companion to Section 2 (Page-Type Templates), Section 3 (Voice & Tone Operating Rules), Section 4 (Compliance Constraint Layer), Section 5 (Awareness-Level Routing Logic). All 10 placeholder proof items must be replaced with verified data before any copy asset enters production. Quarterly review cycle: re-verify all proof items, update freshness flags, run gap analysis against belief chain and objection matrix.*
