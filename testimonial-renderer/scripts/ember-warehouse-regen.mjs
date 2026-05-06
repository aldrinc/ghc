// Regenerate warehouse-low-stock using the actual Ember product image as a
// visual reference so the AI reproduces the real pouch design.
import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const REF = '/Users/auggieclement/Documents/GitHub/ghc/testimonial-renderer/samples/assets/ember/ember-product.jpg';
const OUT = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated/32-warehouse-low-stock.png';
const MODEL = 'gemini-3-pro-image-preview';

const prompt = [
  'A warm editorial photograph of a clean small-batch fulfillment warehouse where stock is visibly running low.',
  'Scene: wooden industrial shelving in a bright high-ceilinged warehouse, soft natural daylight streaming through tall windows.',
  'Key detail — the pouches must match the REFERENCE IMAGE exactly: the Ember Brain Clarity Protocol stand-up pouch. White pouch body, red serif "Ember" wordmark near the top, red bold "BRAIN CLARITY PROTOCOL" text below the wordmark, small red accent droplet-logo. Do NOT invent new packaging. Do NOT add red stripes. Do NOT alter the brand layout.',
  'Composition: 21:9 ultrawide landscape, camera at mid-height looking down a shelving aisle in subtle one-point perspective. Neat rows of the reference pouch stacked on the shelves with clear visible gaps — some shelf sections half-empty, some fully stocked, conveying small-batch scarcity. A wooden rolling ladder in soft-focus mid-distance.',
  'Style: premium editorial product-journalism photography, shallow depth of field, warm golden-hour tones, WSJ or Kinfolk feature aesthetic.',
  'Mood: tactile, artisan, small-batch credibility — real cared-for operation, not a mega-fulfillment center.',
  'CRITICAL: no workers or hands visible, no price tags, no shipping labels, no signage, no text overlays, no watermarks. The only text in the image should be the "Ember" and "BRAIN CLARITY PROTOCOL" branding that appears on the reference pouch. At least 5-6 pouches should be clearly legible in frame.',
].join(' ');

console.log(`model: ${MODEL}`);
console.log(`reference: ${REF}`);
const client = createNanoBananaClient();
const started = Date.now();
const buffer = await generateNanoImage({
  client,
  model: MODEL,
  prompt,
  referenceImages: [REF],
  referenceFirst: true,
  imageConfig: { aspectRatio: '21:9' },
});
await fs.writeFile(OUT, buffer);
console.log(`wrote ${OUT} (${buffer.length} bytes, ${((Date.now() - started)/1000).toFixed(1)}s)`);
