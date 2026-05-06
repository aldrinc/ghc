// Generate the 8 missing Ember presales images (mechanism diagrams + warehouse + seal)
// using gemini-3-pro-image-preview. Writes outputs under
// /Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated/
//
// Prompts follow frankie-pages Image Slot Directive
//   [Subject | Scene/Setting | Style | Mood | Composition | Key Details]
// and EMBER strategy (Brain Fuel Deficit mechanism, women 42-58, clean editorial tone).

import path from 'node:path';
import fs from 'node:fs/promises';
import dotenv from 'dotenv';
import { createNanoBananaClient, generateNanoImage } from '../src/lib/nano-banana.mjs';

dotenv.config({ path: path.resolve(process.cwd(), '..', '.env') });

const OUT_DIR = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/assets/generated';
const MODEL = 'gemini-3-pro-image-preview'; // "pro" per user request

await fs.mkdir(OUT_DIR, { recursive: true });

/** @type {Array<{id: string, slot: string, aspectRatio: string, prompt: string}>} */
const JOBS = [
  {
    id: '11-brain-fueled-vs-depleted',
    slot: 'Line 220 — fully-fueled vs depleted ATP brain',
    aspectRatio: '16:9',
    prompt: [
      'A clean side-by-side comparison illustration of a human brain.',
      'On the LEFT: a vibrant, fully-fueled brain glowing with healthy neural activity, warm amber highlights along active synapses, clear sparking connections, radiating energy.',
      'On the RIGHT: the same brain silhouette but dim, starved, and underpowered — muted cool palette, faded synapses, sluggish connections, a subtle grey veil suggesting brain fog.',
      'Scene: editorial medical illustration on a clean soft-cream backdrop (#FFFAF4), no laboratory equipment, no people.',
      'Style: modern clinical infographic, flat-shaded scientific illustration with subtle gradient depth, Ember brand-adjacent amber (#C41423 red used only as energy accent, not flood color).',
      'Mood: informative, credible, not alarmist. Evokes the "fuel deficit" framing without being cartoonish.',
      'Composition: 16:9 landscape, both brains centered with generous negative space around them, no dividing label strip.',
      'Key details: biologically plausible lobes and gyri; the ATP energy currency implied via small glowing dots traveling along neural paths on the left side only.',
      'CRITICAL: no text, no numbers, no captions, no watermarks, no labels, no arrows, no UI elements. The image must be purely visual — all labels will be added in HTML.',
    ].join(' '),
  },
  {
    id: '14-atp-creatine-recharge',
    slot: 'Line 245 — ATP molecules recharged by creatine inside a neuron',
    aspectRatio: '16:9',
    prompt: [
      'A photorealistic 3D medical molecular render showing ATP regeneration inside a human neuron.',
      'Scene: extreme close-up inside a single firing neuron. Visible mitochondria in soft focus in the background. Glowing ATP molecules are being recharged by creatine phosphate — depicted as energy transfer pulses.',
      'Style: premium pharma/biotech visualization, soft cinematic depth of field, warm amber energy highlights on a cool blue cellular background (teal/navy). Subtle volumetric lighting.',
      'Mood: quiet scientific wonder, restorative, hopeful — the exact opposite of "decline".',
      'Composition: 16:9 landscape. Central cluster of 3-5 molecules mid-transfer. Shallow DOF. Soft vignette.',
      'Key details: biologically plausible molecule geometry (round clusters, not stick diagrams). Energy transfer shown as warm amber sparks / ember-like particles. No people, no equipment.',
      'CRITICAL: absolutely no on-image text, chemical formulas, atom labels, letter overlays, molecule names, or legend. Purely visual render.',
    ].join(' '),
  },
  {
    id: '15-depleted-neurons',
    slot: 'Line 255 — neurons struggling to fire from depleted creatine',
    aspectRatio: '16:9',
    prompt: [
      'A photorealistic 3D biomedical render of a single human neuron struggling to fire.',
      'Scene: microscopic close-up of a neuron in the brain. Synapses are barely sparking; signals stutter and fade mid-transmission. A few weak amber sparks but most connections are dim grey.',
      'Style: premium cinematic scientific render, matched aesthetic to the ATP-recharge image — cool blue/teal cellular environment, same depth of field and color palette. Ember-red used only sparingly for failed sparks.',
      'Mood: quietly grim, "running on empty", but not apocalyptic — this is depletion, not death.',
      'Composition: 16:9 landscape, the struggling synapse centered, surrounding mitochondria visibly drained/faded.',
      'Key details: soft cotton-wool haze at the edges suggesting brain fog. A few neurons just out of focus in the background completely dark.',
      'CRITICAL: no text, no labels, no diagrams, no arrows, no watermarks. Pure visual. Match the aesthetic of the ATP recharge image as a visual pair.',
    ].join(' '),
  },
  {
    id: '16-fuel-gauge-metaphor',
    slot: 'Line 265 — fuel gauge on empty, brain fuel metaphor',
    aspectRatio: '16:9',
    prompt: [
      'A conceptual editorial illustration blending a human brain silhouette with a classic analog automotive fuel gauge.',
      'Scene: a translucent human brain in soft amber outline floating on a clean warm-cream backdrop (#FFFAF4). An analog fuel gauge is embedded in the lower hemisphere of the brain, its needle pointing deep into the red E zone on the left.',
      'Style: modern editorial metaphor illustration, flat-shaded with subtle depth — similar to New York Times or WSJ feature graphics. Ember brand red (#C41423) used for the empty warning zone only.',
      'Mood: understated alarm, "the tank is dry" — metaphorical without being corny.',
      'Composition: 16:9 landscape, brain centered, gauge positioned where the base of the brain stem would be, large negative space around for breathing room.',
      'Key details: the gauge bezel is silver/chrome, needle matte black, warning zone crimson. Brain has subtle visible gyri but rendered more as an icon than anatomy.',
      'CRITICAL: no text, no "E" or "F" letters on the gauge, no unit labels, no numbers — the empty position should be shown by needle angle only. No captions, no UI.',
    ].join(' '),
  },
  {
    id: '17-cognitive-fog-stages',
    slot: 'Line 272 — four-stage progression of cognitive fog',
    aspectRatio: '16:9',
    prompt: [
      'A four-panel progression illustration showing the same woman\'s silhouette becoming progressively more obscured by cognitive fog.',
      'Scene: four equal panels in a row. Each panel shows the same profile silhouette of a professional woman in her late 40s. Panel 1: clear, sharp, fully visible features. Panel 2: a thin mist starting to creep across her face. Panel 3: noticeable fog obscuring half her features. Panel 4: heavy cotton-wool haze almost completely obscuring her — only a faint outline visible.',
      'Style: modern editorial illustration, clean flat-shaded silhouettes with soft gradient fog, warm cream background (#FFFAF4). Ember-adjacent amber highlight tones. Matches the brand palette.',
      'Mood: sobering, empathetic, clinical — this is a medical-journal illustration, not a horror image.',
      'Composition: 16:9 landscape, four equally sized vertical panels with thin dividers between them, each containing one silhouette variant.',
      'Key details: the silhouettes face right, profile view. The fog is rendered as soft layered grey/white mist, not smoke or clouds.',
      'CRITICAL: no numbers, no text labels, no panel headings, no captions, no arrows. The progression must read purely through visual density of fog. Stage numbers will be overlaid in HTML.',
    ].join(' '),
  },
  {
    id: '18-creatine-decline-chart',
    slot: 'Line 285 — female creatine levels declining through perimenopause',
    aspectRatio: '16:9',
    prompt: [
      'A clean editorial line chart showing a single curve declining across the perimenopausal years.',
      'Scene: minimalist chart on a clean off-white paper-texture background (#FFFAF4). A single smooth amber/red line (#C41423) starts at a high plateau on the left, begins a gentle curve downward around the midpoint, and drops into a lower plateau on the right. A soft-shaded band near the inflection zone suggests the perimenopause transition window.',
      'Style: premium medical-infographic design reminiscent of Nature or NEJM editorial figures. Thin minimal axis lines in charcoal, subtle grid in pale grey, no chart junk.',
      'Mood: authoritative, data-driven, credible.',
      'Composition: 16:9 landscape, chart takes up most of the frame with generous padding. No chart title space.',
      'Key details: the inflection/drop zone is softly highlighted with a pale amber/tan shaded band vertically.',
      'CRITICAL: no text whatsoever — no axis labels, no numbers, no chart title, no legend, no gridline values, no units, no asterisks. The chart must be purely shape — all labels will be overlaid in HTML. Think of it as the clean visual skeleton of a chart.',
    ].join(' '),
  },
  {
    id: '32-warehouse-low-stock',
    slot: 'Line 390 — warehouse scene with Ember batch running low',
    aspectRatio: '16:9',
    prompt: [
      'A warm editorial photograph of a clean small-batch fulfillment warehouse where stock is visibly running low.',
      'Scene: wooden industrial shelving in a bright high-ceilinged warehouse. Neat rows of white stand-up supplement pouches with bold red accent stripes and "Ember" wordmark visible on the front of each pouch. Several shelf sections have obvious gaps — half-empty rows, a few remaining pouches in others. A wooden rolling ladder visible in the soft-focus background.',
      'Style: premium editorial product-journalism photography, warm natural daylight streaming through tall windows, shallow depth of field, gentle golden hour tones. Matches the aesthetic of WSJ or Kinfolk business features.',
      'Mood: tactile, artisan, small-batch credibility — this is a real, cared-for operation, not a mega-fulfillment center.',
      'Composition: 16:9 landscape, camera at mid-height looking down a shelving aisle in subtle one-point perspective, rule-of-thirds framing.',
      'Key details: pouches are consistent and on-brand — white with red accents, each one clearly Ember. At least 4-5 shelf rows visible with believable low-stock gaps. No workers, no boxes on the floor, no forklift.',
      'CRITICAL: no signage, no labels other than the "Ember" wordmark on the pouches themselves, no price tags, no text overlays, no watermarks.',
    ].join(' '),
  },
  {
    id: '33-direct-from-brand-seal',
    slot: 'Line 401 — official "direct from brand" verification seal',
    aspectRatio: '1:1',
    prompt: [
      'A premium circular brand authentication seal / certification badge design.',
      'Scene: a standalone circular seal, centered on a clean white background. Two concentric rings in Ember brand red (#C41423) with a ribbed/serrated outer edge like a USP or FDA approval seal. In the center ring: space intentionally reserved for the "Ember" wordmark (will be overlaid in HTML, leave as neutral cream-colored inner circle).',
      'Style: corporate pharma / wellness authority aesthetic, flat vector illustration with subtle shadow beneath the seal for lift. Reminiscent of the USP Verified mark or the B Corp certification badge.',
      'Mood: trusted, official, verified, non-negotiable authenticity.',
      'Composition: 1:1 square. Seal centered, occupying ~80% of frame. Generous white background padding.',
      'Key details: outer ring has small starburst tick marks or a subtle guilloché pattern. Inner ring can contain a small checkmark icon at the bottom OR a subtle laurel flourish. Red accent only, no other colors.',
      'CRITICAL: no text, no letters, no numbers, no "Certified" or "Verified" or "Official" wording. A fully visual seal that reads as official at a glance. The Ember wordmark will be placed in the center via HTML/CSS later.',
    ].join(' '),
  },
];

const client = createNanoBananaClient();

console.log(`Model: ${MODEL}`);
console.log(`Output dir: ${OUT_DIR}`);
console.log(`Jobs: ${JOBS.length}\n`);

const results = [];
for (const job of JOBS) {
  const outFile = path.join(OUT_DIR, `${job.id}.png`);
  const alreadyExists = await fs.access(outFile).then(() => true).catch(() => false);
  if (alreadyExists) {
    console.log(`↻  skip (exists): ${job.id}`);
    results.push({ id: job.id, slot: job.slot, status: 'skipped', path: outFile });
    continue;
  }
  const started = Date.now();
  console.log(`→  generating ${job.id}  [${job.aspectRatio}] — ${job.slot}`);
  try {
    const buffer = await generateNanoImage({
      client,
      model: MODEL,
      prompt: job.prompt,
      imageConfig: { aspectRatio: job.aspectRatio },
    });
    await fs.writeFile(outFile, buffer);
    const secs = ((Date.now() - started) / 1000).toFixed(1);
    console.log(`✓  ${job.id}  ${buffer.length} bytes  ${secs}s`);
    results.push({ id: job.id, slot: job.slot, status: 'ok', path: outFile, bytes: buffer.length });
  } catch (err) {
    console.error(`✗  ${job.id}  FAILED — ${err.message}`);
    results.push({ id: job.id, slot: job.slot, status: 'error', error: err.message });
  }
}

console.log('\n--- summary ---');
for (const r of results) {
  console.log(`${r.status.padEnd(7)}  ${r.id}`);
}
