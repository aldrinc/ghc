# Tenor GLP + Quiz Meta Compliance Audit

Date: 2026-05-08

## Decision

The likely root cause is the combined ad experience, not one isolated copy string. The rejected ads pair medical/news/researcher-style imagery with direct health, weight-loss, testosterone, cortisol, muscle-loss, and personal-attribute claims. That pattern maps most directly to Meta's Unacceptable Business Practices policy for deceptive or exaggerated health-related benefit claims, with secondary exposure under Health and Wellness and Personal Attributes.

Meta API pull:

- Meta campaign: `120245546805940293`
- Total ad objects returned: `149`
- Active configured ads: `83`
- Disapproved ads: `6`
- Duplicate ad objects with rejected-review issues: `3`
- All disapproved ads: `Unacceptable Business Practices`

Artifacts:

- `meta-api-ads-review-pull-2026-05-08-deep.json`
- `rejected-image-contact-sheet.jpg`
- `image-ocr.json`
- `landing-page-crawl.json`
- `glp-lander-top.png`
- `quiz-lander-top.png`
- `sales-page-top.png`

## Policy Basis

Meta's UBP page prohibits ads that use identified deceptive or misleading practices and specifically calls out deceptive or exaggerated success and health-benefit claims. It also says these patterns are often seen in health or weight-loss schemes.

Related Meta policies:

- UBP: `https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/`
- Health and Wellness: `https://transparency.meta.com/policies/ad-standards/restricted-goods-services/health-wellness/`
- Personal Attributes: `https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/`
- General review scope: `https://transparency.meta.com/policies/ad-standards/`

The important operational point is that Meta reviews the ad components and destination together: text, image, targeting, and landing page. Our system treated these as mostly separate checks.

## Campaign-Level Findings

| Area | Finding | Severity |
| --- | --- | --- |
| Meta review result | 6 disapproved, all UBP; 3 duplicate `WITH_ISSUES` ads trace back to those rejections | High |
| Targeting | Rejected ad sets are US-only and 18-65, so age targeting appears compliant for health/weight-loss ads | Pass |
| Imagery | Rejected creatives use doctors, researchers, MRI/brain-scan visuals, news/report labels, and authority framing | High |
| Copy | Copy uses direct second-person health/body claims, hidden-medical-info framing, and strong supplement mechanisms | High |
| GLP lander | Headline and hero include "secretly crashing your testosterone", "$1.17 natural fix", before/after body image, and cortisol/muscle-for-fuel claims | Critical |
| Quiz lander | Quiz asks age and frames result around "what's really happening with your testosterone"; footer links point to `mengotomars.com`, not `shoptenorco.com` | Medium |
| Sales page | Offer congruence is mostly aligned, but sales copy uses "Testosterone Restoration Blend", "restores... testosterone naturally", and medical replacement language | High |
| Internal QA | Copy QA caught 2 of 6 rejected ads; it did not inspect images/OCR or classify UBP-style health exaggeration | Critical |

## Rejected Ad Review

### `curated-13-glp`

- Meta ad id: `120245565635240293`
- Destination: GLP listicle
- Source image: `old_school.jpg`
- Copy: `COPY001`, "What GLP-1 Does to Your Drive"
- Internal copy QA: no finding
- Meta result: UBP disapproved

Creative risk:

- Pre-grouped generated image says "The GLP-1 Side Effect Nobody Warned Me About".
- Testimonial text says the shots worked for the waistline but left the person flat, foggy, and drained.
- CTA says "Click to reveal".

Copy risk:

- "what your prescribing doctor didn't mention"
- "rapid weight loss floods your system with cortisol"
- "your body burns lean tissue for fuel"
- "foggier, flatter, and running on fumes"
- survey proof claims using `1,203`, `94%`, and `87%`

Policy trace:

- UBP: health-related benefit and mechanism claims are presented as a hidden medical problem and product-backed solution.
- Health and Wellness: negative body/health self-perception around GLP weight loss and energy/drive.
- Personal Attributes: second-person claims imply the viewer may be on GLP-1s and experiencing health/body changes.

Likely reason it passed our QA:

- The current regex missed this copy because it focused on explicit shame phrases, not hidden-medical-info framing or broad health mechanism exaggeration.
- Image OCR was not part of the publish gate.

### `curated-16-glp`

- Meta ad id: `120245548456240293`
- Destination: GLP listicle
- Source image: `_initial_swipe_contact_sheet.jpg`
- Copy: `COPY001`, "What GLP-1 Does to Your Drive"
- Internal copy QA: no finding
- Meta result: UBP disapproved

Creative risk:

- Pre-grouped generated image presents a doctor-style frame: "MEN'S HEALTH REPORT".
- Headline says "Doctor: Men On GLP-1s Are Losing Weight, But Quietly Draining Their Drive".
- This creates medical authority/news-report posture before the user reaches the page.

Copy risk:

- Same `COPY001` risks as `curated-13-glp`.

Policy trace:

- UBP: the ad uses a medical authority/report visual style alongside health claims.
- Personal Attributes: implies the viewer may be on GLP-1s and losing drive.
- Health and Wellness: weight-loss and health product claims use negative personal impact.

System issue:

- `_initial_swipe_contact_sheet.jpg` should never have been eligible as a curated source. It is an aggregate review artifact, not a clean swipe concept.

### `curated-17-glp`

- Meta ad id: `120245565625290293`
- Duplicate issue ad: `120245548568280293`
- Destination: GLP listicle
- Source image: `researchers.jpg`
- Copy: `COPY002`, "Keep Your Drive Steady on GLP-1s"
- Internal copy QA: `META-COPY-005`
- Meta result: UBP disapproved

Creative risk:

- Final available 9:16 image uses brain-scan/doctor imagery.
- OCR: "Rapid weight loss can quietly drain your drive, energy, and lean muscle if you miss this critical step."
- Pre-grouped image says "Researchers: Why men on GLP-1s are losing their drive along with the weight - and how to get it back."

Copy risk:

- "GLP-1s cut appetite so hard your body starts burning muscle for fuel"
- "supports muscle preservation, steady metabolism, and healthy hormone pathways"
- "No needles. No prescription. No shutdown."

Policy trace:

- UBP: strong health-benefit and weight-loss mechanism claims.
- Health and Wellness: negative body/health impact tied to weight loss.
- Personal Attributes: implies the viewer is on GLP-1s or at risk of losing muscle/drive.

System issue:

- Our QA did flag negative self-perception, but that finding was not a hard pre-publish gate.
- The more serious UBP/health-exaggeration pattern was not classified.

### `curated-02-quiz`

- Meta ad id: `120245547655270293`
- Destination: quiz
- Source image: `7.png`
- Copy: `COPY012`, "52% Off Limited-Time Welcome Offer"
- Internal copy QA: no finding
- Meta result: UBP disapproved

Creative risk:

- Pre-grouped image says "Science just found a way to restore men's drive after 40".
- It includes a face-in-circle talking-head style that resembles a news/interview frame.
- CTA says "Take the guided quiz to find out why your energy and focus have changed."

Copy risk:

- "You're STILL crashing by 3 p.m. and gaining weight"
- "If you're over 40"
- "The pathways behind energy, drive, and stamina start declining around 30"
- "What happened?"
- survey proof claims around `94%`, `81%`, `87%`, and `92%`

Policy trace:

- UBP: science/restoration framing plus broad health-benefit claims can read as exaggerated.
- Personal Attributes: age, energy, weight, and body status are framed in second person.
- Health and Wellness: negative self-perception around weight gain and performance decline.

System issue:

- Current QA missed this because it did not treat second-person age/body/energy claims as personal-attribute risk.

### `curated-17-quiz`

- Meta ad id: `120245565425580293`
- Duplicate issue ad: `120245547824270293`
- Destination: quiz
- Source image: `researchers.jpg`
- Copy: `COPY011`, "Stop Losing Drive. Start Today."
- Internal copy QA: no finding
- Meta result: UBP disapproved

Creative risk:

- Pre-grouped image uses researcher/brain-scan visual language.
- OCR says "science-backed protocol" and "restore your drive, focus, and stamina faster than anything you have tried."
- That is a high-risk superiority/outcome claim.

Copy risk:

- "Your energy is dropping right now"
- "not just getting older"
- "the gut that won't budge"
- "that's not laziness"
- "three systems keep declining"
- survey proof claims and "every cent back" refund language

Policy trace:

- UBP: exaggerated health/success claims, especially "faster than anything".
- Personal Attributes: direct assertions about the viewer's energy, age, body, and behavior.
- Health and Wellness: negative self-perception around gut, laziness, and declining systems.

System issue:

- The copy checker missed this because its negative-self-perception regex was too narrow and did not include personal-attribute detection.
- Image OCR would have caught the strongest "science-backed" and "faster than anything" risk.

### `curated-24-quiz`

- Meta ad id: `120245565404140293`
- Duplicate issue ad: `120245547747030293`
- Destination: quiz
- Source image: `boss_babe.jpg`
- Copy: `COPY018`, "52% Off Limited-Time Welcome Offer"
- Internal copy QA: `META-COPY-005`
- Meta result: UBP disapproved

Creative risk:

- Pre-grouped image says "Specialist: Men losing their energy and drive share one overlooked trait".
- "Specialist" implies authority without clear substantiation.
- "one overlooked trait" creates hidden-cause bait.

Copy risk:

- "Noticed your midsection holding on"
- "soft tissue where definition used to be"
- "visible sign of what's shifting inside"
- "stored fat where lean tissue should be"
- survey proof claims

Policy trace:

- UBP: hidden-cause and specialist framing around health/body claims.
- Health and Wellness: direct body-image negative self-perception.
- Personal Attributes: implies the viewer has a midsection/body composition issue.

System issue:

- QA caught the negative self-perception issue but did not block publish.
- It did not score the "specialist/overlooked trait" visual claim.

## Landing Page Audit

### GLP Lander

URL: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/`

Status: `200`

Top-page findings:

- Title: "10 Reasons Why GLP-1s are secretly crashing your testosterone (and the $1.17 natural fix that restores it)"
- Hero warning: "If you're on a GLP-1, read this before your next shot."
- Before/after body transformation image labeled "verified customer".
- First reason: "It stops cortisol from eating your muscle for fuel."

Crawler term counts:

- `GLP-1`: `14`
- `testosterone`: `10`
- `cortisol`: `7`
- `muscle`: `22`
- `52%`: `8`
- `90-day`: `3`
- survey terms present: `1,203`, `94%`, `87%`, `92%`

Policy risk:

- Critical UBP risk: "secretly crashing", "$1.17 natural fix", "restores it", and cortisol/muscle claims are strong health-mechanism and solution claims.
- Critical Health and Wellness risk: before/after body image on a weight-loss-related page.
- High Personal Attributes risk: page directly addresses GLP-1 users and "your testosterone".

Footer/legal:

- Privacy, terms, and contact are present.
- This means the earlier footer false positive was a scanner truncation issue, not an actual missing-footer issue.

### Quiz Lander

URL: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/`

Status: `200`

Top-page findings:

- Headline: "Find Out What's Really Happening With Your Testosterone"
- Supporting copy says the assessment analyzes symptoms, lifestyle, and risk factors.
- First question asks age, with age bands starting at `20-29`.

Policy risk:

- Medium-to-high Personal Attributes risk: the page asks and analyzes age, symptoms, lifestyle, risk factor, and testosterone.
- Medium UBP risk: the quiz promises diagnostic-style insight before selling a supplement.
- Business trust/congruence issue: footer privacy/contact links point to `mengotomars.com`, while the campaign domain and brand are `shoptenorco.com` / Tenor.

Footer/legal:

- Privacy/contact links exist, but domain mismatch should be fixed for trust and congruence.

### Sales Page

URL: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/sales-page/?selling_plan=2948432039`

Status: `200`

Top-page findings:

- Product is framed as "Testosterone Restoration Blend".
- Bullets include "Restores, protects, and activates testosterone naturally".
- Also claims defense against cortisol spikes.
- Offer is visible: `$44`, `$92`, `52% off`, 90-day guarantee, 30-day refill language, $35 gift kit.

Crawler term counts:

- `testosterone`: `19`
- `drive`: `38`
- `energy`: `20`
- `52%`: `19`
- `$44`: `7`
- `$35`: `7`
- `90-day`: `14`
- `prescription`: `5`
- `needle`: `3`

Policy risk:

- High UBP risk: "Testosterone Restoration Blend" and "restores... testosterone naturally" are stronger than structure/function support language.
- High medical-comparison risk: repeated "no needles / no prescription" comparisons position the supplement against medical treatment.
- Offer congruence is mostly good: `$44`, `52%`, `90-day`, and `$35` are present.

## Why Our System Missed This

1. Full paid ads QA was not enforced as a hard publish gate.
2. The copy policy checker is too narrow and catches only obvious private-info/discrimination/negative-self-perception patterns.
3. There is no UBP classifier for exaggerated health benefits, hidden-cause framing, or deceptive medical authority posture.
4. Generated image OCR was not checked before publish.
5. Visual source classification was missing, so doctor/researcher/news/report/MRI imagery passed.
6. Curated source hygiene was weak; a contact-sheet asset was allowed into generation.
7. Landing-page review did not evaluate claim severity or ad-to-page congruence. It mostly checked reachability and legal footer basics.
8. The earlier landing-page scanner truncated text at 50k characters, which could create false footer findings. A branch now fixes that truncation.

## Proposed Robust Policy Layer

### New Rule Families

| Rule | Scope | Action |
| --- | --- | --- |
| `META-UBP-HEALTH-EXAGGERATED` | Copy, OCR, landing pages | Block or require manual approval for "restore", "fix", "secret", "doctor didn't mention", "science found", "faster than anything", disease/medical mechanism claims |
| `META-HW-NEGATIVE-BODY` | Copy, OCR, landing pages | Block body shame, before/after weight-loss imagery, "gut won't budge", "soft tissue", "midsection holding on" |
| `META-PA-HEALTH-ATTRIBUTE` | Copy and landing pages | Flag second-person health, age, medical, symptom, body, or testosterone assertions |
| `META-VIS-MEDICAL-AUTHORITY` | Images | Flag doctors, lab coats, researchers, scans, medical charts, news/report frames, "specialist", "doctor", "researchers" |
| `META-VIS-NEWS-BAIT` | Images | Flag fake news labels, click-to-reveal, hidden cause, "one overlooked trait", "nobody warned" |
| `META-PROOF-SUBSTANTIATION` | Copy, OCR, landing pages | Require proof record for survey percentages, clinical/testing claims, and named doctor/authority claims |
| `META-CONGRUENCE-DOMAIN` | Destinations | Flag footer/legal/domain mismatch, e.g. `mengotomars.com` footer on Tenor quiz |
| `META-SOURCE-HYGIENE` | Swipe source | Block contact sheets, collages, review sheets, placeholder/reference boards |
| `META-LP-CLAIM-SEVERITY` | Landing pages | Score destination claims, not just footer/reachability |

### Required Gate Before Publish

The publish path should fail closed when:

- Any generated image OCR contains a blocker.
- Any ad copy contains UBP health exaggeration or personal-attribute blockers.
- The destination page contains high-severity claims that are not represented in the congruence map.
- The ad uses medical-authority imagery without approved substantiation.
- Quiz or sales legal/footer links point to a mismatched brand/domain.
- Weight-loss or health ads are not targeted 18+.

### Review Output Needed

For human review speed, each pre-publish report should show:

- Meta ad name and destination.
- Copy risk snippets.
- Image thumbnail and OCR text.
- Landing page risk snippets.
- Policy mapping.
- Suggested decision: pass, revise, block, or legal/manual review.

## Recommended Immediate Remediation

1. Do not appeal these exact ads as-is.
2. Remove medical authority/news/researcher creative framing from curated swipes for this campaign.
3. Rewrite GLP copy away from "doctor didn't mention", "secretly crashing testosterone", "natural fix", and direct cortisol/muscle-for-fuel claims.
4. Remove before/after body imagery from the GLP lander if this funnel is intended for Meta paid traffic.
5. Fix quiz footer links to Tenor/shoptenorco.com.
6. Change sales page language from testosterone restoration to softer support language before sending more traffic from Meta.
7. Add OCR and landing-page claim severity gates before the next publish.

