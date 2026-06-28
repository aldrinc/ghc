# Whole Campaign Representative QA Classification

## Decision

The full representative audit is now materially complete: `83 / 83` logical groups have an LLM result after retrying `curated-03-quiz` and reusing the earlier successful `curated-02-quiz` run. The validator is broadly catching real creative/copy policy risk, but landing-page findings are polluted by a confirmed snapshot-source bug and should not be treated as true page failures until that is fixed.

## Coverage

- Logical groups covered: `83 / 83`
- Representative selection: one current-generation primary asset per logical group, not every aspect-ratio sibling
- Current generation key: `batch:tenor-glp-quiz-problem-aware-expansion-20260506`
- Raw findings: `418`
- Adjusted findings after deduplicating repeated account readiness checks: `336`

## Classification Counts

- `likely_true_positive`: `237`
- `confirmed_false_positive`: `86`
- `likely_false_positive`: `12`
- `needs_review`: `1`

## Rule Counts

- `META-IMAGE-001`: `80`
- `META-UBP-001`: `78`
- `META-COPY-006`: `57`
- `META-LP-005`: `43`
- `META-LP-006`: `43`
- `META-COPY-005`: `16`
- `META-LP-007`: `12`
- `META-COPY-002`: `6`
- `META-ACCOUNT-008`: `1`

## Confirmed / Likely False Positives

### Landing Page Privacy / Contact

Classification: `confirmed_false_positive` for `META-LP-005` and `META-LP-006`.

The live GLP and quiz URLs both contain privacy/contact/support footer text. Production QA was not inspecting the live HTML for these URLs; it parsed the ShopTenor path as a MOS public funnel route and used `inspectionSource: public_funnel_api`. For GLP that returned an empty body; for quiz it returned internal placeholder content. These LP-005/LP-006 findings should be ignored for Meta compliance and used as a system bug signal.

### Quiz Placeholder / Congruence

Classification: `likely_false_positive` for `META-LP-007` where the evidence cites `Presales Placeholder`, `Final copy and creative can be added later`, or missing quiz substantiation from the internal snapshot.

The live quiz URL did not contain those placeholder strings in direct HTTP inspection. These findings are likely caused by the same snapshot routing bug. However, once snapshot routing is fixed, quiz congruence should still be rechecked because several ads make strong quiz/personalized-profile promises.

### Account Readiness

Classification: `needs_review` for one deduplicated `META-ACCOUNT-008`.

This repeated once per group only because the checkpoint runner called campaign QA one group at a time. The real issue is a single account/profile readiness question: MOS tracking is active, but the helper requires `SalesToCheckoutClick`; the profile currently has `Entered Funnel`, `PageView`, `ViewContent`, `PreSalesToSalesClick`, `AddToCart`, and `Purchase`. This may be a real event-contract gap or an overly strict rule for an external-URL campaign.

## Likely True Positive Patterns

- `META-UBP-001`: hidden-cause, fake authority, sensational health/body framing, quiz-bait framing, or unsupported result framing.
- `META-IMAGE-001`: doctor/lab-coat/medical-scan visuals, fake editorial/report layouts, before/after body transformations, click-to-reveal or diagnostic quiz imagery.
- `META-COPY-006`: direct personal health/body/age/GLP-prescription targeting such as saying or implying the viewer has a condition, symptom, medication status, weight-loss state, or age-related decline.
- `META-COPY-005`: negative self-perception/body-shaming framing, especially midsection, soft tissue, crashing, drained, not yourself, or decline language.
- `META-COPY-002`: stronger private-knowledge variants, especially where copy implies knowledge of the viewer’s prescription or medical context.

Note: none of this treats the word `testosterone` alone as a violation. The flags are tied to personal attribution, hidden-cause framing, body/age targeting, or authority/diagnostic presentation.

## Groups With Likely True Positive Findings

### `curated-01-glp`

- Row: `CURATED-01-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Editorial/news-style creative reinforces misleading medical authority
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Personal health attribute implication

### `curated-01-quiz`

- Row: `CURATED-01-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: News/medical-style creative suggests authority and diagnosis
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct personal-health targeting

### `curated-02-glp`

- Row: `CURATED-02-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: News/expert-style creative reinforces misleading health framing
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `curated-02-quiz`

- Row: `CURATED-02-QUIZ`
- Source: `None` / `None` / `COPY012`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Creative reinforces age/body-targeted callout
- `META-UBP-001` `blocker`: Sensational hidden-cause framing
- `META-COPY-006` `high`: Direct age/health callout to the viewer

### `curated-03-glp`

- Row: `CURATED-03-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Creative reinforces misleading medical warning framing
- `META-UBP-001` `blocker`: Sensational hidden-cause framing around health outcomes
- `META-COPY-006` `high`: Direct viewer health-attribute assumption

### `curated-03-quiz`

- Row: `CURATED-03-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY013`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Image reinforces a personal-condition callout
- `META-UBP-001` `blocker`: Hidden-cause / bait-style claims in ad copy

### `curated-04-glp`

- Row: `CURATED-04-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Pseudo-doctor authority creative
- `META-UBP-001` `blocker`: Hidden-cause and fake-authority health framing
- `META-COPY-006` `high`: Direct personal health/body implication

### `curated-04-quiz`

- Row: `CURATED-04-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY014`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Fake doctor authority in creative
- `META-UBP-001` `blocker`: Misleading health/drive results framing

### `curated-05-glp`

- Row: `CURATED-05-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Image reinforces medical concern bait
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Direct bodily effect attributed to viewer

### `curated-05-quiz`

- Row: `CURATED-05-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY015`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Creative reinforces age-based diagnostic framing
- `META-UBP-001` `blocker`: Hidden-cause / sensational framing
- `META-COPY-005` `high`: Negative self-perception / shame framing
- `META-COPY-006` `high`: Direct age and condition callout to the viewer

### `curated-06-glp`

- Row: `CURATED-06-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Image reinforces medical targeting and sensational outcome framing
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Direct personal health-attribute targeting

### `curated-06-quiz`

- Row: `CURATED-06-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY016`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image directly calls out viewer fatigue and low drive/focus
- `META-UBP-001` `blocker`: Quiz/protocol framing reads as hidden-cause bait

### `curated-07-glp`

- Row: `CURATED-07-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Alarmist medical-style creative
- `META-UBP-001` `blocker`: Hidden-cause / sensational health framing
- `META-COPY-005` `high`: Negative self-perception and depletion framing
- `META-COPY-006` `high`: Direct personal health/body attribute implication

### `curated-07-quiz`

- Row: `CURATED-07-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY017`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Quiz-style image implies pseudo-diagnostic reveal
- `META-UBP-001` `blocker`: Hidden-cause sensational framing
- `META-COPY-006` `high`: Direct age/body attribute claim

### `curated-08-glp`

- Row: `CURATED-08-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Creative reinforces negative body-result framing
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `curated-08-quiz`

- Row: `CURATED-08-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY018`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Creative reinforces fatigue/decline callout
- `META-UBP-001` `blocker`: Hidden-cause and pseudo-scientific framing
- `META-COPY-005` `high`: Health/wellness copy uses body-insecurity framing
- `META-COPY-006` `high`: Direct personal body/energy attribute claims

### `curated-09-glp`

- Row: `CURATED-09-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Image reinforces weight-loss/body-result bait
- `META-UBP-001` `blocker`: Hidden-cause and authority framing is misleading
- `META-COPY-006` `high`: Direct viewer health-status implication

### `curated-09-quiz`

- Row: `CURATED-09-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Age callout in the creative
- `META-UBP-001` `blocker`: Hidden-cause and quasi-scientific framing
- `META-COPY-006` `high`: Direct health, body, and age attribute targeting

### `curated-10-glp`

- Row: `CURATED-10-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-COPY-002` `blocker`: Private medical knowledge implied
- `META-IMAGE-001` `blocker`: Creative reinforces misleading weight-loss narrative
- `META-UBP-001` `blocker`: Hidden-cause medical framing
- `META-COPY-005` `high`: Negative self-perception framing
- `META-COPY-006` `high`: Viewer health/body state is asserted

### `curated-10-quiz`

- Row: `CURATED-10-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY012`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image uses personal-attribute quiz bait
- `META-UBP-001` `blocker`: Hidden-cause and scare framing
- `META-COPY-006` `high`: Direct second-person health/body callout

### `curated-11-glp`

- Row: `CURATED-11-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: News/doctor authority creative may mislead
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `curated-11-quiz`

- Row: `CURATED-11-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY013`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Medical authority and age/health decline creative
- `META-UBP-001` `blocker`: Hidden-cause / diagnostic framing

### `curated-12-glp`

- Row: `CURATED-12-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-COPY-002` `blocker`: Implied knowledge of the viewer's prescription
- `META-IMAGE-001` `blocker`: Image reinforces personal health outcome framing
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Direct personal health/body attribute targeting

### `curated-12-quiz`

- Row: `CURATED-12-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY014`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Image uses a direct personal-attribute / negative-self-perception prompt

### `curated-13-glp`

- Row: `CURATED-13-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Creative reinforces clickbait testimonial and negative health outcome
- `META-UBP-001` `blocker`: Sensational hidden-cause framing around GLP-1 effects
- `META-COPY-006` `high`: Viewer’s medical/body state is implied

### `curated-13-quiz`

- Row: `CURATED-13-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY015`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Creative reinforces a misleading diagnosis/transformation narrative
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct age/body personalization to the viewer

### `curated-14-glp`

- Row: `CURATED-14-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Testimonial-style health-result creative
- `META-UBP-001` `blocker`: Sensational hidden-cause / quick-fix framing
- `META-COPY-006` `high`: Direct body-outcome phrasing

### `curated-14-quiz`

- Row: `CURATED-14-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY016`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image uses hidden-cause quiz/testimonial framing
- `META-UBP-001` `blocker`: Ad experience uses hidden-cause bait framing

### `curated-15-glp`

- Row: `CURATED-15-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Creative reinforces concealed medical-side-effect claim
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Viewer-specific medical assumption

### `curated-15-quiz`

- Row: `CURATED-15-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY017`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Image reinforces personal-attribute callout
- `META-UBP-001` `blocker`: Hidden-cause / sensational health framing
- `META-COPY-005` `high`: Negative self-perception / shame framing
- `META-COPY-006` `high`: Direct viewer age/energy attribute claim

### `curated-16-glp`

- Row: `CURATED-16-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: News-style fake authority creative
- `META-UBP-001` `blocker`: Hidden-cause / sensational framing
- `META-COPY-006` `high`: Viewer-directed health/body implications

### `curated-16-quiz`

- Row: `CURATED-16-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY018`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Creative repeats personal-attribute and bait-style framing
- `META-UBP-001` `blocker`: Hidden-cause and sensational framing
- `META-COPY-005` `high`: Negative self-perception body hook
- `META-COPY-006` `high`: Direct personal body and health attribution

### `curated-17-glp`

- Row: `CURATED-17-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Medical authority / misleading medical implication in creative
- `META-UBP-001` `blocker`: Sensational hidden-cause medical scare framing
- `META-COPY-006` `high`: Personal health/body attribute implication

### `curated-17-quiz`

- Row: `CURATED-17-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Doctor-themed creative reinforces diagnosis/cause claim
- `META-UBP-001` `blocker`: Hidden-cause and sensational wellness framing
- `META-COPY-006` `high`: Direct personal health attribute callout

### `curated-18-glp`

- Row: `CURATED-18-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-COPY-002` `blocker`: Implies private medical status
- `META-IMAGE-001` `blocker`: Image reinforces personal-attribute risk
- `META-UBP-001` `blocker`: Sensational hidden-cause framing
- `META-COPY-006` `high`: Direct personal health/body callout

### `curated-18-quiz`

- Row: `CURATED-18-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY012`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Creative reinforces personal-attribute health diagnosis framing
- `META-UBP-001` `blocker`: Hidden-cause / pseudo-scientific health explanation
- `META-COPY-005` `high`: Negative self-perception / shame framing
- `META-COPY-006` `high`: Direct personal health/age callout in ad copy

### `curated-19-glp`

- Row: `CURATED-19-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Warning-style creative reinforces misleading health authority
- `META-UBP-001` `blocker`: Hidden-cause and authority-framed health messaging
- `META-COPY-006` `high`: Direct viewer health/body implication

### `curated-19-quiz`

- Row: `CURATED-19-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY013`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Direct personal-attribute hook in image

### `curated-20-glp`

- Row: `CURATED-20-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Creative reinforces misleading body/medical risk
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Direct GLP-1 medical-status callout

### `curated-20-quiz`

- Row: `CURATED-20-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY014`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Viewer-directed age and health decline callout
- `META-UBP-001` `blocker`: Sensational hidden-cause quiz framing

### `curated-21-glp`

- Row: `CURATED-21-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Image reinforces weight-loss result framing and personal-attribute callout
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct medical/personal-attribute framing

### `curated-21-quiz`

- Row: `CURATED-21-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY015`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Creative visually reinforces age-targeting and outcome framing
- `META-UBP-001` `blocker`: Hidden-cause / sensational health framing
- `META-COPY-006` `high`: Direct age and body-state callout

### `curated-22-glp`

- Row: `CURATED-22-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Creative reinforces negative body/result framing
- `META-UBP-001` `blocker`: Hidden-cause and sensational medical framing
- `META-COPY-006` `high`: Direct personal health/body attribution

### `curated-22-quiz`

- Row: `CURATED-22-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY016`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image directly calls out the viewer's energy/drive state

### `curated-23-glp`

- Row: `CURATED-23-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Creative reinforces age and transformation risk
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing
- `META-COPY-006` `high`: Viewer body/health attribute implied

### `curated-23-quiz`

- Row: `CURATED-23-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY017`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Creative reinforces personal-attribute fatigue callout
- `META-UBP-001` `blocker`: Hidden-cause and sensational framing
- `META-COPY-006` `high`: Direct age and fatigue callout

### `curated-24-glp`

- Row: `CURATED-24-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-COPY-002` `blocker`: Assumes the viewer's GLP-1 prescription status
- `META-IMAGE-001` `blocker`: Creative reinforces medical bait and targeted health-state callout
- `META-UBP-001` `blocker`: Sensational hidden-cause medical teaser
- `META-COPY-006` `high`: Direct health/body-state callout

### `curated-24-quiz`

- Row: `CURATED-24-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY018`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image amplifies quasi-medical hidden-cause pitch
- `META-UBP-001` `blocker`: Hidden-cause / sensational framing
- `META-COPY-005` `high`: Negative body-image hook
- `META-COPY-006` `high`: Direct personal health/body attribution

### `curated-25-glp`

- Row: `CURATED-25-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Fake article / authority-style creative
- `META-UBP-001` `blocker`: Hidden-cause / sensational medical framing
- `META-COPY-005` `high`: Negative self-perception / body-image pressure
- `META-COPY-006` `high`: Direct personal medical framing

### `curated-25-quiz`

- Row: `CURATED-25-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Fake news / expert-style creative
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct viewer health/age attribute claim

### `curated-26-glp`

- Row: `CURATED-26-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Image makes direct personal-attribute and hidden-cause health callouts
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing in ad copy

### `curated-26-quiz`

- Row: `CURATED-26-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY012`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-COPY-002` `blocker`: Implied private knowledge about the viewer
- `META-IMAGE-001` `blocker`: Creative text reinforces personal-attribute/shame risk
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-005` `high`: Shame / negative self-perception framing
- `META-COPY-006` `high`: Direct personal health/body/age callout

### `curated-27-glp`

- Row: `CURATED-27-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Body-result and personal-attribute visual reinforcement
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct personal-health attribute targeting

### `curated-27-quiz`

- Row: `CURATED-27-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY013`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Creative reinforces distress-based diagnosis
- `META-UBP-001` `blocker`: Sensational hidden-cause and expert-quiz framing

### `curated-28-glp`

- Row: `CURATED-28-GLP`
- Source: `standard_curated` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Publisher-style creative may mislead as editorial content
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct personal health-attribute implication

### `curated-28-quiz`

- Row: `CURATED-28-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY014`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Pseudo-editorial health quiz creative makes a viewer-specific diagnosis-style callout
- `META-UBP-001` `blocker`: Hidden-cause / bait-style funnel framing

### `curated-29-glp`

- Row: `CURATED-29-GLP`
- Source: `standard_curated` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Image reinforces the hidden-cause health claim
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `curated-29-quiz`

- Row: `CURATED-29-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY015`
- Headline: 90-Day Guarantee. Because It Works.
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-005` `high`: Shame-based negative self-perception
- `META-COPY-006` `high`: Direct age and body-state callout

### `curated-30-glp`

- Row: `CURATED-30-GLP`
- Source: `standard_curated` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-IMAGE-001` `blocker`: Testimonial-style image reinforces body/health risk
- `META-UBP-001` `blocker`: Sensational hidden-cause framing
- `META-COPY-006` `high`: Direct medical attribute implication

### `curated-30-quiz`

- Row: `CURATED-30-QUIZ`
- Source: `standard_curated` / `quiz` / `COPY016`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Creative visually reinforces fake authority and personal-attribute risk
- `META-UBP-001` `blocker`: Staged testimonial and diagnostic framing

### `tenor-01-C001-glp`

- Row: `01-TENOR-COPY001-C001`
- Source: `tenor_package` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Before/after body transformation creative
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Viewer health/body effects are strongly implied

### `tenor-02-C002-glp`

- Row: `02-TENOR-COPY001-C002`
- Source: `tenor_package` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Before/after body transformation creative
- `META-UBP-001` `blocker`: Hidden-cause and authority-style health framing
- `META-COPY-006` `high`: Personal health/body attribute implication

### `tenor-03-C004-glp`

- Row: `03-TENOR-COPY001-C004`
- Source: `tenor_package` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Before/after body-result comparison
- `META-UBP-001` `blocker`: Hidden-cause and pseudo-medical framing
- `META-COPY-005` `high`: Negative self-perception / shaming language
- `META-COPY-006` `high`: Implied viewer-specific medical/body state

### `tenor-04-C006-glp`

- Row: `04-TENOR-COPY001-C006`
- Source: `tenor_package` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Comparative body-result creative
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Implied viewer has a specific medical/body status

### `tenor-05-C011-glp`

- Row: `05-TENOR-COPY001-C011`
- Source: `tenor_package` / `glp` / `COPY001`
- Headline: What GLP-1 Does to Your Drive
- `META-IMAGE-001` `blocker`: Before/after body-result comparison
- `META-UBP-001` `blocker`: Hidden-cause / sensational health framing
- `META-COPY-005` `high`: Negative self-perception / body-shaming framing
- `META-COPY-006` `high`: Personal medical attribute implication

### `tenor-06-C008-glp`

- Row: `06-TENOR-COPY002-C008`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after body transformation visual
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `tenor-07-C003-glp`

- Row: `07-TENOR-COPY002-C003`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after body-transformation creative
- `META-UBP-001` `blocker`: Sensational health-risk framing

### `tenor-08-C009-glp`

- Row: `08-TENOR-COPY002-C009`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after body-result comparison in creative
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `tenor-09-C007-glp`

- Row: `09-TENOR-COPY002-C007`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after-style body comparison creative
- `META-UBP-001` `blocker`: Sensational health/body-outcome framing

### `tenor-10-C005-glp`

- Row: `10-TENOR-COPY002-C005`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after transformation creative
- `META-UBP-001` `blocker`: Sensational hidden-cause health framing

### `tenor-11-C010-glp`

- Row: `11-TENOR-COPY002-C010`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after-style body-result comparison
- `META-UBP-001` `blocker`: Hidden-cause and exaggerated health framing

### `tenor-12-C012-glp`

- Row: `12-TENOR-COPY002-C012`
- Source: `tenor_package` / `glp` / `COPY002`
- Headline: Keep Your Drive Steady on GLP-1s
- `META-IMAGE-001` `blocker`: Before/after transformation creative
- `META-UBP-001` `blocker`: Sensational health-outcome framing
- `META-COPY-006` `high`: Direct personal body-effect claim

### `tenor-13-C013-glp`

- Row: `13-TENOR-COPY003-C013`
- Source: `tenor_package` / `glp` / `COPY003`
- Headline: The GLP-1 Side Effect No One Mentions
- `META-COPY-002` `blocker`: Implied knowledge of the viewer's private medical information
- `META-IMAGE-001` `blocker`: Creative reinforces fake-news / hidden-cause medical framing
- `META-UBP-001` `blocker`: Sensational hidden-cause and authority-style framing
- `META-COPY-006` `high`: Direct personal health/medical attribute claim

### `tenor-14-C022-quiz`

- Row: `14-TENOR-COPY011-C022`
- Source: `tenor_package` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Creative reinforces quiz-bait and personal-callout risk
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct personal health/body attribute callout

### `tenor-15-C019-quiz`

- Row: `15-TENOR-COPY011-C019`
- Source: `tenor_package` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Image uses symptom-led quiz bait
- `META-UBP-001` `blocker`: Hidden-cause and pseudo-diagnostic framing
- `META-COPY-006` `high`: Direct personal health/body callouts in ad copy

### `tenor-16-C020-quiz`

- Row: `16-TENOR-COPY011-C020`
- Source: `tenor_package` / `quiz` / `COPY011`
- Headline: Stop Losing Drive. Start Today.
- `META-IMAGE-001` `blocker`: Creative reinforces quiz-bait diagnostic framing
- `META-UBP-001` `blocker`: Uses sensational hidden-cause and pressure framing
- `META-COPY-006` `high`: Directly attributes health and energy issues to the viewer

### `tenor-17-C016-quiz`

- Row: `17-TENOR-COPY012-C016`
- Source: `tenor_package` / `quiz` / `COPY012`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-005` `high`: Negative self-perception / shame framing
- `META-COPY-006` `high`: Direct age and body-attribute targeting

### `tenor-18-C017-quiz`

- Row: `18-TENOR-COPY013-C017`
- Source: `tenor_package` / `quiz` / `COPY013`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Negative self-perception hook in creative

### `tenor-19-C018-quiz`

- Row: `19-TENOR-COPY014-C018`
- Source: `tenor_package` / `quiz` / `COPY014`
- Headline: 52% Off + 90-Day Guarantee
- `META-IMAGE-001` `blocker`: Image makes a direct personal-attribute callout

### `tenor-20-C021-quiz`

- Row: `20-TENOR-COPY015-C021`
- Source: `tenor_package` / `quiz` / `COPY015`
- Headline: 90-Day Guarantee. Because It Works.
- `META-IMAGE-001` `blocker`: Creative callout to viewer state
- `META-UBP-001` `blocker`: Hidden-cause / sensational health framing
- `META-COPY-005` `high`: Negative self-perception / shame framing
- `META-COPY-006` `high`: Direct age and health-state callout

### `tenor-21-C023-quiz`

- Row: `21-TENOR-COPY016-C023`
- Source: `tenor_package` / `quiz` / `COPY016`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Image uses symptom-based personal-attribute bait
- `META-UBP-001` `blocker`: Quiz framing is not substantiated on the destination

### `tenor-22-C024-quiz`

- Row: `22-TENOR-COPY017-C024`
- Source: `tenor_package` / `quiz` / `COPY017`
- Headline: 90-Day Guarantee. Because It Works.
- `META-UBP-001` `blocker`: Hidden-cause and sensational health framing
- `META-COPY-006` `high`: Direct age/body callout to the viewer

### `tenor-23-C025-quiz`

- Row: `23-TENOR-COPY018-C025`
- Source: `tenor_package` / `quiz` / `COPY018`
- Headline: 52% Off Limited-Time Welcome Offer
- `META-IMAGE-001` `blocker`: Before/after transformation creative
- `META-UBP-001` `blocker`: Hidden-cause / sensational framing
- `META-COPY-005` `high`: Negative self-perception / body-shaming framing
- `META-COPY-006` `high`: Direct personal health/body attribute claim

## Groups Needing Rerun After Snapshot Fix

Rerun LP/account portions after fixing snapshot routing and clarifying event requirements. This affects all GLP LP marker findings, all quiz placeholder LP findings, and the duplicated account readiness finding.

## Artifact Paths

- Classified JSON: `/Users/aldrinclement/Documents/programming/marketi/outputs/mars-men-glp-quiz-campaign-package-2026-05-04/full-launch/problem-aware-full-campaign/full-representative-qa-2026-05-08/whole_campaign_representative_qa_classified_2026-05-08.json`
- This report: `/Users/aldrinclement/Documents/programming/marketi/outputs/mars-men-glp-quiz-campaign-package-2026-05-04/full-launch/problem-aware-full-campaign/full-representative-qa-2026-05-08/whole_campaign_representative_qa_classification_report_2026-05-08.md`