# Paid Ads QA Representative Rejected Groups Report

## Scope

- Campaign: `426afe15-ac66-436c-910d-2a1259597bf3`
- Generation: `batch:tenor-glp-quiz-problem-aware-expansion-20260506`
- Validation method: one current-generation `1:1` primary creative per known Meta-rejected group
- Important scope note: this run did not evaluate every campaign creative. It evaluated six representative groups and found multiple findings on those groups plus one account/profile finding.

## Run Summary

- Status: `failed`
- Runtime: `344.6` seconds
- Findings: `27`
- Severity counts: `13` blocker, `11` high, `3` medium, `0` low
- Rules fired: `META-ACCOUNT-008, META-COPY-005, META-COPY-006, META-IMAGE-001, META-LP-005, META-LP-006, META-LP-007, META-UBP-001`

## What Was Flagged Beyond The Six Known Groups

No extra creative groups were evaluated or flagged outside the six known groups in this representative run. The additional flags are additional policy issues within those six groups, plus one campaign/account configuration finding:

- `META-ACCOUNT-008`: Meta Data Set integration incomplete.
- `META-LP-005`: Privacy marker not detected on GLP destination during QA fetch.
- `META-LP-006`: Contact/support marker not detected on GLP destination during QA fetch.
- `META-LP-007`: Quiz destination mismatch/placeholder issue for `curated-24-quiz`.
- Multiple copy/image policy findings per creative: UBP, personal attributes, negative self-perception, medical authority/fake-science/hidden-cause imagery.

## Campaign/Profile Finding

### META-ACCOUNT-008 - Data Set integration is incomplete

- Severity: `high`
- Message: Meta Data Set should use the Shopify partner integration and Maximum data sharing, or have MOS-managed funnel tracking automation active.
- Evidence:
  - `dataSetShopifyPartnerInstalled`: `None`
  - `dataSetDataSharingLevel`: `None`
  - `mosMetaTrackingStatus`: `active`
  - `mosMetaTrackingMode`: `public_funnel_runtime`
  - `mosMetaTrackingPixelId`: `4578413032424797`

## Creative Group Findings

### curated-13-glp

- Row: `CURATED-13-GLP`
- Spec: `1fb7d892-60aa-4bf3-803e-4a16989a0eb2`
- Asset: `5aacf815-ba26-49ce-9994-2bb8d734db83`
- Headline: What GLP-1 Does to Your Drive
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Representative variant: `1:1` primary asset
- Findings: `6` (2 blocker, 3 high, 1 medium)

#### META-IMAGE-001 - Creative reinforces testimonial-style health bait

- Severity: `blocker`
- Status: `failed`
- Message: The image amplifies the same risky angle with a testimonial-like headline, a personal 'I' statement about losing weight and crashing energy, and a 'CLICK TO REVEAL' CTA. Visually, it reinforces deceptive health framing and clickbait rather than a straightforward product presentation.
- Key evidence:
  - Large headline: 'I Lost The Weight, But My Energy Crashed'
  - Body copy in the image says the person 'discovered what GLP-1s quietly drain from men'
  - The layout includes a prominent 'CLICK TO REVEAL' button
  - The portrait + testimonial layout creates pseudo-authority around a health claim
- Policy trace:
  - Meta policy review of ad creative media
  - Image creative visually reinforces policy risk, including misleading medical implication or direct personal-attribute callout
  - Visual bait/click-to-reveal framing can reinforce UBP risk

#### META-UBP-001 - Hidden-cause and sensational medical framing

- Severity: `blocker`
- Status: `failed`
- Message: The copy presents a sensational causal explanation for GLP-1 use ('rapid weight loss floods your system with cortisol') and frames the product as revealing a secret problem your doctor 'didn't mention.' That combination reads as misleading hidden-cause and bait-style health framing rather than neutral product promotion.
- Key evidence:
  - "your prescribing doctor didn't mention"
  - "Rapid weight loss floods your system with cortisol."
  - "GLP-1s quietly drain" / "what GLP-1 does to your drive"
  - "Click to reveal" style hook in the creative experience
- Policy trace:
  - Meta Unacceptable Business Practices
  - Not allowed: deceptive or misleading promotion of products, services, schemes, or offers
  - Not allowed: fake authority, fake news, or fake scientific framing that could mislead people about the product, service, or offer
  - Not allowed: exaggerated health-result or hidden-cause framing used to pressure action

#### META-COPY-005 - Negative self-perception / distress framing

- Severity: `high`
- Status: `failed`
- Message: The ad uses deficit and deterioration language to make the audience feel worse about weight loss and energy changes, including 'foggier, flatter,' 'running on fumes,' and 'your presence fades.' This exploits negative self-perception to push the supplement.
- Key evidence:
  - "Your mornings get heavier."
  - "Your afternoons disappear."
  - "Your presence fades."
  - "You're lighter on the scale — but foggier, flatter, and running on fumes."
- Policy trace:
  - Meta Health and Wellness negative self-perception
  - Not allowed: copy that exploits insecurities, body-shaming, or negative body image to promote a health-related product

#### META-COPY-006 - Direct personal health-attribute implication

- Severity: `high`
- Status: `failed`
- Message: The copy speaks as if the viewer has a GLP-1 prescription and a related doctor-patient context, which implies a personal medical attribute. This moves beyond general audience language and into protected health-attribute targeting.
- Key evidence:
  - "your prescribing doctor didn't mention" presumes the viewer has a prescription and related medical care
  - "See why men on GLP-1s are adding this two-capsule morning protocol" narrows the audience to a specific treatment status
  - The copy addresses the viewer's energy and weight-loss experience as if that medical situation is known
- Policy trace:
  - Meta Privacy Violations and Personal Attributes
  - Not allowed: using you/your/other language to reference a protected personal attribute
  - Not allowed: implying the advertiser knows the viewer's medical information

#### META-LP-005 - Privacy policy marker not found on destination

- Severity: `high`
- Status: `failed`
- Message: The destination page does not visibly reference privacy handling.

#### META-LP-006 - Contact or support marker not found on destination

- Severity: `medium`
- Status: `failed`
- Message: The destination page does not visibly expose contact or support information.

### curated-16-glp

- Row: `CURATED-16-GLP`
- Spec: `c57f8f27-0938-47ea-88c7-011e8e897532`
- Asset: `e33bde34-c537-48f9-9001-ab22449593b3`
- Headline: What GLP-1 Does to Your Drive
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Representative variant: `1:1` primary asset
- Findings: `5` (2 blocker, 2 high, 1 medium)

#### META-IMAGE-001 - Image mimics a news/report article

- Severity: `blocker`
- Status: `failed`
- Message: The creative visually reinforces the same risk: it looks like a men's health report with a portrait, a headline starting with Doctors:, and a Read this 3-min article callout. That styling suggests editorial or scientific authority rather than a straightforward ad.
- Key evidence:
  - Top banner says MEN'S HEALTH REPORT
  - Large article-style headline begins Doctors: Men On GLP-1s Lose Weight But Quietly Drain Their Drive
  - Read this 3-min article prompt reinforces editorial framing
  - Portrait of a distressed-looking man supports the implied health concern
- Policy trace:
  - Image creative visually reinforces a policy risk, including fake authority/news/science framing, misleading medical implication, before/after body-result framing, or direct personal-attribute callout.
  - Meta policy review of ad creative media

#### META-UBP-001 - Sensational hidden-cause and fake-authority framing

- Severity: `blocker`
- Status: `failed`
- Message: The ad uses a hidden-cause narrative and authority cues to pressure a purchase: rapid weight loss allegedly floods the system with cortisol, a doctor supposedly omitted this risk, and the product is positioned as the fix. The survey claim and results you can feel language add promotional certainty without enough substantiation.
- Key evidence:
  - Rapid weight loss floods your system with cortisol
  - what your prescribing doctor didn't mention
  - That's not progress. That's a trade you didn't agree to
  - In a survey of 1,203 men, 94% reported sustained morning energy
  - Results you can feel — backed by transparent dosing, not promises
- Policy trace:
  - Ad experience uses deceptive, misleading, sensational, fake-authority, or hidden-cause framing around a product, service, scheme, offer, or health/body outcome.
  - Meta Unacceptable Business Practices

#### META-COPY-006 - Viewer-specific GLP-1 health implication

- Severity: `high`
- Status: `failed`
- Message: The copy talks to the reader as if they personally take GLP-1 medication and are experiencing medical/body effects. Phrases like your prescribing doctor didn't mention, your mornings get heavier, and your afternoons disappear imply knowledge of the viewer's private health status.
- Key evidence:
  - Uses second person around medical treatment: your prescribing doctor didn't mention
  - Attributes energy and fog effects to the reader: your mornings get heavier, your afternoons disappear
  - Frames the audience as people on GLP-1s and ties outcomes to them personally
- Policy trace:
  - Ad copy makes a direct personal health/body/medical attribute claim about the viewer.
  - Meta Privacy Violations and Personal Attributes

#### META-LP-005 - Privacy policy marker not found on destination

- Severity: `high`
- Status: `failed`
- Message: The destination page does not visibly reference privacy handling.

#### META-LP-006 - Contact or support marker not found on destination

- Severity: `medium`
- Status: `failed`
- Message: The destination page does not visibly expose contact or support information.

### curated-17-glp

- Row: `CURATED-17-GLP`
- Spec: `55120215-56dc-49b8-ac84-2db06ee8fed6`
- Asset: `78c509b8-2fbc-4f7a-9945-a0575fab1092`
- Headline: Keep Your Drive Steady on GLP-1s
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/
- Representative variant: `1:1` primary asset
- Findings: `4` (2 blocker, 1 high, 1 medium)

#### META-IMAGE-001 - Medical authority creative cue

- Severity: `blocker`
- Status: `failed`
- Message: The image visually reinforces a pseudo-clinical message by showing a doctor in a lab coat and stethoscope beside medical scans, paired with 'READ THE PROTOCOL' and 'GLP-1 USERS' copy. That combination can imply medical or scientific authority without clear substantiation.
- Key evidence:
  - Creative features a doctor-like figure in a white coat with a stethoscope in front of scan imagery.
  - Overlay text reads 'GLP-1 USERS: RAPID WEIGHT LOSS CAN QUIETLY DRAIN YOUR ENERGY, DRIVE, AND METABOLISM. HERE IS WHAT TO DO NEXT. READ THE PROTOCOL.'
- Policy trace:
  - Meta creative review flags fake authority, misleading medical implication, and science/doctor framing that can reinforce deceptive health claims.
  - The image pairs a clinical visual with an urgent health warning, creating a stronger medical-authority impression than the product facts support.
  - 'Read the protocol' suggests an expert-backed regimen without clear proof or disclosure.

#### META-UBP-001 - Sensational GLP-1 health-risk framing

- Severity: `blocker`
- Status: `failed`
- Message: The copy uses an exaggerated, causally certain claim that GLP-1s make 'your body start burning muscle for fuel — not fat,' then positions the supplement as the answer. That health-outcome framing is sensational and can mislead viewers about the actual cause, effect, and benefits.
- Key evidence:
  - Primary text says: 'GLP-1s cut appetite so hard your body starts burning muscle for fuel — not fat.'
  - The ad adds urgency with 'No shutdown' and 'Here is what to do next' style language.
- Policy trace:
  - Meta Unacceptable Business Practices prohibits deceptive, misleading, sensational, or hidden-cause framing around a product or health/body outcome.
  - The copy presents a strong physiological consequence without qualification and uses it to create urgency to buy.
  - The offer is framed as a remedy to a medically toned problem rather than a clearly substantiated product benefit.

#### META-LP-005 - Privacy policy marker not found on destination

- Severity: `high`
- Status: `failed`
- Message: The destination page does not visibly reference privacy handling.

#### META-LP-006 - Contact or support marker not found on destination

- Severity: `medium`
- Status: `failed`
- Message: The destination page does not visibly expose contact or support information.

### curated-02-quiz

- Row: `CURATED-02-QUIZ`
- Spec: `04745568-24bf-42e4-8a98-cc894aa87486`
- Asset: `25a0d7ae-28b7-4825-b938-ba5f7888b4ed`
- Headline: 52% Off Limited-Time Welcome Offer
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Representative variant: `1:1` primary asset
- Findings: `3` (2 blocker, 1 high)

#### META-IMAGE-001 - Creative reinforces age/body-targeted callout

- Severity: `blocker`
- Status: `failed`
- Message: The image headline says "A NEW QUIZ IS HELPING MEN RECLAIM THEIR DRIVE AFTER 40" and "A guided path for men who feel their energy and stamina have changed." Combined with the close-up male portrait and selfie inset, the creative visually reinforces age/body-state targeting.
- Key evidence:
  - Overlay text: "A NEW QUIZ IS HELPING MEN RECLAIM THEIR DRIVE AFTER 40"
  - Overlay text: "A guided path for men who feel their energy and stamina have changed."
  - Portrait + inset selfie presentation suggests personal transformation / quiz bait framing
- Policy trace:
  - Meta policy review of ad creative media

#### META-UBP-001 - Sensational hidden-cause framing

- Severity: `blocker`
- Status: `failed`
- Message: The copy uses a hidden-cause narrative and pressure framing: "Here's why," "It's not willpower. It's your systems," and "The pathways behind energy, drive, and stamina start declining around 30." It also contrasts supplements with clinics/prescriptions/needles in a scare-style way.
- Key evidence:
  - "Here's why."
  - "It's not willpower. It's your systems."
  - "The pathways behind energy, drive, and stamina start declining around 30."
  - "Or worse — considering a clinic, a prescription, needles."
- Policy trace:
  - Meta Unacceptable Business Practices

#### META-COPY-006 - Direct age/health callout to the viewer

- Severity: `high`
- Status: `failed`
- Message: The ad copy strongly implies the viewer has specific age and body-state attributes, e.g. "If you're over 40" and "you're STILL crashing by 3 p.m. and gaining weight." That is a personal-attribute-style callout tied to health/body and age.
- Key evidence:
  - "You're STILL crashing by 3 p.m. and gaining weight."
  - "If you're over 40 and constantly dragging through the day"
  - "the feeling that your body is actually responding"
- Policy trace:
  - Meta Privacy Violations and Personal Attributes

### curated-17-quiz

- Row: `CURATED-17-QUIZ`
- Spec: `008d0684-09ea-4e2d-b848-25f90ec89732`
- Asset: `38d7e49f-9685-4fad-824d-44b1eebd3a74`
- Headline: Stop Losing Drive. Start Today.
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Representative variant: `1:1` primary asset
- Findings: `3` (2 blocker, 1 high)

#### META-IMAGE-001 - Doctor imagery implies medical authority and diagnosis

- Severity: `blocker`
- Status: `failed`
- Message: The image uses a lab-coat doctor, stethoscope, and anatomy-scan backdrop to create medical authority, and the on-image text says the quiz can 'identify the cause.' That visually reinforces a diagnostic claim tied to the viewer's own health state.
- Key evidence:
  - A man in a white lab coat with a stethoscope is presented as medical authority.
  - The background shows a glowing human-body scan/anatomy display.
  - On-image text: 'If your energy, drive, and stamina don't feel like they used to, this quiz can help identify the cause.'

#### META-UBP-001 - Hidden-cause and pseudo-medical framing

- Severity: `blocker`
- Status: `failed`
- Message: The copy presents a hidden internal cause for the user's experience and uses quasi-medical language to pressure action. Phrases like 'three systems keep declining together' and 'That's a system problem' read like a diagnosis narrative rather than a straightforward product ad.
- Key evidence:
  - "Every month you put off doing something about it, three systems keep declining together."
  - "The pathway your body uses to produce drive gets quieter."
  - "That's a system problem. And it compounds the longer you wait."

#### META-COPY-006 - Direct viewer health-attribute claims

- Severity: `high`
- Status: `failed`
- Message: The ad copy repeatedly addresses the viewer as if they currently have low energy, brain fog, gut changes, and reduced stamina. That implies knowledge of the user's own health/body state rather than speaking generally about the product category.
- Key evidence:
  - "Your energy is dropping right now."
  - "That brain fog at 2 p.m.? The gut that won't budge no matter what you eat? The fact that you'd rather scroll your phone than do anything with your evening?"
  - "And it's not 'just getting older.'"

### curated-24-quiz

- Row: `CURATED-24-QUIZ`
- Spec: `ac2f5444-b827-487a-8dcd-6ec29977f085`
- Asset: `355f5a45-b319-4a19-bf15-ab3932785d87`
- Headline: 52% Off Limited-Time Welcome Offer
- Destination: https://shoptenorco.com/8b89a76d/daily-drive-essentials/quiz/
- Representative variant: `1:1` primary asset
- Findings: `5` (3 blocker, 2 high)

#### META-IMAGE-001 - Image reinforces authority and hidden-reason risk

- Severity: `blocker`
- Status: `failed`
- Message: The image overlays a portrait with 'Specialist: Men Losing Their Energy and Drive Share One Overlooked Reason' and 'Take the 2-min quiz.' That creates a specialist/authority implication, a hidden-reason promise, and a direct callout to men with energy/drive issues, which visually reinforces policy risk.
- Key evidence:
  - Visible overlaid text: "Specialist: Men Losing Their Energy and Drive Share One Overlooked Reason"
  - Visible overlaid text: "Take the 2-min quiz"
  - Portrait-style creative presented as expert-led health guidance
- Policy trace:
  - Meta policy review of ad creative media

#### META-LP-007 - Landing page does not substantiate the quiz promise

- Severity: `blocker`
- Status: `failed`
- Message: The destination is only a 'Presales Placeholder' and says 'Final copy and creative can be added later,' so it does not actually deliver the promised quiz or substantiate the ad's personalized-drive framing before sending users to continue to Tenor. That mismatch can read as a bait-style funnel step.
- Key evidence:
  - "Presales Placeholder"
  - "Take the Tenor Daily Drive Essentials quiz and get your personalized energy and drive profile."
  - "Final copy and creative can be added later."
  - CTA: "Continue to Tenor"
- Policy trace:
  - Meta landing-page and ad-experience review

#### META-UBP-001 - Hidden-cause and fake-science framing

- Severity: `blocker`
- Status: `failed`
- Message: The ad uses a hidden-cause narrative ('visible sign of what's shifting inside,' 'systems behind your drive start declining,' 'research shows starts around 30') and authority-style support ('Dr. Adam Reese,' survey stats) to explain the problem and sell the solution. That combination can be misleading or sensational if not fully substantiated.
- Key evidence:
  - "It's a visible sign of what's shifting inside."
  - "It's what happens when the systems behind your drive start declining."
  - "research shows starts around 30"
  - "That's why Dr. Adam Reese built Tenor Daily Drive Essentials."
  - "In a survey of 1,203 Tenor customers:"
- Policy trace:
  - Meta Unacceptable Business Practices

#### META-COPY-005 - Negative self-perception / body-shaming hook

- Severity: `high`
- Status: `failed`
- Message: The opening uses insecurity-based body language ('midsection holding on,' 'soft tissue where definition used to be') and frames the product as a fix for a diminished physique/drive. That leans into negative self-perception, which is restricted in health and wellness ads.
- Key evidence:
  - "midsection holding on"
  - "The soft tissue where definition used to be."
  - "Let's talk about something most men quietly notice but never say out loud…"
- Policy trace:
  - Meta Health and Wellness negative self-perception

#### META-COPY-006 - Direct personal body/health targeting

- Severity: `high`
- Status: `failed`
- Message: The copy speaks as if it knows the viewer has a specific body and energy state ('Noticed your midsection holding on,' 'you feel drained by 3 p.m.,' 'your drive isn't what it used to be'), and it adds an age-based claim ('research shows starts around 30'). That is direct personal-attribute targeting rather than general product language.
- Key evidence:
  - "Noticed your midsection holding on — no matter what you do?"
  - "And that same shift is why you feel drained by 3 p.m."
  - "Why your drive isn't what it used to be."
  - "research shows starts around 30"
- Policy trace:
  - Meta Privacy Violations and Personal Attributes
