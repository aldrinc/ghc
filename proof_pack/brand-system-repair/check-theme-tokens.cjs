const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "../..");
const sourceRoots = [
  path.join(root, "mos/frontend/src"),
  path.join(root, "mos/frontend/tailwind.config.ts"),
];

const ignoredMissing = new Set([
  "--radix-dropdown-menu-content-available-height",
  "--radix-dropdown-menu-content-transform-origin",
  "--tw-bg-opacity",
]);

function walk(entry) {
  if (!fs.existsSync(entry)) return [];
  const stat = fs.statSync(entry);
  if (stat.isFile()) return [entry];
  return fs
    .readdirSync(entry, { withFileTypes: true })
    .flatMap((dirent) => walk(path.join(entry, dirent.name)));
}

const files = sourceRoots
  .flatMap(walk)
  .filter((file) => /\.(css|ts|tsx)$/.test(file));

const used = new Set();
const defined = new Set();

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  for (const match of text.matchAll(/var\((--[\w-]+)/g)) used.add(match[1]);
  for (const match of text.matchAll(/(--[\w-]+)\s*:/g)) defined.add(match[1]);
}

const theme = fs.readFileSync(path.join(root, "mos/frontend/src/styles/theme.css"), "utf8");
const hasManus = /manus/i.test(theme);
const missing = [...used]
  .filter((token) => !defined.has(token))
  .filter((token) => !ignoredMissing.has(token))
  .sort();

if (hasManus || missing.length) {
  if (hasManus) console.error("theme.css still contains Manus/manus.");
  if (missing.length) console.error(`Missing CSS variables:\n${missing.join("\n")}`);
  process.exit(1);
}

console.log(`PASS: ${defined.size} variables defined, ${used.size} variables referenced, no copied Manus tokens.`);
