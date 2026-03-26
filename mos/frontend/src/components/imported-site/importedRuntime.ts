type ImportedRuntimeHeadAssets = {
  scriptSrcs: string[];
  stylesheetHrefs: string[];
  inlineStyles: string[];
  inlineScripts: string[];
  bodyClassName: string;
};

type BuildImportedRuntimeSrcDocParams = {
  frameId: string;
  sectionLabel?: string;
  headAssets?: unknown;
  compiledSource: string;
  reactUmdSource: string;
  reactDomUmdSource: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((entry): entry is string => typeof entry === "string")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeInlineTagContent(value: string): string {
  return value.replace(/<\/(script|style)/gi, "<\\/$1");
}

export function isImportedRuntimeSectionType(type: unknown): type is string {
  return typeof type === "string" && /^Imported[A-Za-z0-9]+Section$/.test(type) && type !== "ImportedRuntimeSection";
}

export function normalizeImportedHeadAssets(value: unknown): ImportedRuntimeHeadAssets {
  const record = isRecord(value) ? value : {};
  const bodyClassName = typeof record.bodyClassName === "string" ? record.bodyClassName.trim() : "";

  return {
    scriptSrcs: normalizeStringArray(record.scriptSrcs),
    stylesheetHrefs: normalizeStringArray(record.stylesheetHrefs),
    inlineStyles: normalizeStringArray(record.inlineStyles),
    inlineScripts: normalizeStringArray(record.inlineScripts),
    bodyClassName,
  };
}

export function normalizeImportedRuntimeSectionTypes(value: unknown): boolean {
  let changed = false;

  const walk = (node: unknown) => {
    if (Array.isArray(node)) {
      for (const entry of node) walk(entry);
      return;
    }

    if (!isRecord(node)) return;

    if (isImportedRuntimeSectionType(node.type) && isRecord(node.props) && typeof node.props.runtimeSource === "string") {
      node.props.originalType = node.type;
      node.type = "ImportedRuntimeSection";
      changed = true;
    }

    for (const key of Object.keys(node)) walk(node[key]);
  };

  walk(value);
  return changed;
}

export function buildImportedRuntimeSrcDoc({
  frameId,
  sectionLabel,
  headAssets,
  compiledSource,
  reactUmdSource,
  reactDomUmdSource,
}: BuildImportedRuntimeSrcDocParams): string {
  const normalizedHeadAssets = normalizeImportedHeadAssets(headAssets);
  const title = escapeHtml(sectionLabel?.trim() || "Imported section");
  const bodyClassName = escapeHtml(normalizedHeadAssets.bodyClassName);
  const compiledRuntime = escapeInlineTagContent(compiledSource);

  const bridgeScript = escapeInlineTagContent(`
(() => {
  const frameId = ${JSON.stringify(frameId)};
  const post = (type, payload = {}) => {
    parent.postMessage({ source: "mos-imported-runtime", frameId, type, ...payload }, "*");
  };

  const reportHeight = () => {
    const body = document.body;
    const root = document.documentElement;
    const height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      root ? root.scrollHeight : 0,
      root ? root.offsetHeight : 0,
      64,
    );
    post("height", { height });
  };

  const reportError = (error) => {
    const message =
      error && typeof error === "object" && "message" in error && typeof error.message === "string"
        ? error.message
        : String(error || "Failed to render imported section.");
    post("error", { message });
  };

  window.__notifyImportedRuntimeHeight = reportHeight;
  window.__reportImportedRuntimeError = reportError;

  window.addEventListener("error", (event) => {
    reportError(event.error || event.message || "Failed to render imported section.");
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason || "Imported section runtime rejected.");
  });

  window.addEventListener("load", () => {
    reportHeight();

    if (typeof ResizeObserver === "function") {
      const observer = new ResizeObserver(() => reportHeight());
      if (document.body) observer.observe(document.body);
      if (document.documentElement) observer.observe(document.documentElement);
    }

    if (typeof MutationObserver === "function" && document.body) {
      const observer = new MutationObserver(() => reportHeight());
      observer.observe(document.body, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  });
})();
  `);

  const stylesheetLinks = normalizedHeadAssets.stylesheetHrefs
    .map((href) => `<link rel="stylesheet" href="${escapeHtml(href)}" />`)
    .join("\n");
  const inlineStyles = normalizedHeadAssets.inlineStyles
    .map((css) => `<style>${escapeInlineTagContent(css)}</style>`)
    .join("\n");
  const externalScripts = normalizedHeadAssets.scriptSrcs
    .map((src) => `<script src="${escapeHtml(src)}"></script>`)
    .join("\n");
  const inlineScripts = normalizedHeadAssets.inlineScripts
    .map((script) => `<script>${escapeInlineTagContent(script)}</script>`)
    .join("\n");

  const runtimeScript = escapeInlineTagContent(`
try {
${compiledRuntime}

  if (typeof ImportedSection !== "function") {
    throw new Error("Imported section runtime did not define ImportedSection.");
  }

  const container = document.getElementById("root");
  if (!container) {
    throw new Error("Imported section root container is missing.");
  }

  const root = ReactDOM.createRoot(container);
  root.render(React.createElement(ImportedSection));

  if (typeof window.__notifyImportedRuntimeHeight === "function") {
    requestAnimationFrame(() => window.__notifyImportedRuntimeHeight());
  }
} catch (error) {
  if (typeof window.__reportImportedRuntimeError === "function") {
    window.__reportImportedRuntimeError(error);
  } else {
    throw error;
  }
}
  `);

  return [
    "<!doctype html>",
    "<html>",
    "<head>",
    '<meta charset="utf-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1" />',
    `<title>${title}</title>`,
    "<style>html,body{margin:0;padding:0;background:transparent;}body{min-height:1px;}#root{width:100%;}</style>",
    stylesheetLinks,
    inlineStyles,
    `<script>${bridgeScript}</script>`,
    externalScripts,
    inlineScripts,
    "</head>",
    `<body${bodyClassName ? ` class="${bodyClassName}"` : ""}>`,
    '<div id="root"></div>',
    `<script>${escapeInlineTagContent(reactUmdSource)}</script>`,
    `<script>${escapeInlineTagContent(reactDomUmdSource)}</script>`,
    `<script>${runtimeScript}</script>`,
    "</body>",
    "</html>",
  ]
    .filter(Boolean)
    .join("\n");
}
