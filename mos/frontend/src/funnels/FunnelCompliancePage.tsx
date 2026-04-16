import { useEffect, useMemo, useState } from "react";

import { MarkdownViewer } from "@/components/ui/MarkdownViewer";
import { resolveRuntimePagePath, useFunnelRuntime } from "@/funnels/puckConfig";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";

type FunnelCompliancePageKey =
  | "privacy_policy"
  | "terms_of_service"
  | "returns_refunds_policy"
  | "contact_support";

type FunnelCompliancePageResponse = {
  pageKey: FunnelCompliancePageKey;
  title: string;
  markdown: string;
};

const apiBaseUrl = resolvePublicApiBaseUrl();

// TODO: Replace hardcoded Ember brand fallbacks with tenant-level design-system
// tokens (logo asset + brand colors) once the funnel runtime exposes them.
// For now these defaults target the Ember funnel; other tenants will inherit
// the same neutral cream + brand-red styling until per-tenant theming lands.
const EMBER_LOGO_URL =
  "https://api.moshq.app/public/assets/f35763ee-1099-457b-ad8e-b7bfc43a6b8b";
const EMBER_BRAND_LABEL = "Ember";

async function parsePublicError(resp: Response): Promise<string> {
  try {
    const payload = (await resp.clone().json()) as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
    if (typeof payload.message === "string" && payload.message.trim()) {
      return payload.message;
    }
  } catch {
    const text = await resp.text();
    if (text.trim()) {
      return text;
    }
  }
  return resp.statusText || "Request failed";
}

function resolveWebsiteUrl(runtime: ReturnType<typeof useFunnelRuntime>): string | null {
  if (!runtime) return null;

  const salesPageId = Object.entries(runtime.pageStageMap).find(([, stage]) => stage === "sales")?.[0] || null;
  const currentSlug = runtime.pageId ? runtime.pageMap[runtime.pageId] || null : null;
  const salesSlug = salesPageId ? runtime.pageMap[salesPageId] || null : null;
  const preferredSlug = salesSlug || currentSlug || runtime.entrySlug || null;
  if (!preferredSlug) return null;

  return new URL(resolveRuntimePagePath(runtime, preferredSlug), window.location.origin).toString();
}

function resolvePolicySlugPaths(
  runtime: NonNullable<ReturnType<typeof useFunnelRuntime>>,
): { terms: string; privacy: string; refund: string; contact: string; shop: string } {
  const resolve = (slug: string) => resolveRuntimePagePath(runtime, slug);
  const salesPageId = Object.entries(runtime.pageStageMap).find(([, stage]) => stage === "sales")?.[0];
  const salesSlug = salesPageId ? runtime.pageMap[salesPageId] : undefined;
  return {
    terms: resolve("terms-of-service"),
    privacy: resolve("privacy-policy"),
    refund: resolve("refund-policy"),
    contact: resolve("contact-us"),
    shop: salesSlug ? resolve(salesSlug) : resolve(runtime.entrySlug || ""),
  };
}

const COMPLIANCE_PAGE_CSS = `
.ember-compliance-root {
  --color-brand: #C41423;
  --color-text: #2D2926;
  --color-muted: rgba(45, 41, 38, 0.76);
  --color-bg: #FFFFFF;
  --color-page-bg: #FFFAF4;
  --color-page-bg-secondary: #F7F1E8;
  --color-border: rgba(45, 41, 38, 0.16);
  --font-heading: 'Bookmania', Georgia, 'Times New Roman', serif;
  --font-sans: 'Proxima Nova', -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif;
  background-color: var(--color-page-bg);
  color: var(--color-text);
  font-family: var(--font-sans);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.ember-compliance-header {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: var(--color-page-bg);
  position: relative;
  z-index: 50;
}
.ember-compliance-header__slot { width: 33.333%; display: flex; align-items: center; }
.ember-compliance-header__slot--center { justify-content: center; }
.ember-compliance-header__slot--right { justify-content: flex-end; }
.ember-compliance-shop-link {
  color: var(--color-brand);
  font-weight: 700;
  font-size: 20px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-decoration: none;
}
.ember-compliance-shop-link:hover { text-decoration: underline; }
.ember-compliance-header__logo { height: 40px; width: auto; display: block; }
.ember-compliance-main {
  flex: 1;
  width: 100%;
  padding: 48px 16px 72px;
}
@media (min-width: 768px) {
  .ember-compliance-main { padding: 64px 32px 96px; }
}
.ember-compliance-container {
  max-width: 880px;
  margin: 0 auto;
}
.ember-compliance-eyebrow {
  margin: 0 0 12px;
  color: var(--color-brand);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}
.ember-compliance-title {
  margin: 0 0 32px;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: clamp(36px, 5vw, 56px);
  line-height: 1.05;
  letter-spacing: -0.01em;
  color: var(--color-text);
}
.ember-compliance-card {
  background-color: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 40px clamp(24px, 4vw, 56px);
  box-shadow: 0 8px 24px rgba(45, 41, 38, 0.06);
}
.ember-compliance-status {
  background-color: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 18px 24px;
  font-size: 14px;
  color: var(--color-muted);
  box-shadow: 0 4px 12px rgba(45, 41, 38, 0.05);
}
.ember-compliance-status[role="alert"] {
  border-color: rgba(196, 20, 35, 0.3);
  background-color: rgba(196, 20, 35, 0.06);
  color: var(--color-brand);
}
.ember-compliance-content :where(h1, h2, h3, h4) {
  font-family: var(--font-heading);
  color: var(--color-text);
  letter-spacing: -0.01em;
}
.ember-compliance-content h1 { font-size: 28px; margin: 0 0 20px; line-height: 1.2; }
.ember-compliance-content h2 {
  font-size: 20px;
  font-weight: 700;
  margin: 32px 0 14px;
  line-height: 1.25;
  color: var(--color-brand);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.ember-compliance-content h3 { font-size: 17px; margin: 24px 0 10px; line-height: 1.3; }
.ember-compliance-content p,
.ember-compliance-content li {
  font-size: 16px;
  line-height: 1.65;
  color: var(--color-text);
}
.ember-compliance-content p { margin: 0 0 14px; }
.ember-compliance-content ul,
.ember-compliance-content ol { margin: 0 0 18px; padding-left: 22px; }
.ember-compliance-content li { margin-bottom: 8px; }
.ember-compliance-content strong { color: var(--color-text); font-weight: 700; }
.ember-compliance-content a { color: var(--color-brand); text-decoration: underline; }
.ember-compliance-footer {
  background-color: var(--color-page-bg-secondary);
  border-top: 1px solid var(--color-brand);
  padding: 56px 0 32px;
}
.ember-compliance-footer__inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 32px;
}
.ember-compliance-footer__primary {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding-bottom: 28px;
  border-bottom: 1px solid rgba(45, 41, 38, 0.2);
}
@media (min-width: 768px) {
  .ember-compliance-footer__primary { flex-direction: row; justify-content: space-between; }
}
.ember-compliance-footer__logo { height: 32px; width: auto; }
.ember-compliance-footer__nav {
  display: flex;
  gap: 32px;
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-brand);
}
.ember-compliance-footer__nav a { color: var(--color-brand); text-decoration: none; }
.ember-compliance-footer__nav a:hover { text-decoration: underline; }
.ember-compliance-footer__meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
  font-size: 13px;
  color: rgba(45, 41, 38, 0.6);
}
@media (min-width: 768px) {
  .ember-compliance-footer__meta { flex-direction: row; justify-content: space-between; }
}
.ember-compliance-footer__policies { display: flex; gap: 16px; }
.ember-compliance-footer__policies a {
  color: rgba(45, 41, 38, 0.6);
  text-decoration: none;
}
.ember-compliance-footer__policies a:hover { text-decoration: underline; }
.ember-compliance-footer__disclaimer {
  text-align: center;
  font-size: 12px;
  color: rgba(45, 41, 38, 0.45);
  margin-top: 28px;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.7;
}
`;

export function FunnelCompliancePage({
  pageKey,
  pageTitle,
}: {
  pageKey: FunnelCompliancePageKey;
  pageTitle?: string;
}) {
  const runtime = useFunnelRuntime();
  const [policyPage, setPolicyPage] = useState<FunnelCompliancePageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const websiteUrl = useMemo(() => resolveWebsiteUrl(runtime), [runtime]);
  const footerLinks = useMemo(
    () => (runtime ? resolvePolicySlugPaths(runtime) : null),
    [runtime],
  );

  useEffect(() => {
    if (!runtime?.productSlug || !runtime.funnelSlug || !websiteUrl) {
      return;
    }

    const controller = new AbortController();
    const query = new URLSearchParams({ website_url: websiteUrl });
    const url = `${apiBaseUrl}/public/funnels/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/policy-pages/${encodeURIComponent(pageKey)}?${query.toString()}`;

    setLoading(true);
    setError(null);
    setPolicyPage(null);

    fetch(url, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parsePublicError(resp));
        }
        return (await resp.json()) as FunnelCompliancePageResponse;
      })
      .then((payload) => {
        setPolicyPage(payload);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Unable to load policy page");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [pageKey, runtime?.funnelSlug, runtime?.productSlug, websiteUrl]);

  if (!runtime) {
    throw new Error("FunnelCompliancePage requires funnel runtime context.");
  }

  if (!websiteUrl) {
    throw new Error("FunnelCompliancePage requires a resolvable public funnel URL.");
  }

  const resolvedTitle = policyPage?.title || pageTitle || "Policy Page";
  const currentYear = new Date().getFullYear();

  return (
    <div className="ember-compliance-root">
      <style>{COMPLIANCE_PAGE_CSS}</style>

      <header className="ember-compliance-header">
        <div className="ember-compliance-header__slot">
          {footerLinks ? (
            <a className="ember-compliance-shop-link" href={footerLinks.shop} rel="nofollow">
              SHOP NOW
            </a>
          ) : null}
        </div>
        <div className="ember-compliance-header__slot ember-compliance-header__slot--center">
          <img
            src={EMBER_LOGO_URL}
            alt={EMBER_BRAND_LABEL}
            className="ember-compliance-header__logo"
          />
        </div>
        <div className="ember-compliance-header__slot ember-compliance-header__slot--right" />
      </header>

      <main className="ember-compliance-main">
        <div className="ember-compliance-container">
          <p className="ember-compliance-eyebrow">Compliance</p>
          <h1 className="ember-compliance-title">{resolvedTitle}</h1>

          {loading ? (
            <div className="ember-compliance-status">
              Loading {pageTitle || "policy page"}...
            </div>
          ) : null}

          {error ? (
            <div role="alert" className="ember-compliance-status">
              Unable to load {pageTitle || "policy page"}. {error}
            </div>
          ) : null}

          {policyPage ? (
            <article className="ember-compliance-card ember-compliance-content">
              <MarkdownViewer content={policyPage.markdown} className="max-w-none px-0" />
            </article>
          ) : null}
        </div>
      </main>

      <footer className="ember-compliance-footer">
        <div className="ember-compliance-footer__inner">
          <div className="ember-compliance-footer__primary">
            <img
              src={EMBER_LOGO_URL}
              alt={EMBER_BRAND_LABEL}
              className="ember-compliance-footer__logo"
            />
            <nav className="ember-compliance-footer__nav" aria-label="Footer primary">
              {footerLinks ? (
                <>
                  <a href={footerLinks.contact} rel="nofollow">CONTACT US</a>
                  <a href={footerLinks.shop} rel="nofollow">SHOP NOW</a>
                </>
              ) : null}
            </nav>
          </div>

          <div className="ember-compliance-footer__meta">
            <div>&copy; {currentYear} {EMBER_BRAND_LABEL}: Brain Clarity Protocol. All rights reserved.</div>
            {footerLinks ? (
              <div className="ember-compliance-footer__policies">
                <a href={footerLinks.terms} rel="nofollow">Terms</a>
                <a href={footerLinks.privacy} rel="nofollow">Privacy</a>
                <a href={footerLinks.refund} rel="nofollow">Refunds</a>
              </div>
            ) : null}
          </div>

          <div className="ember-compliance-footer__disclaimer">
            These statements have not been evaluated by the Food and Drug Administration. This product
            is not intended to diagnose, treat, cure, or prevent any disease.
          </div>
        </div>
      </footer>
    </div>
  );
}
