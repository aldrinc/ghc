import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

// load GEMINI_API_KEY from ghc/.env (same pattern the other service entry points use)
dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const OUT_DIR = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/founder';
const OUT = path.join(OUT_DIR, 'dr-langford-portrait.png');

await fs.mkdir(OUT_DIR, { recursive: true });

// Per frankie-pages Image Slot Directive: Subject | Scene | Style | Mood | Composition | Key Details
// Per EMBER KB §2 Founder: hybrid professional-suffering authority, clinical expertise softened by personal vulnerability
const prompt = [
  'An editorial portrait of Dr. Catherine Langford, a 53-year-old neuroendocrinologist who studies perimenopausal brain metabolism.',
  'Setting: her warm home study in Philadelphia. Soft morning light falling from a window to her left. In the slightly out-of-focus background: a wooden bookshelf with medical reference books, a framed diploma or two, a small potted plant. Quiet, lived-in, not a clinic.',
  'Style: cinematic medium-format portrait photography, natural window light, shallow depth of field, rich skin tones, gentle contrast. Not corporate stock. Not a lab-coat brochure photo.',
  'Mood: warm, composed, quietly authoritative, approachable. The kind of doctor who also happens to be a patient.',
  'Composition: shoulders-up framing, subject slightly left of center with soft negative space on the right. Eyes looking directly into the camera. Soft confident half-smile, relaxed posture. 4:5 vertical aspect ratio.',
  'Key details: shoulder-length silver-blonde hair with natural light grey at the temples, subtle laugh lines, minimal makeup, warm ivory cashmere knit layered under an open camel blazer (not a white lab coat). Hands not visible. No visible product. No text overlay. No watermark. Photo-realistic skin texture with small natural imperfections.',
  'Avoid: glossy ad polish, stock photo stiffness, white medical lab coat clichés, stethoscope props, clinical equipment, overly lit beauty lighting, airbrushed skin, text or logos baked into the image.',
].join(' ');

const client = createNanoBananaClient();
const model = process.env.NANO_BANANA_MODEL;
if (!model) throw new Error('NANO_BANANA_MODEL not set in env.');

console.log('generating portrait with model:', model);
const buffer = await generateNanoImage({
  client,
  model,
  prompt,
  imageConfig: { aspectRatio: '4:5' },
});

await fs.writeFile(OUT, buffer);
console.log(`wrote ${OUT} (${buffer.length} bytes)`);
