// Regenerate Amira (02) + Patricia (03) with explicit lock on the pouch label
// so both read "BRAIN CLARITY PROTOCOL" (not "CREATINE GUMMIES").
// Same compositions as the original swipe-template run, same model, same reference.
import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const REF = '/Users/auggieclement/Documents/GitHub/ghc/testimonial-renderer/samples/assets/ember/ember-product.jpg';
const OUT_DIR = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/testimonials';
const MODEL = 'gemini-3-pro-image-preview';

const HARD_LABEL_LOCK = [
  'LABEL LOCK — HARD CONSTRAINT: The pouch must show the "Ember" wordmark with the',
  'bold red "BRAIN CLARITY PROTOCOL" text stacked below it on three lines exactly as',
  'in the reference image. The pouch must NOT say "CREATINE GUMMIES", "WORLD\'S FIRST",',
  '"NEWLY RELEASED", or any alternate product name. If in doubt, reproduce only the',
  'text visible in the reference — white pouch, red serif "Ember" wordmark, three-line',
  '"BRAIN CLARITY PROTOCOL" in bold red, small red droplet accent, minimal supplement',
  'body copy below. No other copy. No stripes. No patterns.',
].join(' ');

const SHARED_STYLE = [
  'Style: authentic iPhone UGC selfie aesthetic — handheld imperfection, natural indoor',
  'light, realistic skin texture with pores and small natural imperfections, mild',
  'handheld motion blur, no studio lighting, no beauty filter, no polished fashion-ad',
  'look. Feels like a real customer photo taken in 10 seconds on a phone.',
  'Mood: warm, relieved, genuine. The confidence of someone who has found something',
  'that works.',
  'CRITICAL: no on-image text, no captions, no watermarks, no logos other than the',
  '"Ember" and "BRAIN CLARITY PROTOCOL" branding that exists on the real pouch.',
].join(' ');

const JOBS = [
  {
    id: '02-amira-47-white-wall',
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
];

await fs.mkdir(OUT_DIR, { recursive: true });
const client = createNanoBananaClient();
console.log(`model: ${MODEL}`);

for (const job of JOBS) {
  const outPath = path.join(OUT_DIR, `ugc-${job.id}.png`);
  const prompt = [
    job.composition,
    HARD_LABEL_LOCK,
    SHARED_STYLE,
    `Aspect ratio: ${job.aspect}.`,
  ].join(' ');

  const started = Date.now();
  console.log(`→ regenerating ugc-${job.id}`);
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
  console.log(`✓ ${outPath}  ${buffer.length} bytes  ${secs}s`);
}
