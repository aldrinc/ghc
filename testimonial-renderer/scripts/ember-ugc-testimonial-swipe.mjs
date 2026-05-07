// Swipe-template testimonial generator for EMBER sales page testimonial carousel.
//
// Modelled on 5 reference UGC composition templates the user provided:
//   Ref 1: blonde 50s, long hair, indoor wooden-wall cabin, friendly close-up grin
//   Ref 2: 40s hijab, beige fabric, plain white wall, thoughtful close smile
//   Ref 3: 50s short brown bob bangs, cream couch, white top, smart tastefully styled home
//   Ref 4: solo woman in cozy kitchen with warm autumn-window light (adapted from couple ref;
//          EMBER avatar is the woman 42-58, so we keep the setting, drop the partner)
//   Ref 5: blonde 40s hair in bun, bright airy modern living room, laughing mid-conversation
//
// All 5 feature the real Ember Brain Clarity Protocol pouch (reference image anchored).
// Ages span 44-56 per frankie-pages Rule 15 (Audience Range Check).
// Model: gemini-3-pro-image-preview per user request.

import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const REF = '/Users/auggieclement/Documents/GitHub/ghc/testimonial-renderer/samples/assets/ember/ember-product.jpg';
const OUT_DIR = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/testimonials';
const MODEL = 'gemini-3-pro-image-preview';

const BRAND_LINE = [
  'The product MUST match the reference image exactly: the Ember Brain Clarity Protocol stand-up pouch.',
  'Clean white pouch, red serif "Ember" wordmark near the top, bold red "BRAIN CLARITY PROTOCOL" text,',
  'small red droplet accent, small dietary-supplement body copy near the bottom.',
  'Do NOT invent alternate packaging, do NOT add stripes or patterns, do NOT alter the brand layout.',
  'The pouch is held face-forward so the brand + protocol name stay clearly legible.',
].join(' ');

const SHARED_STYLE = [
  'Style: authentic iPhone UGC selfie aesthetic — handheld imperfection, natural indoor light,',
  'realistic skin texture with pores and small natural imperfections, mild handheld motion blur,',
  'no studio lighting, no beauty filter, no polished fashion-ad look. Feels like a real customer',
  'photo taken in 10 seconds on a phone.',
  'Mood: warm, relieved, genuine — not triumphant, not stagey. The confidence of someone who',
  'has found something that works.',
  'CRITICAL: no on-image text, no captions, no watermarks, no logos other than the "Ember" and',
  '"BRAIN CLARITY PROTOCOL" branding that exists on the real pouch. No text-overlay card design.',
  'Just the raw UGC photograph.',
].join(' ');

/** @type {Array<{id:string, age:number, aspect:string, composition:string}>} */
const JOBS = [
  {
    id: '01-linda-56-cabin',
    age: 56,
    aspect: '1:1',
    composition: [
      'A close-cropped UGC selfie of a woman aged 56 with long naturally-lightened blonde hair',
      'worn loose and straight, bright warm smile, crinkled laugh lines around her eyes,',
      'wearing a casual olive-green cotton tee, holding the Ember pouch up next to her cheek',
      'at roughly eye level so both her face and the pouch front are clearly visible in frame.',
      'Setting: inside a cozy lake-house-style room with honey-colored knotty pine wood-panel',
      'walls in the background and a white curtained window off to one side letting in warm',
      'afternoon light. Camera slightly above eye level, tight framing.',
    ].join(' '),
  },
  {
    id: '02-amira-47-white-wall',
    age: 47,
    aspect: '1:1',
    composition: [
      'A UGC smartphone photo of a woman aged 47 with warm olive skin wearing a soft cream',
      'beige hijab loosely draped, a subtle pink lip, gentle close-lipped smile. One hand',
      'holds the Ember pouch up at roughly chest-to-shoulder height; her other hand is',
      'relaxed and partly visible near the pouch, gesturing to it naturally.',
      'Setting: plain white wall background, soft natural daylight spilling from off-camera',
      'window (shadow-soft rather than direct). Straight-on angle, roughly bust-up framing.',
    ].join(' '),
  },
  {
    id: '03-patricia-52-couch',
    age: 52,
    aspect: '1:1',
    composition: [
      'A UGC photo of a woman aged 52 with a short chin-length brown bob with wispy bangs,',
      'warm tasteful natural makeup, wearing a fitted white cotton wrap top. She is seated',
      'on a cream upholstered couch with subtle damask texture in a tastefully styled living',
      'room. She holds the Ember pouch forward toward the camera at shoulder height with',
      'one hand, small smart watch on her wrist, simple silver bracelet, soft confident',
      'smile.',
      'Setting: warm indoor daylight from off-camera, neutral beige tones, a hint of a',
      'lamp shade visible in the soft-focus background. Slightly lower camera angle',
      'looking up at her, three-quarter framing.',
    ].join(' '),
  },
  {
    id: '04-denise-44-kitchen',
    age: 44,
    aspect: '1:1',
    composition: [
      'A UGC photo of a woman aged 44 with long dark-brown wavy hair, wearing a soft',
      'taupe ribbed sweater. Bright friendly smile showing teeth, holding the Ember',
      'pouch proudly in front of her with both hands at mid-chest height.',
      'Setting: a bright cozy kitchen with tall leaded-glass windows in the background',
      'showing yellow and amber autumn trees outside, creating a soft warm golden-hour',
      'backdrop. Soft-focus kitchen counter and cabinetry just visible behind her.',
      'Slight 3/4 angle, rule-of-thirds framing with the product dead-centered.',
      'The woman is alone in the frame — solo portrait, no other people.',
    ].join(' '),
  },
  {
    id: '05-maria-49-airy-home',
    age: 49,
    aspect: '1:1',
    composition: [
      'A candid UGC photo of a woman aged 49 with shoulder-length honey-blonde hair',
      'worn up in a messy bun, wearing a casual cropped athleisure top (neutral pattern,',
      'nothing with readable text). Warm open-mouthed laugh, head tilted slightly as if',
      'reacting to someone just out of frame. She holds the Ember pouch raised near her',
      'shoulder with one hand.',
      'Setting: a bright airy modern sunlit living room with a slim console table behind',
      'her, soft pastel sage-green wall, a framed piece of art faintly visible in the',
      'background, a ceiling fan and mirror softly out of focus above her. Mid-morning',
      'daylight. Waist-up framing, slight candid tilt.',
    ].join(' '),
  },
];

await fs.mkdir(OUT_DIR, { recursive: true });
const client = createNanoBananaClient();
console.log(`model: ${MODEL}`);
console.log(`reference product: ${REF}`);
console.log(`output dir: ${OUT_DIR}\n`);

const summary = [];
for (const job of JOBS) {
  const outPath = path.join(OUT_DIR, `ugc-${job.id}.png`);
  const prompt = [
    job.composition,
    BRAND_LINE,
    SHARED_STYLE,
    `Aspect ratio: ${job.aspect}. Subject is a woman aged ${job.age} per the composition above.`,
  ].join(' ');

  const started = Date.now();
  console.log(`→ generating ugc-${job.id} [${job.aspect}]`);
  try {
    const buffer = await generateNanoImage({
      client,
      model: MODEL,
      prompt,
      referenceImages: [REF],
      referenceFirst: true,
      imageConfig: { aspectRatio: job.aspect },
    });
    await fs.writeFile(outPath, buffer);
    const secs = ((Date.now() - started) / 1000).toFixed(1);
    console.log(`✓ ${outPath}  (${buffer.length} bytes, ${secs}s)`);
    summary.push({ id: job.id, status: 'ok', bytes: buffer.length, path: outPath });
  } catch (err) {
    console.error(`✗ ${job.id}  FAILED — ${err.message}`);
    summary.push({ id: job.id, status: 'error', error: err.message });
  }
}

console.log('\n--- summary ---');
for (const r of summary) console.log(`${r.status.padEnd(6)}  ${r.id}`);
