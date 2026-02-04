import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import { chromium } from 'playwright';
import { writeFile } from 'fs/promises';
import sharp from 'sharp';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TEMPLATE_PATHS = {
  review_card: path.resolve(__dirname, '../templates/review_card.html'),
  social_comment: path.resolve(__dirname, '../templates/social_comment.html'),
  testimonial_media: path.resolve(__dirname, '../templates/testimonial_media.html'),
};

const resolveTemplateUrl = (template) => {
  const templatePath = TEMPLATE_PATHS[template];
  if (!templatePath) {
    throw new Error(`No template found for ${template}.`);
  }
  return pathToFileURL(templatePath).href;
};

export const createRenderer = async () => {
  const browser = await chromium.launch();

  const renderToBuffer = async (payload) => {
    const page = await browser.newPage({
      viewport: { width: 1400, height: 2000 },
      deviceScaleFactor: 2,
    });

    const templateUrl = resolveTemplateUrl(payload.template);
    await page.goto(templateUrl, { waitUntil: 'load' });
    await page.evaluate((data) => window.setCardData(data), payload);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForLoadState('networkidle');

    const card = page.locator('#card');
    const buffer = await card.screenshot({ type: 'png' });
    await page.close();
    return buffer;
  };

  const close = async () => {
    await browser.close();
  };

  return { renderToBuffer, close };
};

export const writeRenderedImage = async (buffer, outputPath) => {
  const extension = path.extname(outputPath).toLowerCase();
  if (extension === '.png') {
    await writeFile(outputPath, buffer);
    return;
  }
  if (extension === '.webp') {
    await sharp(buffer).webp({ quality: 92 }).toFile(outputPath);
    return;
  }
  throw new Error('Output path must end with .png or .webp');
};
