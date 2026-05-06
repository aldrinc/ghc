import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const OUT = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated/outcome-words-back.png';
const MODEL = 'gemini-3-pro-image-preview';

// Per frankie-pages Rule 36 + Rule 45: show the outcome state the reader wants to be in.
// Header context: "Ember Has Helped Thousands Of Women Get Their Words, Focus, And Confidence Back"
// Picture must anchor words + focus + confidence in one frame.
const prompt = [
  'A candid editorial documentary photograph of a mid-50s woman mid-sentence in a small professional meeting. She is in the middle of speaking with clear confidence — mouth slightly open forming a word, eye contact engaged with someone off-camera, hands mid-gesture.',
  'Subject: woman approximately 50-55, salt-and-pepper medium-length hair, soft laugh lines, warm skin tone, wearing a cream cashmere sweater or soft knit layered simply — approachable yet senior. She is the visible expert in the room.',
  'Scene: a bright, modern small meeting space — glass walls softly blurred, a natural-wood conference table in the foreground partially visible, a folded laptop and a notebook on the table beside her. Two other professionals (blurred, out-of-focus, listening attentively) visible in the background, confirming she is leading the conversation.',
  'Style: editorial documentary photography in the style of Monocle magazine or the Wall Street Journal — natural window light, shallow depth of field, realistic skin texture, warm but crisp color grading, no studio polish. Feels like a real captured moment, not a corporate stock image.',
  'Mood: quiet confidence, fluency, "she trusts her own brain again." The moment someone is speaking a word they used to search for. Focused, not triumphant.',
  'Composition: 3:2 cinematic landscape. Subject positioned right of center on the rule-of-thirds line. Generous negative space on the left side (clean blurred background) for the eye to rest. Face and engaged hand-gesture both in sharp focus.',
  'Key details: she wears no visible medical or pharma props — no product, no gummy jar, no pill bottles. She wears simple small earrings. Her posture reads as actively listening while speaking — leaning slightly forward.',
  'CRITICAL: absolutely no text, no captions, no watermarks, no logos. No readable documents, no visible brand labels, no phone screens with text. No Ember product in the frame — this is the pure outcome shot, not a product ad. The other people in the background must remain soft-focused and non-distracting.',
].join(' ');

console.log(`model: ${MODEL}`);
console.log(`out: ${OUT}`);
const client = createNanoBananaClient();
const started = Date.now();
const buffer = await generateNanoImage({
  client,
  model: MODEL,
  prompt,
  imageConfig: { aspectRatio: '3:2' },
});
await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, buffer);
console.log(`wrote ${OUT} (${buffer.length} bytes, ${((Date.now() - started) / 1000).toFixed(1)}s)`);
