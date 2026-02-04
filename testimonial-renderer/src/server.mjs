import express from 'express';
import sharp from 'sharp';
import path from 'node:path';
import dotenv from 'dotenv';
import { validatePayload } from './lib/validate.mjs';
import { createRenderer } from './lib/renderer.mjs';
import { createNanoBananaClient, generateNanoImage } from './lib/nano-banana.mjs';

const envPath = path.resolve(process.cwd(), '..', '.env');
dotenv.config({ path: envPath });

const app = express();
app.use(express.json({ limit: '2mb' }));

const renderer = await createRenderer();
let nanoClient = null;

const getNanoClient = () => {
  if (!nanoClient) {
    nanoClient = createNanoBananaClient();
  }
  return nanoClient;
};

const toDataUrl = (buffer, mimeType = 'image/png') =>
  `data:${mimeType};base64,${buffer.toString('base64')}`;

const maybeGenerateReviewCardAssets = async (payload) => {
  if (!payload || payload.template !== 'review_card') {
    return payload;
  }

  const needsAvatar = payload.avatarPrompt && !payload.avatarUrl;
  const needsHero = payload.heroImagePrompt && !payload.heroImageUrl;
  if (!needsAvatar && !needsHero) {
    return payload;
  }

  const model = payload.imageModel || process.env.NANO_BANANA_MODEL;
  if (!model) {
    throw new Error(
      'imageModel is required to generate testimonial images (set NANO_BANANA_MODEL or pass imageModel).',
    );
  }

  const client = getNanoClient();
  const output = { ...payload };

  if (needsAvatar) {
    if (!payload.avatarPrompt || typeof payload.avatarPrompt !== 'string') {
      throw new Error('avatarPrompt is required to generate the reviewer avatar.');
    }
    const avatarBuffer = await generateNanoImage({
      client,
      model,
      prompt: payload.avatarPrompt,
      imageConfig: payload.avatarImageConfig,
    });
    output.avatarUrl = toDataUrl(avatarBuffer);
  }

  if (needsHero) {
    if (!payload.heroImagePrompt || typeof payload.heroImagePrompt !== 'string') {
      throw new Error('heroImagePrompt is required to generate the testimonial hero image.');
    }
    const heroBuffer = await generateNanoImage({
      client,
      model,
      prompt: payload.heroImagePrompt,
      imageConfig: payload.heroImageConfig,
    });
    output.heroImageUrl = toDataUrl(heroBuffer);
  }

  return output;
};

app.post('/render', async (req, res) => {
  try {
    const formatParam = req.query.format;
    if (!formatParam) {
      res.status(400).send('format query parameter is required (png or webp)'); 
      return;
    }
    const format = formatParam.toString().toLowerCase();
    if (format !== 'png' && format !== 'webp') {
      res.status(400).send('format must be png or webp');
      return;
    }
    const hydrated = await maybeGenerateReviewCardAssets(req.body);
    const payload = validatePayload(hydrated, { baseDir: process.cwd() });
    const pngBuffer = await renderer.renderToBuffer(payload);
    if (format === 'webp') {
      const webpBuffer = await sharp(pngBuffer).webp({ quality: 92 }).toBuffer();
      res.set('Content-Type', 'image/webp');
      res.send(webpBuffer);
      return;
    }
    res.set('Content-Type', 'image/png');
    res.send(pngBuffer);
  } catch (error) {
    res.status(400).send(error.message);
  }
});

const port = process.env.PORT || 4545;
app.listen(port, () => {
  console.log(`testimonial-renderer listening on ${port}`);
});
