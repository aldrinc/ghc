const fs = require("fs");
const path = require("path");

const ROOT = "/Users/aldrinclement/Documents/programming/marketi";
const OUT_DIR = path.join(ROOT, "proof_pack/foundational-dsv4-output-review-2026-05-21");
const OUT_HTML = path.join(OUT_DIR, "index.html");

const STEP01 = path.join(ROOT, "proof_pack/deerflow-step01-1to1-2026-05-21");
const STEP0304 = path.join(ROOT, "proof_pack/deerflow-foundational-steps03-04-1to1-2026-05-21");
const GPT_DOCS = path.join(ROOT, ".local/tenor-strategy-run-docs-prod-20260426/docs");

function readText(file) {
  return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
}

function readJson(file) {
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
}

function html(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fileUrl(file) {
  return `file://${file}`;
}

function vscodeUrl(file, line = 1, col = 1) {
  return `vscode://file${file}:${line}:${col}`;
}

function bytes(file) {
  return fs.existsSync(file) ? fs.statSync(file).size : 0;
}

function sourceButtons(file) {
  return `
    <div class="source-actions">
      <a href="${html(vscodeUrl(file))}">Open in VS Code</a>
      <a href="${html(fileUrl(file))}">Open file</a>
      <button type="button" data-copy="${html(file)}">Copy path</button>
    </div>
    <div class="path">${html(file)}</div>
  `;
}

function metric(label, value) {
  return `<div class="metric"><span>${html(label)}</span><strong>${html(value)}</strong></div>`;
}

function outputBlock({ title, file, body, note = "" }) {
  const content = body ?? readText(file);
  return `
    <section class="output-card" data-search="${html(`${title} ${file} ${content.slice(0, 1000)}`.toLowerCase())}">
      <div class="output-head">
        <div>
          <h3>${html(title)}</h3>
          ${note ? `<p>${html(note)}</p>` : ""}
        </div>
        <span class="size">${bytes(file).toLocaleString()} bytes</span>
      </div>
      ${sourceButtons(file)}
      <pre>${html(content)}</pre>
    </section>
  `;
}

function artifactPayload(file) {
  const data = readJson(file);
  return data?.data?.payload || {};
}

const files = {
  dsv4Step01Summary: path.join(STEP01, "outputs/deerflow-dsv4-step01-summary.md"),
  dsv4Step01Content: path.join(STEP01, "outputs/deerflow-dsv4-step01-content.md"),
  dsv4Step01Raw: path.join(STEP01, "outputs/deerflow-dsv4-step01-raw.md"),
  dsv4Step01Meta: path.join(STEP01, "outputs/deerflow-dsv4-step01-run.meta.json"),
  dsv4Step01Validation: path.join(STEP01, "outputs/deerflow-dsv4-step01-validation.json"),
  step01Comparison: path.join(STEP01, "outputs/dsv4-vs-gpt-step01-comparison.md"),
  gptStep01: path.join(GPT_DOCS, "03-v2-02.foundation.01-raw.md"),
  dsv4Step03Raw: path.join(STEP0304, "outputs/dsv4-step03-raw.md"),
  dsv4Step03Summary: path.join(STEP0304, "outputs/dsv4-step03-summary.md"),
  dsv4Step03Content: path.join(STEP0304, "outputs/dsv4-step03-content.md"),
  dsv4Step03Prompt: path.join(STEP0304, "outputs/dsv4-step03-step4-prompt.md"),
  dsv4Step03Meta: path.join(STEP0304, "outputs/dsv4-step03-run.meta.json"),
  gptStep03: path.join(GPT_DOCS, "04-v2-02.foundation.03-raw.md"),
  dsv4Step04Raw: path.join(STEP0304, "runs/dsv4-foundational-03-04-1to1/step-04/raw.md"),
  dsv4Step04Meta: path.join(STEP0304, "runs/dsv4-foundational-03-04-1to1/step-04/run-meta.json"),
  dsv4Step04Events: path.join(STEP0304, "runs/dsv4-foundational-03-04-1to1/step-04/events.jsonl"),
  dsv4Step04ContinuationRaw: path.join(STEP0304, "runs-continuation/dsv4-foundational-03-04-1to1/step-04/raw.md"),
  dsv4Step04ContinuationMeta: path.join(STEP0304, "runs-continuation/dsv4-foundational-03-04-1to1/step-04/run-meta.json"),
  gptStep04: path.join(GPT_DOCS, "05-v2-02.foundation.04-raw.md"),
  validation0304: path.join(STEP0304, "outputs/dsv4-foundational-03-04-validation.json"),
  comparison0304: path.join(STEP0304, "outputs/dsv4-vs-gpt-foundational-03-04-comparison.md"),
  dashboard01: path.join(STEP01, "index.html"),
  dashboard0304: path.join(STEP0304, "index.html"),
};

const step01Meta = readJson(files.dsv4Step01Meta);
const step01Validation = readJson(files.dsv4Step01Validation);
const step0304Validation = readJson(files.validation0304);
const step03Meta = readJson(files.dsv4Step03Meta);
const step04Meta = readJson(files.dsv4Step04Meta);
const continuationMeta = readJson(files.dsv4Step04ContinuationMeta);
const gpt03Payload = artifactPayload(path.join(ROOT, ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5e9d8334-9042-4878-9c38-88770b0f4625.json"));
const gpt04Payload = artifactPayload(path.join(ROOT, ".local/tenor-strategy-run-docs-prod-20260426/artifacts/strategy_v2_step_payload-5992a9b5-3d5c-48b9-a7cd-7869d2946843.json"));

const overviewRows = [
  ["01", "DSV4", step01Validation.pass ? "PASS" : "CHECK", "Competitor research produced full report with citations and scoring.", "$0.0816 prior run total"],
  ["03", "DSV4", "PASS", "Generated a valid Step 04 prompt.", `$${Number(step0304Validation?.costs?.step03?.promo_total_usd || 0).toFixed(4)}`],
  ["04", "DSV4", "FAIL", "Researched with tools, but final answer was only a status sentence. Continuation failed.", `$${Number((step0304Validation?.costs?.step04_failed?.promo_total_usd || 0) + (step0304Validation?.costs?.step04_continuation_failed?.promo_total_usd || 0)).toFixed(4)}`],
  ["06", "Not run", "SKIPPED", "User explicitly scoped to 1-4.", "$0.0000"],
];

const sourceList = [
  ["Step 01 DSV4 Summary", files.dsv4Step01Summary],
  ["Step 01 DSV4 Content", files.dsv4Step01Content],
  ["Step 01 DSV4 Raw", files.dsv4Step01Raw],
  ["Step 01 GPT Reference", files.gptStep01],
  ["Step 01 Comparison", files.step01Comparison],
  ["Step 03 DSV4 Raw", files.dsv4Step03Raw],
  ["Step 03 DSV4 Generated Step 04 Prompt", files.dsv4Step03Prompt],
  ["Step 03 GPT Reference", files.gptStep03],
  ["Step 04 DSV4 Failed Raw", files.dsv4Step04Raw],
  ["Step 04 DSV4 Events", files.dsv4Step04Events],
  ["Step 04 GPT Reference", files.gptStep04],
  ["03/04 Validation JSON", files.validation0304],
  ["03/04 Comparison", files.comparison0304],
  ["Step 01 Proof Dashboard", files.dashboard01],
  ["03/04 Proof Dashboard", files.dashboard0304],
];

const doc = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Foundational Docs DSV4 Output Review</title>
  <style>
    :root {
      --bg: #f7f5ef;
      --ink: #1e2421;
      --muted: #617069;
      --line: #d8d5ca;
      --panel: #ffffff;
      --good: #12715b;
      --warn: #aa6a00;
      --bad: #b83232;
      --accent: #1c5f87;
      --soft: #eaf3ee;
      --code: #101613;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
      letter-spacing: 0;
    }
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(247, 245, 239, 0.95);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }
    .bar {
      max-width: 1480px;
      margin: 0 auto;
      padding: 16px 20px;
      display: grid;
      grid-template-columns: minmax(280px, 1fr) minmax(260px, 420px);
      gap: 16px;
      align-items: center;
    }
    h1 { margin: 0; font-size: 22px; line-height: 1.15; }
    .subtitle { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    #search {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 11px 12px;
      font-size: 14px;
      background: #fff;
      color: var(--ink);
    }
    main {
      max-width: 1480px;
      margin: 0 auto;
      padding: 18px 20px 48px;
    }
    .grid { display: grid; gap: 14px; }
    .top-grid {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 14px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    h2 { margin: 0 0 12px; font-size: 17px; }
    h3 { margin: 0; font-size: 15px; }
    p { margin: 0; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      text-align: left;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 700; }
    .status {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
    }
    .status.pass { color: var(--good); background: #edf8f4; border-color: #b8dccf; }
    .status.fail { color: var(--bad); background: #fff0ee; border-color: #edc0bd; }
    .status.skip, .status.check { color: var(--warn); background: #fff7e8; border-color: #e4c98e; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfbf8;
      min-height: 68px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }
    .metric strong {
      display: block;
      font-size: 19px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    .nav {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0;
    }
    .nav a, .source-actions a, .source-actions button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--accent);
      padding: 7px 10px;
      text-decoration: none;
      font-size: 13px;
      cursor: pointer;
      font-family: inherit;
      min-height: 34px;
    }
    .source-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 6px;
    }
    .path {
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
      margin-bottom: 10px;
    }
    .output-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin: 14px 0;
    }
    .output-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
    }
    .output-head p { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .size { white-space: nowrap; color: var(--muted); font-size: 12px; }
    pre {
      margin: 0;
      max-height: 720px;
      overflow: auto;
      padding: 14px;
      border-radius: 8px;
      background: var(--code);
      color: #e7eee9;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    details {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px 14px;
      margin: 14px 0;
    }
    summary {
      cursor: pointer;
      font-weight: 700;
    }
    .file-list {
      display: grid;
      gap: 10px;
    }
    .file-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .file-row strong { display: block; font-size: 13px; margin-bottom: 2px; }
    .callout {
      background: var(--soft);
      border: 1px solid #bfd9cf;
      border-radius: 8px;
      padding: 12px;
      color: #23463d;
      font-size: 14px;
    }
    .callout.bad {
      background: #fff1ef;
      border-color: #efc1bc;
      color: #7c2929;
    }
    @media (max-width: 920px) {
      .bar, .top-grid { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <div>
        <h1>Foundational Docs DSV4 Output Review</h1>
        <p class="subtitle">Step 01, 03, 04 outputs in one place. Step 06 was not run.</p>
      </div>
      <input id="search" type="search" placeholder="Filter embedded outputs..." />
    </div>
  </header>
  <main>
    <div class="top-grid">
      <section class="panel">
        <h2>Decision View</h2>
        <table>
          <thead><tr><th>Step</th><th>Provider</th><th>Status</th><th>Read</th><th>Cost</th></tr></thead>
          <tbody>
            ${overviewRows.map(([step, provider, status, read, cost]) => `
              <tr>
                <td>${html(step)}</td>
                <td>${html(provider)}</td>
                <td><span class="status ${html(String(status).toLowerCase())}">${html(status)}</span></td>
                <td>${html(read)}</td>
                <td>${html(cost)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Run Metrics</h2>
        <div class="metrics">
          ${metric("Step 01 DSV4 tools", `${JSON.stringify(step01Meta.tool_counts || {})}`)}
          ${metric("Step 03 prompt chars", `${step0304Validation?.step03?.step4_prompt_chars || 0}`)}
          ${metric("Step 04 DSV4 tools", `${JSON.stringify(step04Meta.tool_counts || {})}`)}
          ${metric("03/04 promo cost", `$${Number(step0304Validation?.costs?.total_promo_usd || 0).toFixed(4)}`)}
          ${metric("04 failure raw chars", `${bytes(files.dsv4Step04Raw)}`)}
          ${metric("Continuation tools", `${JSON.stringify(continuationMeta.tool_counts || {})}`)}
        </div>
      </section>
    </div>

    <div class="nav">
      <a href="#step01">Step 01</a>
      <a href="#step03">Step 03</a>
      <a href="#step04">Step 04</a>
      <a href="#gpt">GPT References</a>
      <a href="#files">All Files</a>
    </div>

    <section class="callout">
      <strong>Read this first:</strong> Step 01 looks usable. Step 03 produced a valid Step 04 prompt. Step 04 is not default-ready: DSV4 researched heavily and then failed the final tagged output contract.
    </section>

    <section id="step01">
      <h2>Step 01: Competitor Research</h2>
      ${outputBlock({ title: "DSV4 Step 01 Summary", file: files.dsv4Step01Summary, note: "Bounded summary parsed from DSV4 raw output." })}
      ${outputBlock({ title: "DSV4 Step 01 Full Content", file: files.dsv4Step01Content, note: "Full competitor research output for quality review." })}
      <details>
        <summary>Step 01 Raw + Validation</summary>
        ${outputBlock({ title: "DSV4 Step 01 Raw", file: files.dsv4Step01Raw })}
        ${outputBlock({ title: "Step 01 Validation JSON", file: files.dsv4Step01Validation })}
        ${outputBlock({ title: "Step 01 DSV4 vs GPT Comparison", file: files.step01Comparison })}
      </details>
    </section>

    <section id="step03">
      <h2>Step 03: Deep Research Meta-Prompt</h2>
      ${outputBlock({ title: "DSV4 Step 03 Raw", file: files.dsv4Step03Raw, note: "Contains SUMMARY, STEP4_PROMPT, and CONTENT blocks." })}
      ${outputBlock({ title: "DSV4 Generated Step 04 Prompt", file: files.dsv4Step03Prompt, note: "This is the prompt Step 04 actually consumed." })}
      <details>
        <summary>Step 03 Parsed Summary/Content + Meta</summary>
        ${outputBlock({ title: "DSV4 Step 03 Summary", file: files.dsv4Step03Summary })}
        ${outputBlock({ title: "DSV4 Step 03 Content", file: files.dsv4Step03Content })}
        ${outputBlock({ title: "DSV4 Step 03 Run Meta", file: files.dsv4Step03Meta })}
      </details>
    </section>

    <section id="step04">
      <h2>Step 04: Deep Research Execution</h2>
      <div class="callout bad">
        <strong>Failure mode:</strong> DSV4 made ${html(step0304Validation?.step04?.tool_counts?.web_search || 0)} web_search calls and ${html(step0304Validation?.step04?.tool_counts?.web_fetch || 0)} web_fetch calls, then returned only a status sentence instead of the required report.
      </div>
      ${outputBlock({ title: "DSV4 Step 04 Failed Raw Output", file: files.dsv4Step04Raw, note: "The exact final output from the failed Step 04 run." })}
      ${outputBlock({ title: "DSV4 Step 04 Run Meta", file: files.dsv4Step04Meta })}
      ${outputBlock({ title: "DSV4 Step 04 Continuation Failed Raw", file: files.dsv4Step04ContinuationRaw })}
      ${outputBlock({ title: "DSV4 Step 04 Continuation Meta", file: files.dsv4Step04ContinuationMeta })}
      <details>
        <summary>03/04 Validation + Comparison</summary>
        ${outputBlock({ title: "03/04 Validation JSON", file: files.validation0304 })}
        ${outputBlock({ title: "03/04 DSV4 vs GPT Comparison", file: files.comparison0304 })}
      </details>
    </section>

    <section id="gpt">
      <h2>GPT References</h2>
      ${outputBlock({ title: "GPT Step 01 Reference", file: files.gptStep01, note: "Persisted production GPT Step 01 artifact." })}
      ${outputBlock({ title: "GPT Step 03 Reference", file: files.gptStep03, note: "Persisted production GPT Step 03 artifact." })}
      ${outputBlock({ title: "GPT Step 04 Reference", file: files.gptStep04, note: `Persisted production GPT Step 04 artifact. Artifact payload summary chars: ${String(gpt04Payload.bounded_summary || "").length}; content chars: ${String(gpt04Payload.content || "").length}.` })}
    </section>

    <section id="files" class="panel">
      <h2>All Source Files</h2>
      <div class="file-list">
        ${sourceList.map(([label, file]) => `
          <div class="file-row">
            <strong>${html(label)}</strong>
            ${sourceButtons(file)}
          </div>
        `).join("")}
      </div>
    </section>
  </main>
  <script>
    const input = document.getElementById("search");
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      document.querySelectorAll(".output-card").forEach(card => {
        card.style.display = !q || card.dataset.search.includes(q) ? "" : "none";
      });
    });
    document.querySelectorAll("button[data-copy]").forEach(button => {
      button.addEventListener("click", async () => {
        await navigator.clipboard.writeText(button.dataset.copy);
        const old = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => button.textContent = old, 900);
      });
    });
  </script>
</body>
</html>`;

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(OUT_HTML, doc);
console.log(OUT_HTML);
