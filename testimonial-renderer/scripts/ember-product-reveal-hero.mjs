import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const REF = '/Users/auggieclement/Documents/GitHub/ghc/testimonial-renderer/samples/assets/ember/ember-product.jpg';
const OUT = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated/product-reveal-hero.png';
const MODEL = 'gemini-3-pro-image-preview';

// Per frankie-pages:
//   • Rule 35 — no mechanism recap, the image is the decision-to-act, not a science lesson
//   • Rule 29 — post-reveal is experiential/premium, never educational
//   • Rule 34 — image should make the product feel inevitable, the single logical answer
//   • EMBER KB §2 — "clinical expertise softened by personal vulnerability" → premium/clean, not clinical/cold
//
// This is the FIRST full product glamour shot in the article. It must be:
//   • Clean clinical-premium (no lifestyle props, no gummies scattered, no tools)
//   • Photorealistic 3D studio shot
//   • Pouch front-facing, wordmark + protocol name fully legible
//   • Soft warm lighting, Ember palette (cream #FFFAF4, red #C41423 as brand accent)
const prompt = [
  'A premium, high-end studio product photograph of the Ember Brain Clarity Protocol pouch, centered and hero-framed as the single subject of the image.',
  'The pouch design MUST match the reference image exactly: white stand-up pouch, red serif "Ember" wordmark near the top, red bold "BRAIN CLARITY PROTOCOL" text below the wordmark, small red accent droplet mark, minimal body copy near the bottom. Do NOT invent alternate packaging, alternate colors, striping, or new text.',
  'Scene: studio setting with a seamless warm-cream backdrop transitioning to a subtle soft shadow below the pouch. Soft directional light from the upper left. One very faint amber/red glow wrapping the pouch edge to reinforce the "brain fuel" brand feel — subtle, not neon.',
  'Style: luxury pharma/wellness product photography à la Recess, Lemme, or Dr. Barbara Sturm. High detail, 3D-render-quality, crisp focus on the pouch, tactile softness on the pouch material, no dust or imperfections. Cinematic but minimal.',
  'Mood: authoritative, premium, decisive — this is the answer. Clean. Confident. The product IS the hero.',
  'Composition: 3:2 landscape. Pouch positioned slightly left of center to leave clean right-side negative space for readability. Slight 3/4 angle showing the front face and a hint of the right side depth, so the pouch reads as a real physical object, not a flat render. No tilt — upright and grounded.',
  'Key details: the pouch is sealed and pristine (no tears, no open top). No gummies visible outside the pouch. No coffee mug, no book, no desk, no hand, no fruit, no kitchen. Pure studio emptiness around the subject. Subtle warm floor reflection under the base.',
  'CRITICAL: do not add any text beyond what exists on the actual pouch in the reference. No captions, no price tags, no "5g" callouts, no "new", no asterisks, no bullet points, no additional logos. No laboratory glassware, no lab coat, no pills, no capsules, no mortar and pestle. No brain diagrams. No other products. One pouch, premium background. That is the entire image.',
].join(' ');

console.log(`model: ${MODEL}`);
console.log(`reference: ${REF}`);
console.log(`out: ${OUT}`);

await fs.mkdir(path.dirname(OUT), { recursive: true });
const client = createNanoBananaClient();
const started = Date.now();
const buffer = await generateNanoImage({
  client,
  model: MODEL,
  prompt,
  referenceImages: [REF],
  referenceFirst: true,
  imageConfig: { aspectRatio: '3:2' },
});
await fs.writeFile(OUT, buffer);
console.log(`wrote ${OUT} (${buffer.length} bytes, ${((Date.now() - started) / 1000).toFixed(1)}s)`);
