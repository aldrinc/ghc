#!/usr/bin/env node
/**
 * Semantic UI token enforcement (incremental).
 *
 * Goal:
 * - Prevent new usage of hard-coded Tailwind palette utilities in the app UI.
 * - Support gradual cleanup by comparing against a committed baseline.
 *
 * This repo is standardizing on semantic tokens defined in `src/styles/theme.css`
 * and exposed via Tailwind in `tailwind.config.ts`.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const PROJECT_ROOT = process.cwd();
const SRC_DIR = path.join(PROJECT_ROOT, "src");
const BASELINE_PATH = path.join(PROJECT_ROOT, "scripts", "check-semantic-ui.baseline.json");

const SCANNED_EXTS = new Set([".ts", ".tsx", ".js", ".jsx"]);

const FORBIDDEN_PATTERNS = [
  {
    id: "tailwind_dark_variant",
    // We do dark mode via token switching (`data-theme`), not Tailwind `dark:` variants.
    re: /(^|[\s"'`])dark:/g,
    description: "Tailwind `dark:` variants are forbidden; use token switching via `data-theme` instead.",
  },
  {
    id: "tailwind_slate_palette",
    re: /\bslate-\d{2,3}\b/g,
    description: "Hard-coded `slate-*` palette utilities are forbidden; use semantic tokens (e.g. `bg-surface`).",
  },
  {
    id: "tailwind_other_neutral_palettes",
    re: /\b(?:gray|zinc|neutral|stone)-\d{2,3}\b/g,
    description:
      "Hard-coded neutral palette utilities are forbidden; use semantic tokens (e.g. `text-content-muted`).",
  },
  {
    id: "tailwind_status_palettes",
    re: /\b(?:amber|yellow|orange|red|rose|emerald|green|lime)-\d{2,3}\b/g,
    description:
      "Hard-coded status palette utilities are forbidden; use semantic tokens (e.g. `bg-warning/10`, `text-danger`).",
  },
  {
    id: "tailwind_bg_white",
    re: /\bbg-white\b/g,
    description: "Hard-coded `bg-white` is forbidden; use semantic surface tokens (e.g. `bg-surface`).",
  },
  {
    id: "tailwind_ring_offset_white",
    re: /\bring-offset-white\b/g,
    description:
      "Hard-coded `ring-offset-white` is forbidden; use token surfaces for ring offsets (e.g. `ring-offset-surface`).",
  },
];

function usageAndExit(message, exitCode) {
  // eslint-disable-next-line no-console
  console.error(message);
  process.exit(exitCode);
}

function fingerprintPatterns(patterns) {
  return patterns.map((p) => ({ id: p.id, source: p.re.source, flags: p.re.flags }));
}

async function fileExists(p) {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

async function listFilesRecursive(dir) {
  const out = [];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    // Keep the traversal simple and explicit; don't silently skip unknown directories.
    if (entry.name === "node_modules" || entry.name === "dist" || entry.name === "build") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await listFilesRecursive(full)));
      continue;
    }
    if (!entry.isFile()) continue;
    if (SCANNED_EXTS.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

function countAndSampleMatches(content, pattern, maxSamples) {
  const re = new RegExp(pattern.re.source, pattern.re.flags);
  let count = 0;
  const samples = [];
  for (;;) {
    const match = re.exec(content);
    if (!match) break;
    count += 1;
    if (samples.length < maxSamples) {
      // Prefer the actual "token" part for reporting, not the preceding delimiter group.
      const raw = match[0];
      samples.push({ index: match.index, match: raw.trim() });
    }
    // Guard against zero-length matches causing infinite loops.
    if (re.lastIndex === match.index) re.lastIndex += 1;
  }
  return { count, samples };
}

function indexToLineAndText(content, index) {
  const lines = content.split("\n");
  let acc = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const nextAcc = acc + lines[i].length + 1; // + "\n"
    if (index < nextAcc) {
      return { line: i + 1, text: lines[i] };
    }
    acc = nextAcc;
  }
  return { line: lines.length, text: lines[lines.length - 1] ?? "" };
}

async function computeViolations() {
  if (!(await fileExists(SRC_DIR))) {
    usageAndExit(`Semantic UI check misconfigured: missing directory ${JSON.stringify(SRC_DIR)}.`, 2);
  }

  const files = await listFilesRecursive(SRC_DIR);
  files.sort();

  const byFile = {};

  for (const absPath of files) {
    const relPath = path.relative(PROJECT_ROOT, absPath).replaceAll(path.sep, "/");
    const content = await fs.readFile(absPath, "utf8");

    const counts = {};
    const samples = {};

    for (const pattern of FORBIDDEN_PATTERNS) {
      const { count, samples: matchSamples } = countAndSampleMatches(content, pattern, 5);
      if (count > 0) {
        counts[pattern.id] = count;
        samples[pattern.id] = matchSamples.map((s) => {
          const loc = indexToLineAndText(content, s.index);
          return { line: loc.line, match: s.match, text: loc.text.trim() };
        });
      }
    }

    if (Object.keys(counts).length) {
      byFile[relPath] = { counts, samples };
    }
  }

  return byFile;
}

async function readBaseline() {
  if (!(await fileExists(BASELINE_PATH))) {
    usageAndExit(
      `Semantic UI check baseline missing at ${JSON.stringify(path.relative(PROJECT_ROOT, BASELINE_PATH))}.`,
      2
    );
  }
  const raw = await fs.readFile(BASELINE_PATH, "utf8");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    usageAndExit(`Baseline JSON is invalid: ${String(err)}.`, 2);
  }

  if (!parsed || typeof parsed !== "object") {
    usageAndExit("Baseline JSON is invalid: expected an object.", 2);
  }

  const expectedPatterns = fingerprintPatterns(FORBIDDEN_PATTERNS);
  const baselinePatterns = parsed?.meta?.patterns;
  if (JSON.stringify(baselinePatterns) !== JSON.stringify(expectedPatterns)) {
    usageAndExit(
      [
        "Semantic UI check baseline is out of date (pattern set changed).",
        `- Baseline: ${JSON.stringify(baselinePatterns)}`,
        `- Expected: ${JSON.stringify(expectedPatterns)}`,
        `Update ${path.relative(PROJECT_ROOT, BASELINE_PATH)} to match the current patterns.`,
      ].join("\n"),
      2
    );
  }

  const baseline = parsed?.baseline;
  if (!baseline || typeof baseline !== "object") {
    usageAndExit("Baseline JSON is invalid: missing `baseline` object.", 2);
  }

  return baseline;
}

async function writeBaseline(current) {
  const payload = {
    meta: {
      generatedAt: new Date().toISOString(),
      patterns: fingerprintPatterns(FORBIDDEN_PATTERNS),
      scannedRoot: "src",
    },
    baseline: Object.fromEntries(
      Object.entries(current).map(([file, data]) => [file, data.counts])
    ),
  };

  await fs.mkdir(path.dirname(BASELINE_PATH), { recursive: true });
  await fs.writeFile(BASELINE_PATH, JSON.stringify(payload, null, 2) + "\n", "utf8");
}

function formatCounts(counts) {
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
}

function diffAgainstBaseline(current, baseline) {
  const failures = [];

  const currentFiles = Object.keys(current).sort();
  for (const file of currentFiles) {
    const currentCounts = current[file]?.counts ?? {};
    const baseCounts = baseline[file];

    if (!baseCounts) {
      failures.push({
        type: "new_file",
        file,
        message: `New forbidden palette usage introduced in ${file}: ${formatCounts(currentCounts)}`,
      });
      continue;
    }

    for (const { id } of FORBIDDEN_PATTERNS) {
      const cur = currentCounts[id] ?? 0;
      const base = typeof baseCounts[id] === "number" ? baseCounts[id] : 0;
      if (cur > base) {
        failures.push({
          type: "increased",
          file,
          message: `${file}: ${id} increased (${base} -> ${cur}).`,
        });
      }
    }
  }

  return failures;
}

function formatFailureDetails(current, failures) {
  const lines = [];

  for (const f of failures) {
    lines.push(`- ${f.message}`);

    const fileData = current[f.file];
    if (!fileData?.samples) continue;

    const sampleLines = [];
    for (const [patternId, samples] of Object.entries(fileData.samples)) {
      for (const s of samples) {
        sampleLines.push(`  - ${patternId} @ ${f.file}:${s.line}: ${s.match}  (${s.text})`);
      }
    }
    sampleLines.sort();
    lines.push(...sampleLines.slice(0, 12));
  }

  return lines.join("\n");
}

async function main() {
  const args = new Set(process.argv.slice(2));
  const updateBaseline = args.has("--update-baseline");

  const current = await computeViolations();

  if (updateBaseline) {
    await writeBaseline(current);
    // eslint-disable-next-line no-console
    console.log(`Wrote baseline to ${path.relative(PROJECT_ROOT, BASELINE_PATH)}.`);
    return;
  }

  const baseline = await readBaseline();
  const failures = diffAgainstBaseline(current, baseline);
  if (failures.length) {
    usageAndExit(
      [
        "Semantic UI token check failed.",
        "",
        "This repo standardizes app UI on semantic tokens (no hard-coded Tailwind palettes).",
        `See docs/ui-style-guide.md for rules and migration guidance.`,
        "",
        formatFailureDetails(current, failures),
        "",
        "Fix: replace forbidden classes with semantic equivalents (e.g. `bg-surface`, `text-content-muted`).",
      ].join("\n"),
      1
    );
  }

  // eslint-disable-next-line no-console
  console.log("Semantic UI token check passed.");
}

main().catch((err) => usageAndExit(`Semantic UI token check crashed: ${String(err)}`, 2));
