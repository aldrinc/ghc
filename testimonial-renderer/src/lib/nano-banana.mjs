import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GoogleGenAI } from '@google/genai';

const SUPPORTED_MIME = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
};

const SUPPORTED_MIME_TYPES = new Set(Object.values(SUPPORTED_MIME));
const DEFAULT_MAX_REFERENCE_BYTES = 18 * 1024 * 1024;
const DEFAULT_REFERENCE_TIMEOUT_MS = 30_000;

const getMimeType = (filePath) => {
  const ext = path.extname(filePath).toLowerCase();
  const mimeType = SUPPORTED_MIME[ext];
  if (!mimeType) {
    throw new Error(`Unsupported image type for ${filePath}. Use png, jpg, or webp.`);
  }
  return mimeType;
};

const inlineDataPart = (buffer, mimeType, sourceLabel) => {
  if (!SUPPORTED_MIME_TYPES.has(mimeType)) {
    throw new Error(`Unsupported image mime type for ${sourceLabel}: ${mimeType}. Use png, jpg, or webp.`);
  }
  return {
    inlineData: {
      mimeType,
      data: buffer.toString('base64'),
    },
  };
};

const readInlineImage = (filePath) => {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Reference image not found: ${filePath}`);
  }
  const data = fs.readFileSync(filePath);
  return inlineDataPart(data, getMimeType(filePath), filePath);
};

const parseBase64DataUrl = (dataUrl) => {
  const match = dataUrl.match(/^data:([^;]+);base64,(.+)$/);
  if (!match) {
    throw new Error('Only base64-encoded data URLs are supported for reference images.');
  }
  const mimeType = match[1].trim().toLowerCase();
  const data = match[2].trim();
  if (!SUPPORTED_MIME_TYPES.has(mimeType)) {
    throw new Error(`Unsupported data URL mime type: ${mimeType}. Use png, jpg, or webp.`);
  }
  if (!data) {
    throw new Error('Reference image data URL is empty.');
  }
  return { mimeType, data };
};

const downloadBytes = async (url, options) => {
  const { maxBytes, timeoutMs } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, redirect: 'follow' });
    if (!response.ok) {
      throw new Error(`Failed to download reference image (status=${response.status}) from ${url}`);
    }
    const contentType = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
    if (!response.body) {
      throw new Error(`Reference image response body is empty for ${url}`);
    }

    const chunks = [];
    let total = 0;
    for await (const chunk of response.body) {
      const buf = Buffer.from(chunk);
      total += buf.length;
      if (total > maxBytes) {
        throw new Error(`Reference image too large: ${total} bytes (limit ${maxBytes}) from ${url}`);
      }
      chunks.push(buf);
    }
    const buffer = Buffer.concat(chunks);
    if (buffer.length === 0) {
      throw new Error(`Reference image download returned empty bytes from ${url}`);
    }
    return { buffer, contentType };
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error(`Timed out downloading reference image after ${timeoutMs}ms: ${url}`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
};

const resolveReferenceMimeType = (contentType, urlOrPath) => {
  if (contentType && SUPPORTED_MIME_TYPES.has(contentType)) {
    return contentType;
  }
  return getMimeType(urlOrPath);
};

const readInlineImageFromSource = async (source, options) => {
  const { baseDir, maxBytes, timeoutMs } = options;
  if (typeof source !== 'string') {
    throw new Error('referenceImages entries must be strings.');
  }
  const value = source.trim();
  if (!value) {
    throw new Error('referenceImages entries must not be empty.');
  }

  if (value.startsWith('data:')) {
    const { mimeType, data } = parseBase64DataUrl(value);
    const buffer = Buffer.from(data, 'base64');
    if (buffer.length === 0) {
      throw new Error('Reference image data URL decoded to empty bytes.');
    }
    if (buffer.length > maxBytes) {
      throw new Error(`Reference image data URL too large: ${buffer.length} bytes (limit ${maxBytes}).`);
    }
    return { inlineData: { mimeType, data } };
  }

  if (value.startsWith('http://') || value.startsWith('https://')) {
    const { buffer, contentType } = await downloadBytes(value, { maxBytes, timeoutMs });
    let mimeType;
    try {
      const url = new URL(value);
      mimeType = resolveReferenceMimeType(contentType, url.pathname);
    } catch {
      mimeType = resolveReferenceMimeType(contentType, value);
    }
    return inlineDataPart(buffer, mimeType, value);
  }

  if (value.startsWith('file://')) {
    const filePath = fileURLToPath(value);
    return readInlineImage(filePath);
  }

  const resolvedPath = path.resolve(baseDir || process.cwd(), value);
  return readInlineImage(resolvedPath);
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
  baseDir,
  maxReferenceImageBytes = DEFAULT_MAX_REFERENCE_BYTES,
  referenceImageTimeoutMs = DEFAULT_REFERENCE_TIMEOUT_MS,
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

  const referenceParts = await Promise.all(
    referenceImages.map((source) =>
      readInlineImageFromSource(source, {
        baseDir,
        maxBytes: maxReferenceImageBytes,
        timeoutMs: referenceImageTimeoutMs,
      }),
    ),
  );
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
