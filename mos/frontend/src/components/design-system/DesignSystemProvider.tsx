import { createContext, useContext, useEffect, useId, useMemo, useRef, type CSSProperties, type ReactNode } from "react";
import type { DesignSystemTokens } from "@/types/designSystems";

function toCssVarName(key: string): string {
  const trimmed = key.trim();
  if (trimmed.startsWith("--")) return trimmed;
  if (trimmed.includes("-")) return `--${trimmed}`;
  return `--${trimmed.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase()}`;
}

function cssVarsToStyle(vars?: Record<string, string | number>): CSSProperties | undefined {
  if (!vars) return undefined;
  const style: Record<string, string> = {};
  for (const [key, value] of Object.entries(vars)) {
    if (value === undefined || value === null) continue;
    style[toCssVarName(key)] = String(value);
  }
  return Object.keys(style).length ? (style as CSSProperties) : undefined;
}

const DesignSystemContext = createContext<DesignSystemTokens | Record<string, unknown> | null>(null);

export function useDesignSystemTokens() {
  return useContext(DesignSystemContext);
}

export function DesignSystemProvider({
  tokens,
  children,
  className,
}: {
  tokens?: DesignSystemTokens | Record<string, unknown> | null;
  children: ReactNode;
  className?: string;
}) {
  const cssVars = (tokens as DesignSystemTokens | null | undefined)?.cssVars;
  const dataTheme = (tokens as DesignSystemTokens | null | undefined)?.dataTheme;
  const fontUrls = (tokens as DesignSystemTokens | null | undefined)?.fontUrls;
  const fontCss = (tokens as DesignSystemTokens | null | undefined)?.fontCss;
  const style = useMemo(() => cssVarsToStyle(cssVars), [cssVars]);
  const ownerId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const doc = containerRef.current?.ownerDocument ?? (typeof document !== "undefined" ? document : null);
    if (!doc) return;
    const head = doc.head;
    if (!head) return;

    const normalizedUrls = Array.isArray(fontUrls)
      ? fontUrls.filter((url) => typeof url === "string" && url.trim()).map((url) => url.trim())
      : [];
    const urlSet = new Set(normalizedUrls.map((url) => new URL(url, doc.baseURI).toString()));
    const linkSelector = `link[data-design-system-font-owner="${ownerId}"]`;
    const existingLinks = Array.from(head.querySelectorAll<HTMLLinkElement>(linkSelector));
    const existingMap = new Map(existingLinks.map((link) => [link.href, link]));

    existingLinks.forEach((link) => {
      if (!urlSet.has(link.href)) link.remove();
    });

    urlSet.forEach((href) => {
      if (existingMap.has(href)) return;
      const link = doc.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.dataset.designSystemFontOwner = ownerId;
      head.appendChild(link);
    });

    const styleSelector = `style[data-design-system-font-owner="${ownerId}"]`;
    const trimmedFontCss = typeof fontCss === "string" ? fontCss.trim() : "";
    let styleEl = head.querySelector<HTMLStyleElement>(styleSelector);
    if (trimmedFontCss) {
      if (!styleEl) {
        styleEl = doc.createElement("style");
        styleEl.dataset.designSystemFontOwner = ownerId;
        head.appendChild(styleEl);
      }
      styleEl.textContent = trimmedFontCss;
    } else if (styleEl) {
      styleEl.remove();
    }
  }, [fontUrls, fontCss, ownerId]);

  const shouldWrap = Boolean(style || dataTheme || (fontUrls && Array.isArray(fontUrls) && fontUrls.length) || fontCss);
  const wrapperStyle = useMemo(() => {
    if (!shouldWrap) return undefined;
    return { ...(style ?? {}), display: "contents" } as CSSProperties;
  }, [shouldWrap, style]);
  const body = !shouldWrap ? (
    <>{children}</>
  ) : (
    <div ref={containerRef} className={className} style={wrapperStyle} data-theme={dataTheme}>
      {children}
    </div>
  );

  return <DesignSystemContext.Provider value={tokens ?? null}>{body}</DesignSystemContext.Provider>;
}
