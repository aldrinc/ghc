import path from 'path';
import fs from 'fs/promises';
import { loadJsonInput } from './lib/load-input.mjs';
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

const ensureDirectory = async (dirPath) => {
  let stat;
  try {
    stat = await fs.stat(dirPath);
  } catch (error) {
    throw new Error(`Output directory does not exist: ${dirPath}`);
  }
  if (!stat.isDirectory()) {
    throw new Error(`Output path is not a directory: ${dirPath}`);
  }
};

const run = async () => {
  const args = parseArgs(process.argv.slice(2));
  const hasInput = Boolean(args.input);
  const hasBatch = Boolean(args.batch);

  if (hasInput === hasBatch) {
    throw new Error('Provide exactly one of --input or --batch.');
  }

  const renderer = await createRenderer();

  try {
    if (hasInput) {
      if (!args.output) {
        throw new Error('--output is required for single render.');
      }
      const { data, baseDir } = await loadJsonInput(args.input);
      const payload = validatePayload(data, { baseDir });
      const buffer = await renderer.renderToBuffer(payload);
      const outputPath = path.resolve(args.output);
      await writeRenderedImage(buffer, outputPath);
      return;
    }

    if (!args.outdir) {
      throw new Error('--outdir is required for batch render.');
    }
    const outDir = path.resolve(args.outdir);
    await ensureDirectory(outDir);
    const { data, baseDir } = await loadJsonInput(args.batch);
    if (!Array.isArray(data)) {
      throw new Error('Batch input must be a JSON array.');
    }

    for (const [index, item] of data.entries()) {
      if (item == null || typeof item !== 'object' || Array.isArray(item)) {
        throw new Error(`Batch item ${index} must be an object.`);
      }
      const output = item.output;
      if (typeof output !== 'string' || !output.trim()) {
        throw new Error(`Batch item ${index} is missing a valid output filename.`);
      }
      const { output: _ignored, ...payload } = item;
      const validated = validatePayload(payload, { baseDir });
      const buffer = await renderer.renderToBuffer(validated);
      const outputPath = path.resolve(outDir, output);
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
