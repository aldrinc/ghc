import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMaybeB2CRuntime } from "@/components/commerce/b2c";
import {
  buildImportedRuntimeSrcDoc,
  normalizeImportedHeadAssets,
} from "@/components/imported-site/importedRuntime";
import { useImportedRuntimeContext } from "@/components/imported-site/ImportedTemplateBlocks";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { toast } from "@/components/ui/toast";

type ImportedRuntimeSectionProps = {
  id?: string;
  originalType?: string;
  runtimeSource?: string;
  headAssets?: unknown;
  sectionLabel?: string;
  componentName?: string;
  sectionTargetId?: string;
  textOverrides?: Array<Record<string, unknown>>;
  buttonOverrides?: Array<Record<string, unknown>>;
  imageOverrides?: Array<Record<string, unknown>>;
};

type RuntimeFrameAssets = {
  reactUmdSource: string;
  reactDomUmdSource: string;
};

type ImportedRuntimeCommerceActionPayload = {
  action?: unknown;
  selectedOfferTitle?: unknown;
  selectionStrategy?: unknown;
  replaceCart?: unknown;
};

const compiledSourceCache = new Map<string, Promise<string>>();

function readViewportHeightPx(): number {
  if (typeof window === "undefined") return 900;
  const next = window.visualViewport?.height || window.innerHeight || 900;
  return Math.max(1, Math.round(next));
}

function hashString(value: string): string {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}

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

function normalizeComparableLabel(value: unknown): string {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export function ImportedRuntimeSection({
  id,
  originalType,
  runtimeSource,
  headAssets,
  sectionLabel,
  componentName,
  sectionTargetId,
  textOverrides,
  buttonOverrides,
  imageOverrides,
}: ImportedRuntimeSectionProps) {
  const sharedRuntime = useImportedRuntimeContext();
  const funnelRuntime = useFunnelRuntime();
  const b2cRuntime = useMaybeB2CRuntime();
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const commerceActionPendingRef = useRef(false);
  const initialOverridesFrameRevisionRef = useRef<string | null>(null);
  const initialTextOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const initialButtonOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const initialImageOverridesRef = useRef<Array<Record<string, unknown>>>([]);
  const frameId = useMemo(() => `imported-runtime-${id || Math.random().toString(36).slice(2)}`, [id]);
  const [compiledSource, setCompiledSource] = useState<string | null>(null);
  const [frameAssets, setFrameAssets] = useState<RuntimeFrameAssets | null>(null);
  const [height, setHeight] = useState(96);
  const [error, setError] = useState<string | null>(null);
  const [viewportHeightPx, setViewportHeightPx] = useState<number>(readViewportHeightPx);
  const resolvedRuntimeSource = runtimeSource || sharedRuntime.runtimeSource;
  const textOverridesJson = JSON.stringify(textOverrides || []);
  const buttonOverridesJson = JSON.stringify(buttonOverrides || []);
  const imageOverridesJson = JSON.stringify(imageOverrides || []);
  const normalizedHeadAssets = useMemo(
    () => normalizeImportedHeadAssets(headAssets ?? sharedRuntime.headAssets),
    [headAssets, sharedRuntime.headAssets],
  );
  const runtimeRevision = useMemo(
    () =>
      hashString(
        JSON.stringify({
          frameId,
          compiledSource,
          frameAssets,
          normalizedHeadAssets,
          sectionLabel,
          viewportHeightPx,
          componentName,
          sectionTargetId,
        }),
      ),
    [
      compiledSource,
      componentName,
      frameAssets,
      frameId,
      normalizedHeadAssets,
      sectionLabel,
      sectionTargetId,
      viewportHeightPx,
    ],
  );

  if (initialOverridesFrameRevisionRef.current !== runtimeRevision) {
    initialOverridesFrameRevisionRef.current = runtimeRevision;
    initialTextOverridesRef.current = textOverridesJson
      ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>)
      : [];
    initialButtonOverridesRef.current = buttonOverridesJson
      ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>)
      : [];
    initialImageOverridesRef.current = imageOverridesJson
      ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>)
      : [];
  }

  const srcDoc = useMemo(() => {
    if (!compiledSource || !frameAssets) return null;
    return buildImportedRuntimeSrcDoc({
      frameId,
      sectionLabel,
      headAssets: normalizedHeadAssets,
      compiledSource,
      reactUmdSource: frameAssets.reactUmdSource,
      reactDomUmdSource: frameAssets.reactDomUmdSource,
      viewportHeightPx,
      componentName,
      sectionTargetId,
      initialTextOverrides: initialTextOverridesRef.current,
      initialButtonOverrides: initialButtonOverridesRef.current,
      initialImageOverrides: initialImageOverridesRef.current,
    });
  }, [
    compiledSource,
    frameAssets,
    frameId,
    normalizedHeadAssets,
    sectionLabel,
    viewportHeightPx,
    componentName,
    sectionTargetId,
  ]);
  const frameRevision = useMemo(() => (srcDoc ? `${frameId}-${hashString(srcDoc)}` : frameId), [frameId, srcDoc]);
  const overridesRevision = useMemo(
    () => hashString(`${textOverridesJson}|${buttonOverridesJson}|${imageOverridesJson}`),
    [textOverridesJson, buttonOverridesJson, imageOverridesJson],
  );

  const handleCommerceAction = useCallback(
    async (payload: ImportedRuntimeCommerceActionPayload) => {
      if ((payload.action || "") !== "medusa_buy_now") {
        return;
      }
      if (commerceActionPendingRef.current) {
        return;
      }

      const productHandle = (funnelRuntime?.productSlug || "").trim();
      if (!productHandle || productHandle === "preview-product") {
        toast.error("This imported purchase section needs a real Medusa product binding before Buy now can work.");
        return;
      }
      if (!b2cRuntime) {
        toast.error("The Medusa storefront runtime is not available for this imported section.");
        return;
      }

      const selectedOfferTitle = String(payload.selectedOfferTitle || "").trim();
      if (!selectedOfferTitle) {
        const selectionStrategy = String(payload.selectionStrategy || "").trim();
        toast.error(
          selectionStrategy
            ? `Unable to resolve the selected offer for strategy "${selectionStrategy}".`
            : "Unable to resolve the selected offer for this imported purchase section.",
        );
        return;
      }

      commerceActionPendingRef.current = true;
      try {
        const product = await b2cRuntime.loadProductByHandle(productHandle);
        if (!product) {
          throw new Error(`No Medusa product could be loaded for handle "${productHandle}".`);
        }

        const variants = Array.isArray(product.variants) ? product.variants : [];
        const normalizedSelectedOfferTitle = normalizeComparableLabel(selectedOfferTitle);
        const selectedVariant = variants.find((variant) => {
          return normalizeComparableLabel(variant.title) === normalizedSelectedOfferTitle;
        });

        if (!selectedVariant) {
          throw new Error(
            `No Medusa variant title matches the imported offer "${selectedOfferTitle}" on product "${product.title}".`,
          );
        }

        if (payload.replaceCart && Array.isArray(b2cRuntime.cart?.items) && b2cRuntime.cart.items.length > 0) {
          for (const item of b2cRuntime.cart.items) {
            await b2cRuntime.removeCartItem(item.id);
          }
        }

        await b2cRuntime.addToCart(selectedVariant.id, 1);
        b2cRuntime.navigateToCheckout();
      } catch (reason) {
        toast.error(reason instanceof Error ? reason.message : "Failed to start Medusa checkout from the imported section.");
      } finally {
        commerceActionPendingRef.current = false;
      }
    },
    [b2cRuntime, funnelRuntime?.productSlug],
  );

  useEffect(() => {
    let cancelled = false;

    setCompiledSource(null);
    setHeight(96);
    setError(null);

    if (!resolvedRuntimeSource?.trim()) {
      setError("Imported section runtime is missing.");
      return () => {
        cancelled = true;
      };
    }

    compileImportedRuntimeSource(resolvedRuntimeSource)
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
  }, [resolvedRuntimeSource]);

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
    const handleResize = () => setViewportHeightPx(readViewportHeightPx());

    window.addEventListener("resize", handleResize);
    window.visualViewport?.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      window.visualViewport?.removeEventListener("resize", handleResize);
    };
  }, []);

  useEffect(() => {
    const ownerWindow = frameRef.current?.ownerDocument?.defaultView || window;
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
        return;
      }

      if ((payload as { type?: unknown }).type === "commerce-action") {
        void handleCommerceAction(payload as ImportedRuntimeCommerceActionPayload);
      }
    };

    ownerWindow.addEventListener("message", handleMessage);
    return () => ownerWindow.removeEventListener("message", handleMessage);
  }, [frameId, handleCommerceAction, srcDoc]);

  useEffect(() => {
    if (!srcDoc) return;
    const frame = frameRef.current;
    if (!frame) return;

    const requestHeight = () => {
      frame.contentWindow?.postMessage(
        { source: "mos-imported-runtime-host", frameId, type: "request-height" },
        "*",
      );
    };

    requestHeight();
    const timeoutId = window.setTimeout(requestHeight, 100);
    return () => window.clearTimeout(timeoutId);
  }, [frameId, srcDoc]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || !srcDoc) return;

    const payload = {
      source: "mos-imported-runtime-host",
      frameId,
      type: "update-overrides",
      revision: overridesRevision,
      textOverrides: textOverridesJson ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>) : [],
      buttonOverrides: buttonOverridesJson ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>) : [],
      imageOverrides: imageOverridesJson ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>) : [],
    };

    frame.contentWindow?.postMessage(payload, "*");
  }, [frameId, srcDoc, overridesRevision, textOverridesJson, buttonOverridesJson, imageOverridesJson]);

  const resolvedTitle = sectionLabel?.trim() || originalType?.trim() || "Imported section";

  if (error) {
    return <ImportedRuntimeError title={`${resolvedTitle} unavailable`} message={error} />;
  }

  if (!resolvedRuntimeSource?.trim()) {
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
      key={frameRevision}
      ref={frameRef}
      title={resolvedTitle}
      srcDoc={srcDoc}
      sandbox="allow-forms allow-popups allow-scripts"
      className="block w-full overflow-hidden border-0 bg-transparent"
      style={{ height: `${height}px` }}
      onLoad={() => {
        frameRef.current?.contentWindow?.postMessage(
          { source: "mos-imported-runtime-host", frameId, type: "request-height" },
          "*",
        );
        frameRef.current?.contentWindow?.postMessage(
          {
            source: "mos-imported-runtime-host",
            frameId,
            type: "update-overrides",
            revision: overridesRevision,
            textOverrides: textOverridesJson ? (JSON.parse(textOverridesJson) as Array<Record<string, unknown>>) : [],
            buttonOverrides: buttonOverridesJson ? (JSON.parse(buttonOverridesJson) as Array<Record<string, unknown>>) : [],
            imageOverrides: imageOverridesJson ? (JSON.parse(imageOverridesJson) as Array<Record<string, unknown>>) : [],
          },
          "*",
        );
      }}
    />
  );
}
