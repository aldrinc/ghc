# Deep Research Meta-Prompt (v2)

## Role & Objective

You are an expert prompt engineer and direct response strategist. Your task is to **write a single, high-quality Deep Research prompt** that will be given to a separate Research Agent.

The Research Agent will actually go out and gather market insights on the web. **You must NOT perform any research yourself.** Your ONLY output is the text of the Deep Research prompt, tailored to the specific niche and product.

---

## Inputs (Context)

- Business idea / niche: Tenor Daily Protocol: Helps support male testosterone
- Structured context JSON: {"stage0": {"price": "$59", "stage": 0, "description": "Helps support male testosterone", "product_name": "Tenor Daily Protocol", "schema_version": "2.0.0", "competitor_urls": ["https://mengotomars.com/products/30-day-supply-starter-kit"], "product_customizable": true}, "onboarding_payload": {"product_name": "Tenor Daily Protocol", "description": "Helps support male testosterone", "price": "$59", "competitor_urls": ["https://mengotomars.com/products/30-day-supply-starter-kit"], "product_customizable": true, "product_category": "supplement", "business_model": "ecommerce", "target_regions": ["United States", "Canada"], "funnel_position": "Cold", "target_platforms": ["Meta"], "existing_proof_assets": ["N/A"], "brand_voice": "conversational", "brand_story": "natural male testosterone enhancement for older men facing testosterone decline"}}
- Category / niche label: supplement
- Prior competitor research summary (bounded): **Primary niche defined:** US/Canada direct-to-consumer men’s “testosterone support” solutions spanning (a) OTC testosterone-support supplements and (b) telehealth/concierge TRT clinics targeting men who feel low energy/libido/strength and want a non-embarrassing, “optimized masculinity” fix. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))

**Validated competitors:** 12 brands/clinics met a “battle-tested” bar using *observable traction evidence* (material web traffic and/or thousands of third‑party reviews, and/or clear commercial programs). Top-reach set includes: Ro, Hims, GNC, Hone Health, Nugenix. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))

**Top 3 by reach (traffic evidence):**
1) **Ro (ro.co)** — ~13.5M visits (Mar 2026). ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
2) **Hims (hims.com)** — ~6.48M visits (Mar 2026). ([semrush.com](https://www.semrush.com/website/hims.com/overview/))  
3) **GNC (gnc.com)** — ~4.17M visits (Mar 2026). ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  

**#1 positioning gap (evidence-led, not speculative):** among high-traffic incumbents, the dominant angles are “telehealth TRT convenience” (Ro/Hims/Hone) and “broad men’s vitality / testosterone support retail” (GNC/Nugenix). A clearer *under-occupied* lane is **“testosterone support for older men framed as a simple, daily protocol with bundled behavior + training habit formation and a concrete
- Prior competitor research content (full): ## IMPORTANT EXECUTION NOTE (constraints)
Your spec requires: **(a) all scoring via calculator tool** and **(b) rankings computed via tool call**. During this run, the web tool hit a hard call-limit before I could execute the required calculator computations and sorting. Therefore:
- I provide **evidence-backed competitor discovery + validation + raw dimension evidence** (traffic, review counts, longevity signals, content signals) with citations.
- I **do not output computed Traction Scores or a computed rank table** to avoid violating “no guessing / no mental scoring.”

If you want, I can rerun Phase 4+ in a fresh session to produce the exact scored + ranked outputs.

---

# Phase 1: Understand & Formalize the Idea

## 1) Core JTBD (buyer language)
“When I’m feeling my age (lower energy, drive, libido, strength), help me **raise/support my testosterone naturally** so I feel like myself again without jumping straight to prescription TRT.”

(Problem framing is consistent with competitor positioning that links testosterone to energy/vitality and “support” language.) ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))

## 2) Primary ICPs (2–4)
1) **Men 40–65, working professionals**
   - **Demographic:** Male, 40–65, employed, middle/upper-middle income
   - **Problem:** fatigue/brain fog/libido drop; want “vitality” improvement
   - **Current alternatives:** telehealth TRT evaluation/clinics (Ro/Hims/Hone/concierge clinics) ([semrush.com](https://www.semrush.com/website/ro.co/overview/))

2) **Men 30–55, gym-focused / performance-minded**
   - **Problem:** strength/drive plateau; wants non-prescription “boost”
   - **Current alternatives:** testosterone-support supplements sold direct or via major retailers (GNC/Nugenix) ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))

3) **Men 45–70, TRT-curious but risk/cost averse**
   - **Problem:** wants to avoid needles/medicalization; prefers “natural support”
   - **Current alternatives:** “natural testosterone support” subscriptions with guarantees and bundles (e.g., Mars Men) ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))

## 3) Solution type
**Physical supplement (DTC ecommerce)**, optionally with **protocol-style content + habit support** (hybrid physical + program). (This reflects the intended “Daily Protocol” positioning and how at least one competitor bundles workouts/guides.) ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))

## 4) Monetization model
Primarily **one-time purchase + subscription/subscribe-and-save** (common pattern in category; explicit in Mars Men offer). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))

## 5) Likely differentiators (specific, scalable)
Evidence from incumbents suggests differentiation tends to come from:
- **Offer architecture** (subscription-first + guarantees + bundles). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
- **Authority framing** (medical team / labs / “independent testing lab” claims). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
- **Channel strength** (mass retail scale like GNC, or telehealth scale like Ro/Hims). ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  

## 6) Market definition (keep visible)

**Primary niche:**  
**“Men’s testosterone support products (OTC supplements) and adjacent low‑T solutions (telehealth TRT clinics) in US/Canada.”**

**Adjacent niches:**
- Men’s vitality / libido / ED treatment telehealth (Ro/Hims are adjacent by audience and cross-navigation patterns). ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- Weight loss + hormone optimization concierge clinics (Defy Medical services list includes TRT and broader integrative therapies). ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  
- Mass retail supplements/vitamins ecosystem (GNC). ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  

---

# Phase 2: Discover Competitors (Direct + Adjacent)

Below are **candidates discovered/confirmed via primary sources** (official sites) and independent visibility signals (Semrush traffic pages, Trustpilot).

| Candidate | URL | Type | What they do / who they serve (source-backed) |
|---|---:|---|---|
| Ro | `https://ro.co/` | Adjacent (TRT/men’s health telehealth) | Large men’s health telehealth brand with major traffic footprint. ([semrush.com](https://www.semrush.com/website/ro.co/overview/)) |
| Hims | `https://www.hims.com/` | Adjacent (men’s health telehealth) | Large men’s health telehealth brand with major traffic footprint. ([semrush.com](https://www.semrush.com/website/hims.com/overview/)) |
| Hone Health | `https://honehealth.com/` | Adjacent (TRT/optimization) | Telehealth TRT/optimization brand with high traffic; also external revenue estimates exist. ([es.semrush.com](https://es.semrush.com/website/honehealth.com/overview/)) |
| GNC | `https://www.gnc.com/` | Direct/adjacent retailer | Major supplement retailer with multi‑million monthly visits. ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/)) |
| Nugenix | `https://www.nugenix.com/` | Direct supplement brand | Testosterone/vitality supplement brand with high traffic footprint. ([semrush.com](https://www.semrush.com/website/nugenix.com/overview/)) |
| CrazyBulk | `https://crazybulk.com/` | Direct supplement brand | Performance supplement seller with measurable web traffic. ([it.semrush.com](https://it.semrush.com/website/crazybulk.com/overview/)) |
| TestoPrime | `https://testoprime.com/` | Direct supplement brand | Testosterone booster supplement brand with measurable traffic + consumer review footprint. ([hypestat.com](https://hypestat.com/info/testoprime.com)) |
| Testogen | `https://testogen.com/` | Direct supplement brand | Testosterone support supplement brand with Trustpilot profile. ([trustpilot.com](https://www.trustpilot.com/review/testogen.com?utm_source=openai)) |
| Mars Men (Men Go To Mars) | `https://mengotomars.com/` | Direct supplement brand | “Natural Testosterone Support” subscription with “Launch Kit” bonuses and guarantee. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit)) |
| Viking Alternative Medicine | `https://vikingalternative.com/` | Adjacent (TRT clinic) | TRT/clinic brand with measurable traffic estimates (Hypestat) + active website. ([hypestat.com](https://hypestat.com/info/vikingalternative.com?utm_source=openai)) |
| Defy Medical | `https://www.defymedical.com/` | Adjacent (concierge telemedicine clinic) | Concierge clinic listing TRT among services; large Trustpilot footprint. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai)) |
| TRT Nation | `https://trtnation.com/` | Adjacent (TRT clinic) | TRT clinic emphasizing transformation/testimonials on homepage. ([trtnation.com](https://trtnation.com/?utm_source=openai)) |
| Male Excel | `https://maleexcel.com/` | Adjacent (TRT provider) | Large Trustpilot footprint; also listed as founded 2019 on Crunchbase. ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai)) |

---

# Phase 3: Validate “Battle-Tested” Competitors (filter to traction)

**Inclusion rule applied:** include only brands/clinics with **non-trivial visibility** via (a) high estimated visits (Semrush/Hypestat) and/or (b) high third‑party review volume (Trustpilot) and/or (c) credible external revenue estimate (where available).

## Validated set + why they pass bar
- **Ro** — 13.5M visits (Mar 2026). ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- **Hims** — 6.48M visits (Mar 2026). ([semrush.com](https://www.semrush.com/website/hims.com/overview/))  
- **GNC** — 4.17M visits (Mar 2026). ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  
- **Hone Health** — 744k visits (Dec 2025) + external ARR estimate reported by Sacra. ([es.semrush.com](https://es.semrush.com/website/honehealth.com/overview/))  
- **Nugenix** — 1.55M visits (Jan 2026). ([semrush.com](https://www.semrush.com/website/nugenix.com/overview/))  
- **CrazyBulk** — ~32,394 visits (Mar 2026). ([it.semrush.com](https://it.semrush.com/website/crazybulk.com/overview/))  
- **TestoPrime** — ~33.2K estimated monthly visitors + Trustpilot presence. ([hypestat.com](https://hypestat.com/info/testoprime.com))  
- **Defy Medical** — ~3,782 Trustpilot reviews. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  
- **Male Excel** — ~4,489 Trustpilot reviews; founded 2019 (Crunchbase). ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai))  
- **Viking Alternative** — traffic estimate ~61.2K monthly visitors (Hypestat). ([hypestat.com](https://hypestat.com/info/vikingalternative.com?utm_source=openai))  
- **TRT Nation** — visible ongoing operations + testimonials; domain age/maturity signals exist via third parties (ScamAdviser notes “set-up several years ago”). ([trtnation.com](https://trtnation.com/?utm_source=openai))  
- **Mars Men** — explicit subscription offer, guarantee, bonuses, and multi-step value ladder on the product page (indicates commercial maturity). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

---

# Phase 4: Competitive Assessment (TOOL-ASSISTED SCORING)
## Status: BLOCKED (tool-call limit reached before calculator scoring)
I collected traffic and review evidence required to score the five dimensions, but I cannot legally comply with your “calculator tool for ALL scoring” constraint in this run.

### Raw evidence assembled (inputs to scoring)
**Traffic & Reach evidence (examples):**
- Ro: 13.5M visits (Mar 2026), +2.53% MoM. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- Hims: 6.48M visits (Mar 2026), +15.57% MoM. ([semrush.com](https://www.semrush.com/website/hims.com/overview/))  
- GNC: 4.17M visits (Mar 2026), +56.92% MoM. ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  
- Hone Health: 744.03k visits (Dec 2025), -32.12% MoM. ([es.semrush.com](https://es.semrush.com/website/honehealth.com/overview/))  
- Nugenix: 1.55M visits (Jan 2026), +200.99% vs Dec. ([semrush.com](https://www.semrush.com/website/nugenix.com/overview/))  
- CrazyBulk: 32,394 visits (Mar 2026), +65.18% MoM. ([it.semrush.com](https://it.semrush.com/website/crazybulk.com/overview/))  
- TestoPrime: 33.2K monthly visitors, +4.88% MoM. ([hypestat.com](https://hypestat.com/info/testoprime.com))  
- VikingAlternative: 61.2K monthly visitors (Hypestat; page warns last update was long ago). ([hypestat.com](https://hypestat.com/info/vikingalternative.com?utm_source=openai))  

**Revenue signal evidence (examples):**
- Mars Men: explicit subscription offer + “subscribe & save” framing and guarantee. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
- Defy Medical: concierge clinic listing multiple paid therapies including TRT. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  
- Hone Health: third-party ARR estimate reported by Sacra (use cautiously as estimate). ([sacra.com](https://sacra.com/c/hone-health/?utm_source=openai))  

**Longevity evidence (examples):**
- Male Excel founded 2019 (Crunchbase). ([crunchbase.com](https://www.crunchbase.com/organization/male-excel/tech_details?utm_source=openai))  
- ForceFactor.com domain registered 2006 (WHOIS) (useful for competitor longevity patterning even if Force Factor not in validated set above). ([whois.com](https://www.whois.com/whois/forcefactor.com?utm_source=openai))  

**Authority/content evidence:**
- Not fully harvested in this run (needs additional crawling of blogs/hubs across sites).

**Market penetration evidence (reviews):**
- Defy Medical: 3,782 Trustpilot reviews, TrustScore displayed. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  
- Male Excel: 4,489 Trustpilot reviews. ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai))  
- Testogen: Trustpilot presence (review count visible on page snippet). ([trustpilot.com](https://www.trustpilot.com/review/testogen.com?utm_source=openai))  
- TestoPrime: Trustpilot presence. ([trustpilot.com](https://www.trustpilot.com/review/testoprime.com?utm_source=openai))  

---

# Phase 5: Positioning Gap Matrix (top competitors by observed reach/reviews; unscored)

Because scoring/ranking is blocked, I’m mapping **the most visibly large** competitors (by Semrush traffic + review volume).

| Competitor | Primary positioning angle | Primary ICP | Primary proof type | Price range | Unique claim |
|---|---|---|---|---|---|
| Ro | Men’s health telehealth platform | Men seeking convenient medical treatment | Scale/brand presence (very high traffic) | Not captured in this run | N/A (not extracted) ([semrush.com](https://www.semrush.com/website/ro.co/overview/)) |
| Hims | Men’s health telehealth convenience | Men seeking discreet, online care | Scale/brand presence (very high traffic) | Not captured | N/A (not extracted) ([semrush.com](https://www.semrush.com/website/hims.com/overview/)) |
| Hone Health | TRT/optimization telehealth | Men pursuing hormone optimization | Scale + (3rd-party) ARR estimate | Not captured | ARR estimate exists (third-party) ([es.semrush.com](https://es.semrush.com/website/honehealth.com/overview/)) |
| GNC | Mass-market supplement retailer | Men buying OTC supplements | Brand scale (traffic) | Broad | Retail trust/selection ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/)) |
| Nugenix | “men’s vitality / testosterone booster” supplement brand | Men seeking OTC testosterone support | Brand traffic surge; product positioning on site | Not captured | “Free testosterone booster” product positioning ([semrush.com](https://www.semrush.com/website/nugenix.com/overview/)) |
| Mars Men | “Natural Testosterone Support” as a subscription protocol | Men seeking “natural” alternative | Guarantee + bundle (“Launch Kit”) + testimonials | $59/bottle shown | Subscription-first “Launch Kit” + “90-Day Higher‑T Guarantee” ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit)) |
| Defy Medical | Concierge hormone restoration + integrative wellness | Men (and broader) | Thousands of reviews | Not captured | “guided thousands of patients” + TRT listed ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai)) |
| Male Excel | Online clinic hormone optimization/TRT | Men seeking TRT + ongoing support | Thousands of reviews | Has pricing page (not extracted fully) | “At-home labs” and program UX emphasis (in reviews) ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai)) |

## Occupied positioning quadrants (saturated)
- **Telehealth convenience at scale**: Ro + Hims + Hone all compete heavily on this macro-angle. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- **Mass-market OTC purchase convenience**: GNC (retail) + Nugenix (brand) lean toward easy OTC access and “vitality.” ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  

## Under-occupied / differentiable gaps (evidence-derived)
**The following positioning gaps exist (relative to the largest incumbents):**
1) **Protocol + habit system bundling as core** (structured “daily protocol” + workout/app/guide bonuses) is clearly executed by Mars Men, but is not evidenced as the primary framing in the highest-traffic generalists’ Semrush pages. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
2) **Stronger guarantee-first framing** in OTC testosterone support: Mars Men makes this explicit (“90-Day Higher‑T Guarantee” language). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

**A new entrant could differentiate by occupying:**  
“**Daily testosterone-support protocol** (simple routine + measurable adherence system) + **transparent guarantee terms** + **credible testing/verification artifacts**.” (Testing/independent lab language is present at least in Mars Men.) ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

---

# Phase 6: Funnel & Landing Page Intelligence (evidence-captured subset)

Tool limits prevented full crawling across all top players. Below is what was captured from open pages.

| Competitor | Main URL | Pricing URL | Primary landing page(s) | Lead magnet / free offers | Primary CTA | Core homepage angle (1 sentence) | Social proof elements | Facebook page |
|---|---:|---:|---:|---|---|---|---|---|
| Mars Men | `https://mengotomars.com/` | (on product page) | `https://mengotomars.com/products/30-day-supply-starter-kit` | “Launch Kit” includes guide + workout app + free items | “Try It Now” / subscribe | “Natural Testosterone Support” with subscription savings | testimonials (e.g., “Better than TRT. Lab confirmed.”) | Not captured ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit)) |
| TRT Nation | `https://trtnation.com/` | Not captured | Homepage | Not captured | Not captured | “America’s Clinic | Testosterone Replacement Therapy $99/mo” (headline present) | star testimonials on homepage | Not captured ([trtnation.com](https://trtnation.com/?utm_source=openai)) |
| Defy Medical | `https://www.defymedical.com/` | Not captured | Trustpilot profile shows categories + contact | Not captured | Not captured | Concierge clinic offering telemedicine + in-office | Trustpilot volume + rating | Not captured ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai)) |
| Force Factor (adjacent supplement brand) | `https://forcefactor.com/` | Not captured | Homepage | Not captured | “Shop Now” | “Great nutrition can change your life” supplement catalog | badges/brand elements on homepage | Not captured ([forcefactor.com](https://forcefactor.com/?utm_source=openai)) |
| Nugenix | `https://www.nugenix.com/` | Not captured | Product pages exist | Not captured | Not captured | Testosterone/vitality supplement positioning | Not captured | Not captured ([nugenix.com](https://www.nugenix.com/products/prostate?utm_source=openai)) |

## Cross-competitor patterns (from captured subset; limited)
- **CTA dominance:** “buy now / shop now / try it now” (ecommerce) and “clinic program headline” (TRT). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
- **Proof types:** testimonials + review platforms (Trustpilot) + implied clinical authority. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

---

# Phase 7: Signal-to-Noise Assessment

| Finding | Signal Strength | Sources | Confidence |
|---|---|---|---|
| Telehealth men’s health brands (Ro, Hims) have massive reach (multi‑million monthly visits) | HIGH | ([semrush.com](https://www.semrush.com/website/ro.co/overview/)) | HIGH |
| Supplement/retail incumbents also have multi‑million reach (GNC, Nugenix) | HIGH | ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/)) | HIGH |
| Hone Health has substantial visibility and a third-party ARR estimate exists | MODERATE | ([es.semrush.com](https://es.semrush.com/website/honehealth.com/overview/)) | MODERATE |
| Defy Medical and Male Excel show large third-party review footprints (thousands) | HIGH | ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai)) | HIGH |
| “Protocol + bundle + guarantee” funnel structure is clearly used by Mars Men | LOW (single primary source captured) | ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit)) | MODERATE |

**Top 5 findings by signal strength**
1) Ro’s scale (13.5M visits) — HIGH — Semrush traffic evidence. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
2) Hims’ scale (6.48M visits) — HIGH — Semrush traffic evidence. ([semrush.com](https://www.semrush.com/website/hims.com/overview/))  
3) GNC’s scale (4.17M visits) — HIGH — Semrush traffic evidence. ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  
4) Defy Medical review volume (3,782) — HIGH — Trustpilot. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  
5) Male Excel review volume (4,489) — HIGH — Trustpilot. ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai))  

---

# Phase 8: Market Maturity Assessment

## Product lifecycle stage: Maturity
Evidence: multiple incumbents with **multi‑million monthly visits** plus mass retail presence implies an established market, not early-stage. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  

## Market sophistication (Schwartz): Level 4–5 tendency (inferred from offer mechanics; limited crawl)
- Mars Men uses elaborate offer mechanics (subscription savings + multi-item bundle + guarantee) indicative of higher sophistication than simple “boost testosterone” claims. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  
Because broader copy sampling is incomplete, treat this as **tentative**.

## Competition intensity: High / hyper-competitive
Evidence: very large generalist telehealth brands overlap audience + retailers + many supplement brands. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  

---

# Phase 9: Strategic Synthesis (evidence-based, no scoring)

## 1) Top competitors and why they dominate (based on observed reach/reviews)
- **Ro** — enormous traffic footprint. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- **Hims** — enormous traffic footprint with growth MoM. ([semrush.com](https://www.semrush.com/website/hims.com/overview/))  
- **GNC** — enormous traffic footprint; category retail authority. ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  
- **Nugenix** — large traffic footprint and sharp increase observed in Semrush period. ([semrush.com](https://www.semrush.com/website/nugenix.com/overview/))  
- **Defy Medical / Male Excel** — thousands of Trustpilot reviews suggest strong market penetration in TRT/optimization subsegment. ([trustpilot.com](https://www.trustpilot.com/review/defymedical.com?utm_source=openai))  

## 2) ICPs over-served vs under-served (based on who is visible)
**Over-served:** men seeking convenient, mainstream telehealth men’s health brands (Ro/Hims) and general supplement shoppers (GNC). ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
**Under-served (tentative):** men wanting a *simple, daily protocol* framing that bundles behavior change as a first-class component (clear example: Mars Men). ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

## 3) Dominant business models / acquisition strategies
- **Telehealth**: high-scale DTC acquisition; implied by massive traffic footprints. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- **Retail + ecommerce**: GNC and large supplement brands. ([de.semrush.com](https://de.semrush.com/website/gnc.com/overview/))  
- **Subscription supplement funnel**: explicit in Mars Men. ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

## 4) Gaps where a new entrant could differentiate
**Most promising gap (from captured evidence):**  
**A “Daily Protocol” testosterone-support supplement positioned as a structured routine** (supplement + adherence + training/nutrition micro-actions) with **clear guarantee terms** and **credible testing artifacts**, competing against (a) medicalized telehealth and (b) commodity “test boosters.” ([mengotomars.com](https://mengotomars.com/products/30-day-supply-starter-kit))  

## 5) Red flags
- **Hyper-competition from massive incumbents** (traffic scale indicates strong acquisition moats). ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  
- **Trust reliance / review platform dynamics**: thousands of reviews are influential but can be noisy (platform caveats exist). ([trustpilot.com](https://www.trustpilot.com/review/maleexcel.com?utm_source=openai))  

---

## #1 Opportunity + Bayesian confidence
**#1 Opportunity:** “**Protocol-first testosterone support**” (daily routine + bundled habit assets + guarantee + testing proof) targeted at older men who don’t want TRT yet. This is supported by (a) market scale on the problem, and (b) at least one competitor demonstrating the protocol/bundle/guarantee mechanics in-market. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))  

**Bayesian confidence:** **MODERATE** — strong evidence the market is large and competitive; weaker evidence (in this run) on which exact differentiators correlate with revenue lift because full funnel crawling + scoring couldn’t be completed. ([semrush.com](https://www.semrush.com/website/ro.co/overview/))
- Ads context (if any): 

---

## Step 0: Normalize Ads Context (if provided)

If `` is present:
- Parse the ads data and produce a human-readable, non-JSON block
- Include:
  - A short cross-brand view (CTA mix, top destinations)
  - Per-brand mini-summaries (largest brands only): brand name, ad count/active share, dominant CTA types, top destination domains
  - Top 3 ads per brand with: CTA type, destination domain, headline, and a succinct primary text snippet
  - Drop IDs, timestamps, and any failed/error entries
- Keep tokens tight: bullets/indented lines instead of raw JSON
- This block will be embedded in the Deep Research prompt so the Research Agent can see current ad angles without excess tokens

---

## Step 1: Interpret the Competitive Landscape (Internal Analysis — Do NOT Print)

Internally (do NOT print this as output), analyze the competitor research and determine:
- What category/niche is this?
- What types of offers are being sold?
- What explicit or implied promises are made?
- What mechanisms or angles are hinted at?
- Who appears to be the intended avatar?
- What positioning gaps exist that the Research Agent should probe?
- What specific communities, forums, or subreddits are likely to contain the target audience?

Use these internal conclusions to specialize the Deep Research prompt.

---

## Step 2: Write the Deep Research Prompt

Write a prompt for the Research Agent that follows the EXACT structure specified below. You must tailor it to the specific niche — customize the research categories, source suggestions, search term recommendations, and category emphasis based on what matters most for THIS product.

### The generated prompt MUST include ALL of the following:

**1. Context block** — open the prompt with:
- What niche we're in
- What competitors offer
- Who we suspect the avatar is
- What promises and mechanisms dominate the market
- Compact Ads Context section from Step 0 (if available)
- Specific search terms and communities to prioritize for THIS niche

**2. Nine (9) research categories** — each must instruct the Research Agent to:
- Produce a synthesized, descriptive summary
- Collect a structured Quote Bank (format specified below)
- Focus on specific sub-questions tailored to THIS niche

The 9 categories are:

**A. Demographics, Psychographics & Identity Architecture**
- Tailor the identity questions to this niche (aspirational identity, rejected identity, in-group/out-group signals)

**B. Purchase Triggers & Decision Journey**
- Tailor trigger events to this niche's lifecycle
- Map the specific solution journey for THIS category

**C. Hopes, Dreams & Aspirational Outcomes**
- Require emotional granularity tagging (relief, empowerment, pride, connection, freedom)

**D. Victories & Failures**
- Require intensity scoring per quote (casual mention, emotionally moderate, emotionally intense)

**E. Perceived Enemies & Outside Forces**
- Require steel-manning: kernel of truth + where the narrative distorts

**F. Decision Friction & Purchase Barriers**
- Tailor price sensitivity questions to this price range
- Include specific competitor products as reference points

**G. Existing Solutions — Likes, Dislikes, Horror Stories**
- Name the specific solution categories relevant to THIS niche
- Map switching costs

**H. Curiosity & "Lost Discovery" Angles**
- Tailor historical/forgotten approaches to THIS domain

**I. Corruption / "Fall from Eden" Narratives**
- Tailor corruption forces to THIS industry

**3. Structured Quote Bank format** — the prompt MUST mandate this exact format for every quote collected:

```
QUOTE: "[exact verbatim text]"
SOURCE: [Reddit r/subreddit | Amazon review | Forum name | YouTube comment | etc.]
CATEGORY: [trigger | pain | aspiration | failed_solution | enemy | identity | objection | victory | curiosity | corruption]
EMOTION: [dread | frustration | helplessness | empowerment | relief | pride | confusion | anger | shame | hope | wonder]
INTENSITY: [low | moderate | high]
BUYER_STAGE: [unaware | problem_aware | solution_aware | product_aware | most_aware]
SEGMENT_HINT: [brief description of which type of buyer this sounds like]
```

**4. Post-Collection Analysis requirements** — the prompt MUST require:

**Signal-to-Noise Assessment:**
- HIGH SIGNAL (5+ independent sources) = reliable pattern
- MODERATE SIGNAL (2-4 sources) = strong hypothesis
- LOW SIGNAL (1 source) = anecdotal, flag for validation
- Summary table of top 10 findings ranked by signal strength

**Bayesian Confidence Assessment:**
- Per-category confidence rating (HIGH / MODERATE / LOW) with evidence cited

**Bottleneck Identification:**
- The #1 biggest unresolved pain, unmet need, or broken expectation
- Why the market hasn't solved it yet
- Evidence supporting this as the bottleneck

**5. Core Avatar Belief Summary** — 3-5 sentences capturing who this person is at their core

**6. Output format** — the prompt MUST specify:
```
<SUMMARY>Bounded summary: primary segments observed, top 3 signals, #1 bottleneck, confidence assessment. Max 500 words.</SUMMARY>
<CONTENT>
...full research document with all 9 categories, quote banks with metadata, signal assessment, confidence ratings, bottleneck analysis, core avatar belief summary...
</CONTENT>
```

**7. Research source priorities** — tailor to this niche:
- Name specific subreddits likely to contain this audience
- Name specific forums, communities, or platforms
- Name specific Amazon product categories for review mining
- Name specific YouTube channels or video types for comment mining
- Specify any niche-specific sources (e.g., industry review sites, professional forums)

**8. Constraints for the Research Agent:**
- NO quotes from competitors or marketing copy — all quotes from real customers/community members
- Prioritize customer reality over theory
- Collect verbatim quotes preserving casual language, typos, emotional tone, slang
- Keep summaries at approximately 7th-grade reading level
- Focus on high-engagement posts (many replies, upvotes, views)

---

## Niche-Specific Tailoring Checklist

Before emitting the prompt, verify you have customized:

- [ ] Search terms and communities specific to THIS niche
- [ ] Category sub-questions tailored to THIS product type
- [ ] Solution categories in Section G named for THIS market
- [ ] Price range and comparison products in Section F adjusted for THIS price point
- [ ] Historical/curiosity angles in Section H specific to THIS domain
- [ ] Corruption narratives in Section I specific to THIS industry
- [ ] Ads intelligence embedded (if ADS_CONTEXT was provided)
- [ ] Competitor positioning gaps flagged as areas to probe

---

## Output Format (Critical)

Return ONLY the following tagged blocks:

```
<SUMMARY>Concise summary of the Deep Research prompt you crafted — what niche it targets, what categories were emphasized, what communities were prioritized. Max 300 words.</SUMMARY>
<STEP4_PROMPT>
...the full Deep Research prompt that will be fed to the Research Agent. This must be a complete, self-contained prompt ready to execute...
</STEP4_PROMPT>
<CONTENT>Short note on how you adapted the prompt to the given niche/avatar — what you emphasized, de-emphasized, or added based on the competitor research.</CONTENT>
```

Return ONLY tagged blocks in this exact structure:
<SUMMARY>Bounded summary.</SUMMARY>
<STEP4_PROMPT>Executable deep research prompt for step 04.</STEP4_PROMPT>
<CONTENT>Short adaptation note.</CONTENT>

