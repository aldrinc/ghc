import { readFile } from 'fs/promises';
import path from 'path';

export const loadJsonInput = async (inputPath) => {
  if (typeof inputPath !== 'string' || !inputPath.trim()) {
    throw new Error('input path must be provided.');
  }
  const resolvedPath = path.resolve(inputPath);
  const raw = await readFile(resolvedPath, 'utf-8');
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid JSON in ${resolvedPath}: ${error.message}`);
  }
  return {
    data: parsed,
    baseDir: path.dirname(resolvedPath),
  };
};
