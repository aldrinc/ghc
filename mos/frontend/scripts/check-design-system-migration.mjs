import { readdirSync, readFileSync, statSync } from "node:fs";
import { relative, resolve } from "node:path";

const root = resolve(new URL("..", import.meta.url).pathname);
const targets = [resolve(root, "src"), resolve(root, "tailwind.config.ts")];

const forbidden = [
  { label: "manus namespace", pattern: /\bmanus\b/i },
  { label: "source demo CSS token", pattern: /--moz-/i },
  { label: "source demo camel token", pattern: /mozBlue/i },
  { label: "source demo kebab token", pattern: /moz-blue/i },
];

const allowedLinePatterns = [
  /-moz-osx-font-smoothing/,
];

const allowedPathPatterns = [
  /(^|\/)funnels\/templates\//,
];

function walk(path) {
  const stat = statSync(path);
  if (stat.isDirectory()) {
    return readdirSync(path).flatMap((entry) => walk(resolve(path, entry)));
  }
  if (!/\.(css|mjs|ts|tsx)$/.test(path)) return [];
  return [path];
}

const files = targets.flatMap((target) => walk(target));
const failures = [];

for (const file of files) {
  const rel = relative(root, file);
  if (allowedPathPatterns.some((pattern) => pattern.test(rel))) continue;
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  lines.forEach((line, index) => {
    if (allowedLinePatterns.some((pattern) => pattern.test(line))) return;
    for (const rule of forbidden) {
      if (rule.pattern.test(line)) {
        failures.push(`${rel}:${index + 1}: ${rule.label}: ${line.trim()}`);
      }
    }
  });
}

if (failures.length) {
  console.error("Forbidden borrowed design-system names found:");
  for (const failure of failures) console.error(failure);
  process.exit(1);
}

console.log("Design-system name scan passed.");
