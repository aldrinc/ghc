# Whole Campaign Paid Ads QA False-Positive Analysis

## Decision

The validator is catching real Meta-policy risks on the six known rejected groups, but it also has confirmed landing-page false positives caused by the snapshot source. The full 83-group LLM pass could not complete because the configured OpenAI account hit `insufficient_quota`; no alternate model or fallback was used.

## Campaign Scope

- Campaign ID: `426afe15-ac66-436c-910d-2a1259597bf3`
- Generation key: `batch:tenor-glp-quiz-problem-aware-expansion-20260506`
- Current-generation prepared creative specs: `83` logical representatives
- Destination split: `43` GLP, `40` quiz
- Source split: `60` standard curated, `23` Tenor package
- Raster variants represented: `249` images, but this audit uses one representative per logical group because variants are aspect-ratio siblings

## Full Campaign LLM Run Status

I attempted the remaining `77` non-known groups in four parallel chunks after excluding the six already validated rejected groups. All chunks failed before returning findings:

- Chunk 0: `RateLimitError`, OpenAI `insufficient_quota`, after `349.8s`
- Chunk 1: `APITimeoutError`, after `345.0s`
- Chunk 2: `RateLimitError`, OpenAI `insufficient_quota`, after `365.6s`
- Chunk 3: `RateLimitError`, OpenAI `insufficient_quota`, after `348.3s`

I also checked MOS metadata for cached LLM policy reviews on the `83` representatives. Result: `0` cached reviews. So there is no complete whole-campaign LLM result to classify yet.

## Confirmed False Positives

### `META-LP-005` and `META-LP-006` on live ShopTenor destinations

Classification: **false positive**

Reason: live HTTP inspection of both destinations found footer privacy/contact/support content, but production QA did not inspect the live HTML. It routed the external-looking ShopTenor URLs through the MOS public funnel API parser.

Live-page check:

- GLP URL `https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/`: `privacy=True`, `contact=True`, `support=True`, HTTP `200`, body length `577785`.
- Quiz URL `https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/`: `privacy=True`, `contact=True`, `support=True`, HTTP `200`, body length `493502`.

Production validator snapshot check:

- GLP inspection source: `public_funnel_api`, body length `0`, privacy/contact false.
- Quiz inspection source: `public_funnel_api`, body length `59231`, privacy/contact false, placeholder true.

Root cause: `_landing_page_snapshot()` treats any URL with at least three path segments as a MOS public funnel route, even when the host is the external storefront domain. For this campaign, `shoptenorco.com/8b89a76d/daily-drive-essentials/...` gets parsed as a MOS public funnel route and bypasses the live page fetch.

Expected fix: only use `_load_public_funnel_snapshot()` when the host matches MOS public funnel hosting, or when the campaign delivery mode says the destination is MOS-managed. External storefront URLs should be fetched directly.

### `META-LP-007` quiz placeholder mismatch

Classification: **likely false positive for Meta review of the live ad**, caused by the same snapshot-source bug.

Reason: the LLM saw public-funnel API text containing `Presales Placeholder` and `Final copy and creative can be added later`; live HTTP inspection of the ShopTenor quiz URL did not find those strings. If Meta is reviewing the live `shoptenorco.com` URL, the internal placeholder finding is not describing the reviewed page.

## Needs Review / Not Clearly False Positive

### `META-ACCOUNT-008` Data Set integration incomplete

Classification: **needs review, not a confirmed false positive**

Evidence from production profile:

- MOS tracking status: `active`
- Mode: `public_funnel_runtime`
- Channel: `meta`
- Pixel: `4578413032424797`
- Browser events present: `Entered Funnel`, `PageView`, `ViewContent`, `PreSalesToSalesClick`, `AddToCart`, `Purchase`
- Readiness helper requires: `PageView` and `SalesToCheckoutClick`

Interpretation: this may be a real operational gap if `SalesToCheckoutClick` is required for this funnel. It may be an overly strict rule if `AddToCart`/`Purchase` are sufficient for this external-URL campaign. The current finding evidence is incomplete because it reports status/mode/pixel but not the missing event requirement.

## Confirmed True Positives From The Six Meta-Rejected Groups

### `curated-13-glp`

- Row: `CURATED-13-GLP`
- Headline: What GLP-1 Does to Your Drive
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Likely true positives:
  - `META-UBP-001` `blocker`: Hidden-cause and sensational medical framing
    - The copy presents a sensational causal explanation for GLP-1 use ('rapid weight loss floods your system with cortisol') and frames the product as revealing a secret problem your doctor 'didn't mention.' That combination reads as misleading hidden-cause and bait-style health framing rather than neutral product promotion.
  - `META-COPY-005` `high`: Negative self-perception / distress framing
    - The ad uses deficit and deterioration language to make the audience feel worse about weight loss and energy changes, including 'foggier, flatter,' 'running on fumes,' and 'your presence fades.' This exploits negative self-perception to push the supplement.
  - `META-COPY-006` `high`: Direct personal health-attribute implication
    - The copy speaks as if the viewer has a GLP-1 prescription and a related doctor-patient context, which implies a personal medical attribute. This moves beyond general audience language and into protected health-attribute targeting.
  - `META-IMAGE-001` `blocker`: Creative reinforces testimonial-style health bait
    - The image amplifies the same risky angle with a testimonial-like headline, a personal 'I' statement about losing weight and crashing energy, and a 'CLICK TO REVEAL' CTA. Visually, it reinforces deceptive health framing and clickbait rather than a straightforward product presentation.
- Likely false positives from snapshot-source issue:
  - `META-LP-005` `high`: Privacy policy marker not found on destination
  - `META-LP-006` `medium`: Contact or support marker not found on destination

### `curated-16-glp`

- Row: `CURATED-16-GLP`
- Headline: What GLP-1 Does to Your Drive
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Likely true positives:
  - `META-COPY-006` `high`: Viewer-specific GLP-1 health implication
    - The copy talks to the reader as if they personally take GLP-1 medication and are experiencing medical/body effects. Phrases like your prescribing doctor didn't mention, your mornings get heavier, and your afternoons disappear imply knowledge of the viewer's private health status.
  - `META-UBP-001` `blocker`: Sensational hidden-cause and fake-authority framing
    - The ad uses a hidden-cause narrative and authority cues to pressure a purchase: rapid weight loss allegedly floods the system with cortisol, a doctor supposedly omitted this risk, and the product is positioned as the fix. The survey claim and results you can feel language add promotional certainty without enough substantiation.
  - `META-IMAGE-001` `blocker`: Image mimics a news/report article
    - The creative visually reinforces the same risk: it looks like a men's health report with a portrait, a headline starting with Doctors:, and a Read this 3-min article callout. That styling suggests editorial or scientific authority rather than a straightforward ad.
- Likely false positives from snapshot-source issue:
  - `META-LP-005` `high`: Privacy policy marker not found on destination
  - `META-LP-006` `medium`: Contact or support marker not found on destination

### `curated-17-glp`

- Row: `CURATED-17-GLP`
- Headline: Keep Your Drive Steady on GLP-1s
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Likely true positives:
  - `META-UBP-001` `blocker`: Sensational GLP-1 health-risk framing
    - The copy uses an exaggerated, causally certain claim that GLP-1s make 'your body start burning muscle for fuel — not fat,' then positions the supplement as the answer. That health-outcome framing is sensational and can mislead viewers about the actual cause, effect, and benefits.
  - `META-IMAGE-001` `blocker`: Medical authority creative cue
    - The image visually reinforces a pseudo-clinical message by showing a doctor in a lab coat and stethoscope beside medical scans, paired with 'READ THE PROTOCOL' and 'GLP-1 USERS' copy. That combination can imply medical or scientific authority without clear substantiation.
- Likely false positives from snapshot-source issue:
  - `META-LP-005` `high`: Privacy policy marker not found on destination
  - `META-LP-006` `medium`: Contact or support marker not found on destination

### `curated-02-quiz`

- Row: `CURATED-02-QUIZ`
- Headline: 52% Off Limited-Time Welcome Offer
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Likely true positives:
  - `META-COPY-006` `high`: Direct age/health callout to the viewer
    - The ad copy strongly implies the viewer has specific age and body-state attributes, e.g. "If you're over 40" and "you're STILL crashing by 3 p.m. and gaining weight." That is a personal-attribute-style callout tied to health/body and age.
  - `META-UBP-001` `blocker`: Sensational hidden-cause framing
    - The copy uses a hidden-cause narrative and pressure framing: "Here's why," "It's not willpower. It's your systems," and "The pathways behind energy, drive, and stamina start declining around 30." It also contrasts supplements with clinics/prescriptions/needles in a scare-style way.
  - `META-IMAGE-001` `blocker`: Creative reinforces age/body-targeted callout
    - The image headline says "A NEW QUIZ IS HELPING MEN RECLAIM THEIR DRIVE AFTER 40" and "A guided path for men who feel their energy and stamina have changed." Combined with the close-up male portrait and selfie inset, the creative visually reinforces age/body-state targeting.

### `curated-17-quiz`

- Row: `CURATED-17-QUIZ`
- Headline: Stop Losing Drive. Start Today.
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Likely true positives:
  - `META-COPY-006` `high`: Direct viewer health-attribute claims
    - The ad copy repeatedly addresses the viewer as if they currently have low energy, brain fog, gut changes, and reduced stamina. That implies knowledge of the user's own health/body state rather than speaking generally about the product category.
  - `META-UBP-001` `blocker`: Hidden-cause and pseudo-medical framing
    - The copy presents a hidden internal cause for the user's experience and uses quasi-medical language to pressure action. Phrases like 'three systems keep declining together' and 'That's a system problem' read like a diagnosis narrative rather than a straightforward product ad.
  - `META-IMAGE-001` `blocker`: Doctor imagery implies medical authority and diagnosis
    - The image uses a lab-coat doctor, stethoscope, and anatomy-scan backdrop to create medical authority, and the on-image text says the quiz can 'identify the cause.' That visually reinforces a diagnostic claim tied to the viewer's own health state.

### `curated-24-quiz`

- Row: `CURATED-24-QUIZ`
- Headline: 52% Off Limited-Time Welcome Offer
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Likely true positives:
  - `META-COPY-006` `high`: Direct personal body/health targeting
    - The copy speaks as if it knows the viewer has a specific body and energy state ('Noticed your midsection holding on,' 'you feel drained by 3 p.m.,' 'your drive isn't what it used to be'), and it adds an age-based claim ('research shows starts around 30'). That is direct personal-attribute targeting rather than general product language.
  - `META-COPY-005` `high`: Negative self-perception / body-shaming hook
    - The opening uses insecurity-based body language ('midsection holding on,' 'soft tissue where definition used to be') and frames the product as a fix for a diminished physique/drive. That leans into negative self-perception, which is restricted in health and wellness ads.
  - `META-UBP-001` `blocker`: Hidden-cause and fake-science framing
    - The ad uses a hidden-cause narrative ('visible sign of what's shifting inside,' 'systems behind your drive start declining,' 'research shows starts around 30') and authority-style support ('Dr. Adam Reese,' survey stats) to explain the problem and sell the solution. That combination can be misleading or sensational if not fully substantiated.
  - `META-IMAGE-001` `blocker`: Image reinforces authority and hidden-reason risk
    - The image overlays a portrait with 'Specialist: Men Losing Their Energy and Drive Share One Overlooked Reason' and 'Take the 2-min quiz.' That creates a specialist/authority implication, a hidden-reason promise, and a direct callout to men with energy/drive issues, which visually reinforces policy risk.
- Likely false positives from snapshot-source issue:
  - `META-LP-007` `blocker`: Landing page does not substantiate the quiz promise

## Whole-Campaign Risk Patterns To Validate After Credits Are Restored

These are not final LLM findings for the whole campaign; they are high-priority hypotheses based on the repeated copy/source structure and the confirmed six-group results:

- Curated GLP groups reuse `COPY001`, `COPY002`, and `COPY003`; if the same copy is attached, copy-level personal attribute and UBP risks may repeat across many curated GLP groups.
- Curated quiz groups reuse `COPY011` through `COPY018`; `COPY011`, `COPY012`, and `COPY018` already appear in confirmed rejected groups and likely need broad review.
- Tenor package groups may have fewer image false positives because they are source-specific, but their copy can still trigger the same personal-attribute or UBP issues if it reuses the same copy units.
- Any future LP findings on these live external URLs should be interpreted cautiously until the snapshot routing bug is fixed.

## Recommended System Fixes

1. Fix landing-page snapshot routing for external storefront URLs before trusting LP policy results.
2. Add complete evidence to `META-ACCOUNT-008`, including required events, present events, and missing events.
3. Change campaign QA orchestration to checkpoint per logical group, so quota or timeout failures preserve completed LLM findings.
4. Collapse aspect-ratio siblings before publish-gate QA, so one logical ad group is reviewed once unless variant content differs materially.
5. After OpenAI quota is restored, rerun the remaining 77 representatives using the checkpointed runner and classify all findings into true positive, likely false positive, and needs review.