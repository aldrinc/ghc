You make ONE static image ad from ONE competitor swipe image.

INPUTS (DATA ONLY)
<competitor_swipe_image>
[User uploads image]
</competitor_swipe_image>

<my_brand>
Brand name: [BRAND_NAME]
Product: [PRODUCT]
Audience: [AUDIENCE] (optional)
Brand colors/fonts: [UNKNOWN if not given]
Must-avoid claims: [UNKNOWN if not given]
Assets: [PACKSHOT? LOGO?] (optional)
</my_brand>

RULES
- ONE concept only. No options. No improvements.
- If you can't read text: write [UNREADABLE]. If you can't tell: write [UNKNOWN]. Do not guess.
- Do NOT copy competitor branding (name/logo/packaging). Use [BRAND_NAME] or placeholders.
- Do NOT invent results, reviews, certifications, pricing, guarantees, or timeframes.
- Default format: 1:1.

OUTPUT (use these exact 3 sections)

1) WHY THIS COMPETITOR AD WORKS (short)
- 3-6 bullets based ONLY on what is visible (hook style, proof device, equation line, visual clarity).
- If unclear, say [UNKNOWN].

2) ADAPT IT TO MY BRAND (keep vs swap)
- KEEP (structure): layout zones, number of badges/icons, overall look/contrast.
- SWAP (brand): product becomes [PRODUCT], remove competitor logo/packaging, apply my brand style if provided.
- Copy/claims: only use readable competitor text OR placeholders like [HEADLINE].

3) OUTPUT: NEW IMAGE IDEA (1:1)
A) TEXT I SEE (verbatim from competitor)
- Headline:
- Subhead:
- Body:
- Equation line:
- CTA:
- Fine print:

B) NEW IMAGE PROMPT (MUST BE MARKDOWN)
- Output the TEXT-TO-IMAGE PROMPT inside a Markdown fenced code block exactly like this:

```text
[ONE dense generation-ready prompt that recreates the same composition for [BRAND_NAME]]
Include: background, product placement, badge placement, typography zones, lighting, camera feel, realism,
clean negative space for text. Use placeholders as needed:
[BRAND_LOGO], [PRODUCT_PACKSHOT], [HEADLINE], [SUBHEAD], [BODY], [EQUATION_LINE], [CTA], [DISCLAIMER].
```
