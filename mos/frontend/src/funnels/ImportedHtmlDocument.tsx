import { useEffect, useMemo, useState } from "react";

const IMPORTED_HTML_HEIGHT_MESSAGE = "mos:imported-html-document:height";
const DEFAULT_MIN_HEIGHT = 900;
const MAX_FRAME_HEIGHT = 20000;

function injectResizeScript(htmlDocument: string, frameId: string): string {
  const resizeScript = `
<script>
(function() {
  var FRAME_ID = ${JSON.stringify(frameId)};
  var TYPE = ${JSON.stringify(IMPORTED_HTML_HEIGHT_MESSAGE)};
  function measure() {
    var body = document.body;
    var doc = document.documentElement;
    var height = Math.max(
      body ? body.scrollHeight : 0,
      body ? body.offsetHeight : 0,
      doc ? doc.scrollHeight : 0,
      doc ? doc.offsetHeight : 0
    );
    parent.postMessage({ type: TYPE, frameId: FRAME_ID, height: height }, "*");
  }
  window.addEventListener("load", function() {
    measure();
    setTimeout(measure, 50);
    setTimeout(measure, 250);
    setTimeout(measure, 1000);
  });
  window.addEventListener("resize", measure);
  if (typeof ResizeObserver === "function") {
    var observer = new ResizeObserver(measure);
    if (document.documentElement) observer.observe(document.documentElement);
    if (document.body) observer.observe(document.body);
  }
})();
</script>`;

  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${resizeScript}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${resizeScript}</html>`);
  }
  return `${htmlDocument}${resizeScript}`;
}

export function ImportedHtmlDocument({
  id,
  title,
  htmlDocument,
}: {
  id?: string;
  title?: string;
  htmlDocument?: string;
}) {
  const [height, setHeight] = useState(DEFAULT_MIN_HEIGHT);
  const frameId = id || "imported-html-document";

  const srcDoc = useMemo(() => {
    const normalizedHtml = typeof htmlDocument === "string" ? htmlDocument.trim() : "";
    if (!normalizedHtml) return "";
    return injectResizeScript(normalizedHtml, frameId);
  }, [frameId, htmlDocument]);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      const data = event.data;
      if (!data || typeof data !== "object") return;
      if (data.type !== IMPORTED_HTML_HEIGHT_MESSAGE) return;
      if (data.frameId !== frameId) return;
      const nextHeight = Number(data.height);
      if (!Number.isFinite(nextHeight) || nextHeight <= 0) return;
      setHeight(Math.max(DEFAULT_MIN_HEIGHT, Math.min(MAX_FRAME_HEIGHT, Math.ceil(nextHeight))));
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [frameId]);

  if (!srcDoc) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface-2 p-6 text-sm text-content-muted">
        Imported HTML is empty.
      </div>
    );
  }

  return (
    <div className="w-full overflow-hidden">
      <iframe
        title={title || "Imported HTML document"}
        srcDoc={srcDoc}
        sandbox="allow-scripts allow-forms allow-popups allow-modals allow-downloads"
        className="block w-full border-0 bg-transparent"
        style={{ height }}
      />
    </div>
  );
}
