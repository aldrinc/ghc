import { useEffect, useMemo, useState } from "react";
import {
  buildImportedRuntimeSrcDoc,
  normalizeImportedHeadAssets,
} from "@/components/imported-site/importedRuntime";

type ImportedRuntimeSectionProps = {
  id?: string;
  originalType?: string;
  runtimeSource?: string;
  headAssets?: unknown;
  sectionLabel?: string;
};

type RuntimeFrameAssets = {
  reactUmdSource: string;
  reactDomUmdSource: string;
};

const compiledSourceCache = new Map<string, Promise<string>>();

function compileImportedRuntimeSource(runtimeSource: string): Promise<string> {
  const cached = compiledSourceCache.get(runtimeSource);
  if (cached) return cached;

  const next = import("typescript").then((tsModule) => {
    const ts = "default" in tsModule ? tsModule.default : tsModule;
    const output = ts.transpileModule(runtimeSource, {
      compilerOptions: {
        jsx: ts.JsxEmit.React,
        jsxFactory: "React.createElement",
        jsxFragmentFactory: "React.Fragment",
        module: ts.ModuleKind.None,
        target: ts.ScriptTarget.ES2020,
      },
      reportDiagnostics: false,
    }).outputText;

    if (!output.trim()) {
      throw new Error("Imported section runtime compiled to empty output.");
    }

    return output;
  });

  compiledSourceCache.set(runtimeSource, next);
  return next;
}

function ImportedRuntimeError({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-sm text-content">
      <div className="font-semibold text-danger">{title}</div>
      <div className="mt-2 whitespace-pre-wrap text-content">{message}</div>
    </div>
  );
}

export function ImportedRuntimeSection({
  id,
  originalType,
  runtimeSource,
  headAssets,
  sectionLabel,
}: ImportedRuntimeSectionProps) {
  const frameId = useMemo(() => `imported-runtime-${id || Math.random().toString(36).slice(2)}`, [id]);
  const [compiledSource, setCompiledSource] = useState<string | null>(null);
  const [frameAssets, setFrameAssets] = useState<RuntimeFrameAssets | null>(null);
  const [height, setHeight] = useState(96);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    setCompiledSource(null);
    setHeight(96);
    setError(null);

    if (!runtimeSource?.trim()) {
      setError("Imported section runtime is missing.");
      return () => {
        cancelled = true;
      };
    }

    compileImportedRuntimeSource(runtimeSource)
      .then((output) => {
        if (!cancelled) setCompiledSource(output);
      })
      .catch((reason) => {
        if (cancelled) return;
        const message = reason instanceof Error ? reason.message : "Failed to compile imported section runtime.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [runtimeSource]);

  useEffect(() => {
    let cancelled = false;

    import("./importedRuntimeFrameAssets")
      .then((module) => {
        if (!cancelled) setFrameAssets(module.importedRuntimeFrameAssets);
      })
      .catch((reason) => {
        if (cancelled) return;
        const message = reason instanceof Error ? reason.message : "Failed to load imported section runtime assets.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || typeof payload !== "object") return;
      if ((payload as { source?: unknown }).source !== "mos-imported-runtime") return;
      if ((payload as { frameId?: unknown }).frameId !== frameId) return;

      if ((payload as { type?: unknown }).type === "height") {
        const nextHeight = (payload as { height?: unknown }).height;
        if (typeof nextHeight === "number" && Number.isFinite(nextHeight)) {
          setHeight(Math.max(64, Math.ceil(nextHeight)));
        }
      }

      if ((payload as { type?: unknown }).type === "error") {
        const message = (payload as { message?: unknown }).message;
        setError(typeof message === "string" && message.trim() ? message : "Imported section runtime failed.");
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [frameId]);

  const normalizedHeadAssets = useMemo(() => normalizeImportedHeadAssets(headAssets), [headAssets]);
  const srcDoc = useMemo(() => {
    if (!compiledSource || !frameAssets) return null;
    return buildImportedRuntimeSrcDoc({
      frameId,
      sectionLabel,
      headAssets: normalizedHeadAssets,
      compiledSource,
      reactUmdSource: frameAssets.reactUmdSource,
      reactDomUmdSource: frameAssets.reactDomUmdSource,
    });
  }, [compiledSource, frameAssets, frameId, normalizedHeadAssets, sectionLabel]);

  const resolvedTitle = sectionLabel?.trim() || originalType?.trim() || "Imported section";

  if (error) {
    return <ImportedRuntimeError title={`${resolvedTitle} unavailable`} message={error} />;
  }

  if (!runtimeSource?.trim()) {
    return <ImportedRuntimeError title={`${resolvedTitle} unavailable`} message="Imported section runtime is missing." />;
  }

  if (!srcDoc) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4 text-sm text-content-muted">
        Preparing {resolvedTitle.toLowerCase()}...
      </div>
    );
  }

  return (
    <iframe
      title={resolvedTitle}
      srcDoc={srcDoc}
      sandbox="allow-forms allow-popups allow-scripts"
      className="block w-full overflow-hidden border-0 bg-transparent"
      style={{ height: `${height}px` }}
    />
  );
}
