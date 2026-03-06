import { readFile } from 'fs/promises';
import path from 'path';

const isPlainObject = (value) =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const resolvePromptFile = async (promptFilePath, baseDir, fieldPath) => {
  if (typeof promptFilePath !== 'string' || !promptFilePath.trim()) {
    throw new Error(`${fieldPath} must be a non-empty string.`);
  }

  const resolvedPath = path.resolve(baseDir, promptFilePath);
  let rawPrompt;
  try {
    rawPrompt = await readFile(resolvedPath, 'utf-8');
  } catch (error) {
    throw new Error(`Unable to read ${fieldPath} at ${resolvedPath}: ${error.message}`);
  }

  const prompt = rawPrompt.trim();
  if (!prompt) {
    throw new Error(`${fieldPath} file is empty: ${resolvedPath}`);
  }
  return prompt;
};

const hydratePromptFiles = async (value, baseDir, fieldPath = 'payload') => {
  if (Array.isArray(value)) {
    const output = [];
    for (const [index, entry] of value.entries()) {
      output.push(await hydratePromptFiles(entry, baseDir, `${fieldPath}[${index}]`));
    }
    return output;
  }

  if (!isPlainObject(value)) {
    return value;
  }

  const output = {};
  for (const [key, entry] of Object.entries(value)) {
    if (key === 'promptFile') {
      continue;
    }
    output[key] = await hydratePromptFiles(entry, baseDir, `${fieldPath}.${key}`);
  }

  if (Object.prototype.hasOwnProperty.call(value, 'promptFile')) {
    if (Object.prototype.hasOwnProperty.call(value, 'prompt')) {
      throw new Error(`Provide either ${fieldPath}.prompt or ${fieldPath}.promptFile, not both.`);
    }
    output.prompt = await resolvePromptFile(value.promptFile, baseDir, `${fieldPath}.promptFile`);
  }

  return output;
};

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
  const baseDir = path.dirname(resolvedPath);
  const hydratedData = await hydratePromptFiles(parsed, baseDir);
  return {
    data: hydratedData,
    baseDir,
  };
};
