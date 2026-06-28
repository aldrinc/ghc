# Tenor Advertorial No-Product Swipe Image Flow Runbook

## Decision
Use the MOS production swipe-image flow to regenerate the advertorial imagery, but keep the image system compliance-safe:

- No Tenor product.
- No supplement bottle, jar, box, label, supplement facts card, capsules, pills, powders, scoops, sachets, packaging, branded objects, logos, or readable product text.
- Images should be editorial context only, not product creatives.

## Additional Context From This Chat
Use this context to improve prompt quality. It should inform tone, subject matter, and composition, but it should not create product visuals.

Core advertorial narrative:

- The article is about men past 40 whose testosterone labs look normal but who still feel like a different person.
- The emotional frame is not extreme illness. It is the quiet gap between a normal lab report and lived decline: slower mornings, 2 p.m. fog, worse recovery, lower drive, and feeling like the body is not responding the way it used to.
- The central metaphor is: the blood test measured the key, not the lock. Testosterone is the key; androgen receptors are the lock.
- The mechanism is androgen receptor decay: receptor density and binding sensitivity decline with age even when circulating testosterone remains in range.
- The article explains three forces behind receptor decay: chronic cortisol, low-grade inflammation, and nutrient depletion.
- The visual system should feel like a serious health and longevity editorial, not a supplement ad.

Audience context:

- Primary reader: skeptical, lab-literate men in their 40s and 50s who have tried basic lifestyle changes, generic T-boosters, or considered TRT.
- The tone should be grounded, premium, restrained, and evidence-aware.
- Avoid hype, transformation fantasy, gym-bro aesthetics, or aggressive performance imagery.
- The images should support the article like editorial photography in a health publication.

Tenor context that can inform mood but must not appear as product imagery:

- Brand: Tenor.
- Product discussed in copy: Daily Drive Essentials.
- Product facts in the article: two vegan capsules daily, 21 clinically-dosed actives, disclosed active doses, no proprietary blend.
- Ingredient territories discussed: Tongkat Ali, Zinc, Maca, L-Arginine, Panax Ginseng, Eleuthero, Astragalus, minerals, botanicals, cortisol clearance, circulation, receptor upregulation, binding support.
- Proof discussed in copy: 90-day trial of 1,203 men, 94% recommendation signal, third-party testing, cGMP manufacturing, review/purchase volume.
- These facts may inform scene choices such as botanicals, minerals, lab-like surfaces, papers, morning routines, and evidence cues.
- These facts must not become embedded text, charts, labels, badges, logos, or product shots.

## Visual Lessons From Prior Iterations
These constraints came from the image review process in this chat and should be treated as quality requirements:

- Do not use product shots in advertorial imagery. The user explicitly identified product visuals as a compliance layer for this page.
- Do not use any supplement-ad visual language: no bottle, capsules, labels, supplement facts card, packaging, powders, scoops, sachets, or pill piles.
- Do not embed text in generated images. The prior hero failed because it generated text inside the image.
- Keep backgrounds light and neutral. Earlier dark/red-heavy outputs were rejected or corrected.
- Use warm off-white, stone, black/graphite, and muted bronze. Avoid strong red as a dominant background color.
- If the image includes mechanism abstraction, make it feel physical/editorial, not a flat infographic or fake chart.
- Avoid doctors, hospitals, needles, clinics, fake UI, charts, before/after imagery, shirtless gym tropes, and exaggerated transformation scenes.
- Lifestyle images should show realistic men in their 40s or 50s with grounded, understated energy.
- The page already contains the copy and claims. Images should add atmosphere and context, not repeat claims visually.

## Prompt Context Block
Add this block to every MOS `swipeAngle` before the slot-specific direction:

```text
This image is for a Tenor health and longevity advertorial about men over 40 whose testosterone labs can look normal while energy, drive, recovery, and felt-state decline. The article's core metaphor is "the key versus the lock": testosterone is the key, androgen receptors are the lock. The image should support the editorial narrative around receptor sensitivity, cortisol load, inflammation, nutrient depletion, and a grounded morning routine.

The image must feel like premium editorial photography for a serious health publication, not a supplement ad. It should be restrained, warm, evidence-aware, and article-native. Use warm off-white, stone, graphite/black, mineral neutrals, and muted bronze accents. Use natural window light, clean shadows, and calm composition.

Hard compliance constraint: do not show the Tenor product or any supplement product. No bottle, jar, box, label, supplement facts panel, capsules, pills, tablets, powders, scoops, sachets, packaging, branded object, logo, or readable product text. No embedded words, letters, numbers, charts, claim badges, fake certifications, or fake UI. No doctors, hospitals, needles, clinics, shirtless gym tropes, before/after imagery, or exaggerated transformation scenes.
```

## Source Page
Advertorial HTML:

`/Users/aldrinclement/Documents/programming/mos_strategy/.claude/worktrees/peaceful-lovelace/NEWPRODUCT/09-creative-launch/pages/tenor-daily-drive-advertorial-from-md.html`

Current local generated image destination used by the page:

`/Users/aldrinclement/Documents/programming/mos_strategy/.claude/worktrees/peaceful-lovelace/NEWPRODUCT/09-creative-launch/pages/tenor-advertorial-md-source-clone/generated/`

## Required Local Inputs
No-product source images staged into MOS:

`/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/source-no-product/`

Required files:

- `01-hero-normal-labs-source.jpg`
- `02-mechanism-actives-source.jpg`
- `03-product-kit-label-source.jpg`
- `04-lifestyle-recovery-source.jpg`
- `05-two-capsule-protocol-source.jpg`
- `06-volume-signal-source.jpg`

Rerun script:

`/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/run_mos_advertorial_images_no_product.mjs`

Auth file required by the script:

`/Users/aldrinclement/Documents/programming/marketi/.env.mos-test-auth`

Required keys in that file:

- `MOS_TEST_EMAIL`
- `MOS_TEST_PASSWORD`

Do not paste credentials into this runbook or any tracked file.

## Credentials You Need To Provide
To execute this workflow, the runner needs credentials for a MOS user account that can access the Tenor workspace/campaign in production.

Provide these credentials via the local ignored auth file only:

```dotenv
MOS_TEST_EMAIL=your-mos-login-email
MOS_TEST_PASSWORD=your-mos-login-password
```

Expected file path:

`/Users/aldrinclement/Documents/programming/marketi/.env.mos-test-auth`

What these credentials are used for:

- Sign in to Clerk for `https://moshq.app`.
- Retrieve a backend JWT from Clerk.
- Call the MOS production API at `https://api.moshq.app`.
- Stage no-product source images as funnel AI attachments.
- Start `/swipes/generate-image-ad` workflows.
- Poll workflow status.
- Resolve generated asset `public_id`s and download final images locally.

What permissions the MOS account needs:

- Access to the org/workspace containing the Tenor campaign.
- Access to campaign `a5af5e49-1eb8-4fb4-8029-d3d2006114e9`.
- Permission to create/generated image assets.
- Permission to upload funnel AI attachments for the staging funnel/page.

You do not need to provide these for the current script:

- Hetzner token.
- SSH key.
- GitHub token.
- OpenAI API key.
- Gemini API key.
- Direct database credentials.
- Shopify credentials.

If the auth file is missing or stale, the workflow should fail with a clear auth error. Do not commit this file.

## MOS Production Inputs
API base:

`https://api.moshq.app`

Clerk frontend API:

`https://immune-turtle-79.clerk.accounts.dev/v1`

Required auth headers for Clerk:

- `Origin: https://moshq.app`
- `Referer: https://moshq.app/`

Campaign and asset context:

- `campaignId`: `a5af5e49-1eb8-4fb4-8029-d3d2006114e9`
- `clientId`: `70124684-505f-48af-a25c-5f7a79601fa0`
- `productId`: `8b89a76d-069c-41a6-be38-b7e4f4483460`
- `stagingFunnelId`: `be65d76e-ced9-4948-9465-18723c8446fd`
- `stagingPageId`: `ab3102f4-a179-410a-9eb0-66aa3020cafc`

Endpoint used:

`POST /swipes/generate-image-ad`

Attachment staging endpoint:

`POST /funnels/{stagingFunnelId}/pages/{stagingPageId}/ai/attachments`

## Global Creative Requirements
Apply this to every generated image:

```text
Hard compliance constraint: do not show the Tenor product or any supplement product.
No bottle, jar, box, label, supplement facts panel, capsules, pills, powders, scoops, sachets, packaging, branded object, logo, or readable product text.
This image must be editorial context only, not a product visual.

Premium editorial health and longevity photography for men over 40.
Warm off-white, stone, black, graphite, and muted bronze accents.
Natural window light, clean shadows, restrained contrast, article-native composition.
Photorealistic only.
No fake UI, no charts, no doctors, no hospitals, no needles, no shirtless gym tropes, no before/after imagery.
```

Recommended improved global prompt:

```text
This image is for a Tenor health and longevity advertorial about men over 40 whose testosterone labs can look normal while energy, drive, recovery, and felt-state decline. The article's core metaphor is "the key versus the lock": testosterone is the key, androgen receptors are the lock. The image should support the editorial narrative around receptor sensitivity, cortisol load, inflammation, nutrient depletion, and a grounded morning routine.

Hard compliance constraint: do not show the Tenor product or any supplement product. No bottle, jar, box, label, supplement facts panel, capsules, pills, tablets, powders, scoops, sachets, packaging, branded object, logo, or readable product text. This image must be editorial context only, not a product visual.

Premium editorial health and longevity photography for men over 40. Warm off-white, stone, black, graphite, mineral neutrals, and muted bronze accents. Natural window light, clean shadows, restrained contrast, article-native composition. Photorealistic only.

No embedded words, letters, numbers, charts, claim badges, fake certifications, fake UI, doctors, hospitals, needles, clinics, shirtless gym tropes, before/after imagery, or exaggerated transformation scenes.
```

Every MOS payload must include:

```json
{
  "swipeRequiresProductImage": false,
  "swipeContextMode": "minimal",
  "swipeBrandName": "Tenor",
  "swipeProductName": "Daily Drive Essentials",
  "count": 1
}
```

Do not set `model` or `renderModelId` unless explicitly authorized.

## Slot Requirements
| Slot | Source file | Output key | Aspect ratio | Page placement | Required image direction |
|---|---|---|---|---|---|
| 01 | `01-hero-normal-labs-source.jpg` | `01-hero-normal-labs` | `21:9` | Top hero | Quiet lab-report / driveway / morning-light mood. No words, letters, numbers, labels, product, or packaging. |
| 02 | `02-mechanism-actives-source.jpg` | `02-mechanism-actives` | `4:3` | Androgen receptor section | Abstract lock-and-key receptor still life with minerals/botanicals. No product or readable diagram labels. |
| 03 | `03-product-kit-label-source.jpg` | `03-formulation-context` | `4:3` | Restoration protocol section | Formulation workspace with botanicals, minerals, notebook. No supplement objects or packaging. |
| 04 | `04-lifestyle-recovery-source.jpg` | `04-lifestyle-recovery` | `4:3` | 30/60/90 day reports section | Realistic man in early 50s near window after calm morning activity. No product or gym-ad trope. |
| 05 | `05-two-capsule-protocol-source.jpg` | `05-morning-routine` | `4:3` | How men get started section | Morning routine still life: water glass, notebook, keys, stone counter. No capsules or product. |
| 06 | `06-volume-signal-source.jpg` | `06-volume-signal` | `4:3` | Volume signal section | Quality-control workspace, papers, stone objects, process cue. No product, badges, certification logos, or readable claims. |

## Section-Specific Context To Improve Outputs
Use these details to make each image less generic.

### Slot 01: Hero, Normal Labs
Relevant copy:

- A 47-year-old man gets normal testosterone results, around the middle of the range, but still does not feel normal.
- He sits with the disconnect: the number is fine, but the lived experience is not.
- The image should create an editorial opening mood, not an ad.

Better direction:

```text
Wide hero image. Quiet early morning exterior or interior-adjacent scene with a soft, unreadable lab report cue, driveway or window light, and a sense of private reflection. The paper can imply medical results but must not contain readable values or words. No product objects, no text overlay, no headline copy, no pills, no bottle.
```

### Slot 02: Mechanism, The Lock And Key
Relevant copy:

- Testosterone is the key.
- Androgen receptors are the lock.
- After 40, receptor density and binding sensitivity decline.
- The point is reception, not more signal.

Better direction:

```text
Premium physical still life representing the lock-and-key mechanism through abstract sculptural forms, metal rings, stone, light, and shadow. It should feel scientific and editorial, not like a classroom diagram. Include minerals or botanical textures only as context. No labels, no arrows, no molecules with text, no product.
```

### Slot 03: Restoration Protocol / Formulation Context
Relevant copy:

- The formula discussion centers on receptor upregulation, binding amplification, and cortisol clearance.
- Ingredient territories include Tongkat Ali, Zinc, Maca, L-Arginine, Eleuthero, Panax Ginseng, Astragalus, boron, magnesium, botanicals, and minerals.
- The product itself must not be shown.

Better direction:

```text
Editorial formulation workspace with botanicals, roots, mineral stones, a clean notebook with only abstract unreadable marks, warm lab-like surface, and daylight. It should imply scientific formulation and disclosed actives without showing capsules, bottle, label, supplement facts, packaging, or readable ingredient lists.
```

### Slot 04: Lifestyle Recovery
Relevant copy:

- Men report gradual shifts over 30, 60, and 90 days.
- Examples include moving better, steadier energy, recovery, and feeling like themselves again.
- The tone should be realistic, not a dramatic transformation.

Better direction:

```text
Photorealistic lifestyle image of a realistic man in his early 50s near a window after a calm morning workout or weekend activity. Relaxed posture, grounded expression, premium neutral interior, warm light. No gym-ad intensity, no shirtless body, no visible supplement product, no medical cue.
```

### Slot 05: How Men Get Started / Morning Routine
Relevant copy:

- The protocol is presented as straightforward and morning-based.
- The visual should imply routine but cannot show capsules or the product.

Better direction:

```text
Morning routine still life with a water glass, notebook, keys, and warm stone counter. Clean, masculine, organized, and simple. It should suggest a daily protocol without showing the actual protocol object. No capsules, pills, bottle, label, powder, scoop, shaker, packaging, or text.
```

### Slot 06: Volume Signal / Trust Context
Relevant copy:

- The section discusses volume, testing, review footprint, purchases, and operational confidence.
- The visual should communicate rigor without inventing certifications or showing logos.

Better direction:

```text
Premium editorial quality-control workspace with anonymous papers, process materials, stone/mineral objects, and a subtle non-branded checkmark-like cue. No readable text, no certification logo, no badges, no product, no packaging. The mood should be rigor, repeatability, and scale.
```

## Recommended Script Prompt Updates
If rerunning after this update, revise `run_mos_advertorial_images_no_product.mjs` so each `swipeAngle` combines:

1. `Prompt Context Block`
2. The matching `Section-Specific Context`
3. The current slot-specific image direction

Keep these fixed:

- `swipeRequiresProductImage: false`
- `swipeContextMode: "minimal"`
- No `model`
- No `renderModelId`

Do not attach the product image as a source reference for this run. Only attach the no-product source images.

## Execute
From the Marketi repo:

```bash
cd /Users/aldrinclement/Documents/programming/marketi
node /Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/run_mos_advertorial_images_no_product.mjs
```

Expected outputs:

`/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/generated-no-product/`

Expected manifest:

`/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/mos-swipe-generation-manifest-advertorial-images-no-product.json`

Important: the script writes to fixed filenames under `generated-no-product/`. If you need to preserve the prior run, copy that directory before executing.

## Build Review Contact Sheet
After generation completes:

```bash
python3 - <<'PY'
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os

root = Path('/Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29')
gen = root / 'generated-no-product'
paths = sorted(gen.glob('*.jpg'))
font_path = next((p for p in [
    '/System/Library/Fonts/Helvetica.ttc',
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
] if os.path.exists(p)), None)
label_font = ImageFont.truetype(font_path, 26) if font_path else ImageFont.load_default()
small_font = ImageFont.truetype(font_path, 19) if font_path else ImageFont.load_default()
thumb_w, thumb_h, pad, label_h, cols = 430, 320, 28, 58, 2
rows = (len(paths) + 1) // 2
canvas = Image.new('RGB', (pad + cols * (thumb_w + pad), pad + rows * (thumb_h + label_h + pad)), '#f2eee8')
d = ImageDraw.Draw(canvas)
for i, p in enumerate(paths):
    im = Image.open(p).convert('RGB')
    size = im.size
    im.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
    x = pad + (i % cols) * (thumb_w + pad)
    y = pad + (i // cols) * (thumb_h + label_h + pad)
    d.text((x, y), p.stem.replace('-', ' '), font=label_font, fill='#111')
    d.text((x, y + 31), f'{size[0]}x{size[1]}', font=small_font, fill='#555')
    d.rounded_rectangle([x - 2, y + label_h - 2, x + thumb_w + 2, y + label_h + thumb_h + 2], radius=8, fill='#fffdf8', outline='#cfc6b8', width=2)
    canvas.paste(im, (x + (thumb_w - im.width) // 2, y + label_h + (thumb_h - im.height) // 2))
out = gen / 'advertorial-no-product-contact-sheet.jpg'
canvas.save(out, quality=94)
print(out)
PY
```

## QA Checklist
Reject and rerun any slot if it contains:

- Tenor bottle or any bottle/jar.
- Supplement facts card, label, product box, packaging, sachet, scoop, powder, capsule, pill, or tablet.
- Readable product text, logo, certification mark, fake badge, or claim.
- Doctor, hospital, needle, clinic imagery, or medical-treatment visual.
- Shirtless gym trope, before/after body imagery, or exaggerated transformation.
- AI-generated copy embedded in the image, especially in the hero.

Accept only if:

- The image is product-free.
- The image fits the section context.
- The image feels editorial, premium, and article-native.
- The image has the expected aspect ratio.
- The image loads locally in the advertorial page.

## Copy Approved Images Into The Advertorial Folder
After selecting the six approved images:

```bash
rm -f /Users/aldrinclement/Documents/programming/mos_strategy/.claude/worktrees/peaceful-lovelace/NEWPRODUCT/09-creative-launch/pages/tenor-advertorial-md-source-clone/generated/*.jpg

cp /Users/aldrinclement/Documents/programming/marketi/outputs/tenor-advertorial-images-2026-04-29/final-selected-no-product/*.jpg \
  /Users/aldrinclement/Documents/programming/mos_strategy/.claude/worktrees/peaceful-lovelace/NEWPRODUCT/09-creative-launch/pages/tenor-advertorial-md-source-clone/generated/
```

If the selected set differs from the existing `final-selected-no-product/` folder, create/update that folder first.

## Page References
The advertorial HTML should reference:

```html
./tenor-advertorial-md-source-clone/generated/01-hero-normal-labs.jpg
./tenor-advertorial-md-source-clone/generated/02-mechanism-actives.jpg
./tenor-advertorial-md-source-clone/generated/03-formulation-context.jpg
./tenor-advertorial-md-source-clone/generated/04-lifestyle-recovery.jpg
./tenor-advertorial-md-source-clone/generated/05-morning-routine.jpg
./tenor-advertorial-md-source-clone/generated/06-volume-signal.jpg
```

## Local Render Validation
Serve the page locally:

```bash
cd /Users/aldrinclement/Documents/programming/mos_strategy/.claude/worktrees/peaceful-lovelace/NEWPRODUCT/09-creative-launch/pages
python3 -m http.server 8765 --bind 127.0.0.1
```

Open:

`http://127.0.0.1:8765/tenor-daily-drive-advertorial-from-md.html`

Confirm all six images load and that rendered dimensions are non-zero.

Stop the local server after validation.

## Operational Guardrails
- Do not deploy or restart production services from this runbook.
- Do not edit live production state.
- Do not expose public Hetzner URLs.
- Do not commit credentials.
- Do not use model fallbacks or change model settings without explicit authorization.
- If MOS returns token expiration during polling, refresh auth and resume using the existing workflow IDs instead of starting duplicate jobs.
