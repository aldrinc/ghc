import sharp from 'sharp';
import path from 'node:path';
import fs from 'node:fs/promises';

const LOGO = '/Users/auggieclement/Documents/GitHub/ghc/testimonial-renderer/samples/assets/ember/ember-logo.png';
const OUT = '/Users/auggieclement/Documents/GitHub/ghc/.local/deployed-ember-html/public/favicons';

await fs.mkdir(OUT, { recursive: true });

const meta = await sharp(LOGO).metadata();
console.log(`logo: ${meta.width}x${meta.height}`);

// Tight "E" crop: leftmost square region sized just under image height (sharp
// boundary quirk rejects top+height === imageHeight in this version).
const eCropSize = Math.min(meta.height, meta.width) - 1;
const eCrop = await sharp(LOGO)
  .extract({ left: 0, top: 0, width: eCropSize, height: eCropSize })
  .png()
  .toBuffer();

// Pad to 20% margin on transparent bg for breathing room at small sizes
const ePadded = Math.round(eCropSize * 1.25);
const eSquare = await sharp({
  create: {
    width: ePadded,
    height: ePadded,
    channels: 4,
    background: { r: 0, g: 0, b: 0, alpha: 0 },
  },
})
  .composite([{ input: eCrop, gravity: 'center' }])
  .png()
  .toBuffer();

// Write E-only favicons for small sizes
for (const size of [16, 32, 48, 64]) {
  await sharp(eSquare)
    .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(path.join(OUT, `favicon-${size}.png`));
  console.log(`wrote favicon-${size}.png`);
}

// Larger icons: full wordmark on white square with padding (better legibility)
const wordmarkMeta = meta;
const wSide = Math.max(wordmarkMeta.width, wordmarkMeta.height);
const wPadded = Math.round(wSide * 1.15);
const wSquareWhite = await sharp({
  create: {
    width: wPadded,
    height: wPadded,
    channels: 4,
    background: { r: 255, g: 255, b: 255, alpha: 1 },
  },
})
  .composite([{ input: LOGO, gravity: 'center' }])
  .png()
  .toBuffer();

for (const size of [180, 192, 512]) {
  const name =
    size === 180 ? 'apple-touch-icon.png' : `icon-${size}.png`;
  await sharp(wSquareWhite)
    .resize(size, size, { fit: 'cover' })
    .png()
    .toFile(path.join(OUT, name));
  console.log(`wrote ${name}`);
}

// Also produce a 32x32 "classic" favicon.ico-substitute — modern browsers
// accept PNG via <link rel="icon" type="image/png"> so we skip real .ico.
await sharp(eSquare)
  .resize(32, 32, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
  .png()
  .toFile(path.join(OUT, 'favicon.png'));
console.log('wrote favicon.png');

console.log('\nall favicons written to:', OUT);
