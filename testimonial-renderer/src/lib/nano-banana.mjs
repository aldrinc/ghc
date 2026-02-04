import fs from 'node:fs';
import path from 'node:path';
import { GoogleGenAI } from '@google/genai';

const SUPPORTED_MIME = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
};

const getMimeType = (filePath) => {
  const ext = path.extname(filePath).toLowerCase();
  const mimeType = SUPPORTED_MIME[ext];
  if (!mimeType) {
    throw new Error(`Unsupported image type for ${filePath}. Use png, jpg, or webp.`);
  }
  return mimeType;
};

const readInlineImage = (filePath) => {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Reference image not found: ${filePath}`);
  }
  const data = fs.readFileSync(filePath);
  return {
    inlineData: {
      mimeType: getMimeType(filePath),
      data: data.toString('base64'),
    },
  };
};

export const createNanoBananaClient = () => {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error('GEMINI_API_KEY is required to use Nano Banana.');
  }
  return new GoogleGenAI({ apiKey });
};

export const generateNanoImage = async ({
  client,
  model,
  prompt,
  referenceImages = [],
  referenceFirst = false,
  imageConfig,
}) => {
  if (!model || typeof model !== 'string') {
    throw new Error('model is required for Nano Banana generation.');
  }
  if (!prompt || typeof prompt !== 'string') {
    throw new Error('prompt is required for Nano Banana generation.');
  }

  if (imageConfig?.imageSize && model !== 'gemini-3-pro-image-preview') {
    throw new Error('imageConfig.imageSize is only supported for gemini-3-pro-image-preview.');
  }

  const referenceParts = referenceImages.map((filePath) => readInlineImage(filePath));
  const promptPart = { text: prompt };
  const contents = referenceFirst
    ? [...referenceParts, promptPart]
    : [promptPart, ...referenceParts];

  const config = { responseModalities: ['TEXT', 'IMAGE'] };
  if (imageConfig) {
    config.imageConfig = imageConfig;
  }

  const response = await client.models.generateContent({
    model,
    contents,
    config,
  });

  const parts = response?.candidates?.[0]?.content?.parts ?? [];
  const imagePart = parts.find((part) => part.inlineData && part.inlineData.data);
  if (!imagePart) {
    throw new Error('Nano Banana did not return an image.');
  }

  return Buffer.from(imagePart.inlineData.data, 'base64');
};
