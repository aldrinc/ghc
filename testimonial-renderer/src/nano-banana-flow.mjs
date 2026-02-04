import fs from 'node:fs/promises';
import path from 'node:path';
import dotenv from 'dotenv';
import { loadJsonInput } from './lib/load-input.mjs';
import { createNanoBananaClient, generateNanoImage } from './lib/nano-banana.mjs';
import { validatePayload } from './lib/validate.mjs';
import { createRenderer, writeRenderedImage } from './lib/renderer.mjs';

const parseArgs = (argv) => {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith('--')) {
      throw new Error(`Unexpected argument: ${key}`);
    }
    const value = argv[i + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`Missing value for ${key}`);
    }
    args[key.slice(2)] = value;
    i += 1;
  }
  return args;
};

const ensureDir = async (dirPath) => {
  await fs.mkdir(dirPath, { recursive: true });
};

const replacePlaceholders = (value, assets) => {
  if (Array.isArray(value)) {
    return value.map((entry) => replacePlaceholders(entry, assets));
  }
  if (value && typeof value === 'object') {
    const output = {};
    for (const [key, entry] of Object.entries(value)) {
      output[key] = replacePlaceholders(entry, assets);
    }
    return output;
  }
  if (typeof value === 'string') {
    const match = value.match(/^\{\{(avatar|content):([a-zA-Z0-9_-]+)\}\}$/);
    if (!match) {
      return value;
    }
    const [, type, id] = match;
    const asset = assets[type]?.[id];
    if (!asset) {
      throw new Error(`Missing generated asset for ${type}:${id}.`);
    }
    return asset;
  }
  return value;
};

const run = async () => {
  const envPath = path.resolve(process.cwd(), '..', '.env');
  dotenv.config({ path: envPath });

  const args = parseArgs(process.argv.slice(2));
  if (!args.input) {
    throw new Error('--input is required.');
  }

  const { data, baseDir } = await loadJsonInput(args.input);
  const { model, outputDir, avatarRequests, contentRequests, renders, render } = data;

  if (!model || typeof model !== 'string') {
    throw new Error('model is required in the input payload.');
  }
  if (!outputDir || typeof outputDir !== 'string') {
    throw new Error('outputDir is required in the input payload.');
  }
  if (render) {
    throw new Error('render is no longer supported. Use renders (array) instead.');
  }
  if (!Array.isArray(renders) || renders.length === 0) {
    throw new Error('renders must be a non-empty array.');
  }

  const resolvedOutputDir = path.resolve(baseDir, outputDir);
  await ensureDir(resolvedOutputDir);

  const client = createNanoBananaClient();
  const assets = { avatar: {}, content: {} };

  const runRequests = async (requests, type) => {
    if (!requests) {
      return;
    }
    if (!Array.isArray(requests)) {
      throw new Error(`${type}Requests must be an array when provided.`);
    }

    for (const request of requests) {
      if (!request || typeof request !== 'object') {
        throw new Error(`${type}Requests entries must be objects.`);
      }
      const { id, prompt, output, referenceImages, referenceFirst, imageConfig } = request;
      if (!id || typeof id !== 'string') {
        throw new Error(`${type}Requests.id is required.`);
      }
      if (assets[type][id]) {
        throw new Error(`${type}Requests.id must be unique: ${id}`);
      }
      if (!prompt || typeof prompt !== 'string') {
        throw new Error(`${type}Requests.prompt is required for ${id}.`);
      }
      if (!output || typeof output !== 'string') {
        throw new Error(`${type}Requests.output is required for ${id}.`);
      }

      const resolvedOutput = path.resolve(resolvedOutputDir, output);
      await ensureDir(path.dirname(resolvedOutput));

      const resolvedRefs = (referenceImages || []).map((ref) => path.resolve(baseDir, ref));
      const buffer = await generateNanoImage({
        client,
        model,
        prompt,
        referenceImages: resolvedRefs,
        referenceFirst: Boolean(referenceFirst),
        imageConfig,
      });

      await fs.writeFile(resolvedOutput, buffer);
      const relativePath = path.relative(baseDir, resolvedOutput);
      assets[type][id] = relativePath;
    }
  };

  await runRequests(avatarRequests, 'avatar');
  await runRequests(contentRequests, 'content');

  const renderer = await createRenderer();
  try {
    for (const [index, renderSpec] of renders.entries()) {
      if (!renderSpec || typeof renderSpec !== 'object') {
        throw new Error(`renders[${index}] must be an object.`);
      }
      if (!renderSpec.output || typeof renderSpec.output !== 'string') {
        throw new Error(`renders[${index}].output is required.`);
      }
      if (!renderSpec.payload || typeof renderSpec.payload !== 'object') {
        throw new Error(`renders[${index}].payload is required.`);
      }

      const mergedPayload = replacePlaceholders(renderSpec.payload, assets);
      const validatedPayload = validatePayload(mergedPayload, { baseDir });
      const buffer = await renderer.renderToBuffer(validatedPayload);
      const outputPath = path.resolve(baseDir, renderSpec.output);
      await writeRenderedImage(buffer, outputPath);
    }
  } finally {
    await renderer.close();
  }
};

run().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
