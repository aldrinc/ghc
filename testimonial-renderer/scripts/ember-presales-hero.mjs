import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const OUT = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated/presales-hero-podium.png';
const MODEL = 'gemini-3-pro-image-preview';

const prompt = [
  'A cinematic editorial photograph of an empty neurology conference lecture hall moments after a speaker has paused mid-sentence.',
  'Subject: a wooden lectern with a thin microphone arm in sharp focus, the speaker not visible (just-walked-away or mid-pause feel). Soft overhead stage light falls on the lectern.',
  'Scene: tiered dark leather auditorium seating visible in gentle out-of-focus background. A large projection screen behind the lectern shows a softly-blurred scientific slide featuring a brain cross-section diagram and a few lines of illegible scientific text — no readable words.',
  'Style: premium editorial journalism photography (think New Yorker long-form feature), shallow depth of field, warm-to-cool lighting contrast (warm stage glow on lectern against cool blue auditorium shadows). Matches the register of a serious science-magazine feature, not a product ad.',
  'Mood: the silence after a word vanished. Quietly dramatic, narrative, inviting the reader to lean in. Not ominous, not tragic — editorial.',
  'Composition: 21:9 cinematic ultrawide landscape. Lectern positioned center-left on the rule-of-thirds line. Generous negative space on the upper right where headline will overlay (kept clean). Subtle vignette.',
  'Key details: the lectern wood has warmth and texture. The microphone is a thin modern gooseneck, slightly tilted. The projection slide behind is legibly brain-science without being readable as specific text.',
  'CRITICAL: absolutely no people visible, no readable text, no captions, no watermarks, no letters, no numbers, no conference signage. The slide projection should suggest science through geometry and color only. This is the moment after — empty stage, charged atmosphere.',
].join(' ');

console.log(`model: ${MODEL}`);
console.log(`out: ${OUT}`);
const client = createNanoBananaClient();
const start = Date.now();
const buffer = await generateNanoImage({
  client,
  model: MODEL,
  prompt,
  imageConfig: { aspectRatio: '21:9' },
});
await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, buffer);
console.log(`wrote ${OUT} (${buffer.length} bytes, ${((Date.now() - start) / 1000).toFixed(1)}s)`);
