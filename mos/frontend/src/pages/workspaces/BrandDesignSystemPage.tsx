import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import {
  useDesignSystems,
  useCreateDesignSystem,
  useUpdateDesignSystem,
  useDeleteDesignSystem,
  useUploadDesignSystemLogo,
} from "@/api/designSystems";
import {
  useAuditClientShopifyThemeBrand,
  useClientShopifyThemeTemplateBuildJobStatus,
  useClient,
  useEnqueueClientShopifyThemeTemplateBuildJob,
  useGenerateClientShopifyThemeTemplateImages,
  useListClientShopifyThemeTemplateDrafts,
  usePublishClientShopifyThemeTemplateDraft,
  useCreateClientShopifyInstallUrl,
  useClientShopifyStatus,
  useDisconnectClientShopifyInstallation,
  useSetClientShopifyDefaultShop,
  useUpdateClientShopifyThemeTemplateDraft,
  useUpdateClientShopifyInstallation,
  useUpdateClient,
  type ClientShopifyThemeBrandAuditResponse,
  type ClientShopifyThemeTemplateDraftData,
  type ClientShopifyThemeTemplateImageSlot,
  type ClientShopifyThemeTemplateTextSlot,
  type ClientShopifyThemeTemplatePublishResponse,
} from "@/api/clients";
import {
  useSyncComplianceShopifyPolicyPages,
  type ComplianceShopifyPolicySyncResponse,
} from "@/api/compliance";
import { useAssets } from "@/api/assets";
import { useProducts, useUploadProductAssets } from "@/api/products";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Table, TableBody, TableCell, TableHeadCell, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import type { DesignSystem } from "@/types/designSystems";
import type { Product } from "@/types/products";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/toast";

const DESIGN_SYSTEM_TEMPLATE = `{
  "dataTheme": "light",
  "fontUrls": [
    "https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800;900&family=Merriweather:wght@700;900&display=swap"
  ],
  "cssVars": {
    "--font-sans": "Poppins, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial, Apple Color Emoji, Segoe UI Emoji",
    "--font-heading": "Merriweather, ui-serif, Georgia, Times New Roman, Times, serif",
    "--font-cta": "var(--font-sans)",
    "--text-11": "11px",
    "--text-12": "12px",
    "--text-13": "13px",
    "--text-sm": "14px",
    "--text-15": "15px",
    "--text-base": "16px",
    "--text-18": "18px",
    "--text-20": "20px",
    "--text-lg": "22px",
    "--text-24": "24px",
    "--text-25": "25px",
    "--text-32": "32px",
    "--text-34": "34px",
    "--text-36": "36px",
    "--text-38": "38px",
    "--text-40": "40px",
    "--h1": "clamp(35px, 5.2vw, 50px)",
    "--h2": "clamp(35px, 4vw, 40px)",
    "--h3": "20px",
    "--line": "1.6",
    "--heading-size": "clamp(35px, 4.5vw, 50px)",
    "--heading-size-mobile": "clamp(30px, 4.5vw, 35px)",
    "--heading-line": "1.4",
    "--heading-weight": "500",
    "--color-page-bg": "rgb(255, 249, 244)",
    "--color-brand": "#061a70",
    "--color-bg": "#ffffff",
    "--color-text": "var(--color-brand)",
    "--color-muted": "rgba(6, 26, 112, 0.76)",
    "--color-border": "rgba(6, 26, 112, 0.18)",
    "--color-soft": "rgba(6, 26, 112, 0.06)",
    "--focus-outline-color": "rgba(6, 26, 112, 0.35)",
    "--focus-outline-color-soft": "rgba(6, 26, 112, 0.25)",
    "--focus-outline": "3px solid var(--focus-outline-color)",
    "--focus-outline-soft": "3px solid var(--focus-outline-color-soft)",
    "--color-cta": "#3b8c33",
    "--color-cta-text": "#ffffff",
    "--color-cta-shell": "#ffffff",
    "--color-cta-icon": "#2f6f29",
    "--container-max": "1380px",
    "--container-pad": "24px",
    "--section-pad-y": "120px",
    "--space-1": "4px",
    "--space-2": "8px",
    "--space-3": "12px",
    "--space-4": "16px",
    "--space-5": "24px",
    "--space-6": "32px",
    "--space-7": "48px",
    "--space-8": "64px",
    "--radius-sm": "10px",
    "--radius-md": "14px",
    "--radius-lg": "18px",
    "--shadow-sm": "0 2px 10px rgba(0, 0, 0, 0.06), 0 10px 30px rgba(0, 0, 0, 0.05)",
    "--hero-bg": "#e9fbff",
    "--hero-min-height": "520px",
    "--hero-pad-x": "clamp(24px, 6vw, 92px)",
    "--hero-pad-y": "clamp(28px, 5vw, 70px)",
    "--hero-title-max": "none",
    "--hero-subtitle-max": "none",
    "--hero-title-size": "var(--heading-size)",
    "--hero-title-weight": "var(--heading-weight)",
    "--hero-title-letter-spacing": "-0.06em",
    "--hero-title-line": "1.1",
    "--hero-subtitle-size": "clamp(18px, 2.6vw, 25px)",
    "--hero-subtitle-weight": "500",
    "--hero-subtitle-line": "1.2",
    "--hero-subtitle-gap": "16px",
    "--hero-media-placeholder-bg": "rgba(0, 0, 0, 0.06)",
    "--badge-strip-bg": "var(--hero-bg)",
    "--badge-strip-border": "1px solid var(--color-border)",
    "--badge-strip-pad-y": "clamp(30px, 4vw, 40px)",
    "--badge-strip-gap": "clamp(22px, 4vw, 64px)",
    "--badge-icon-size": "60px",
    "--badge-text-color": "var(--color-brand)",
    "--badge-text-weight": "600",
    "--badge-value-size": "clamp(14px, 1.7vw, 25px)",
    "--badge-label-size": "clamp(14px, 1.7vw, 25px)",
    "--badge-text-size": "var(--badge-label-size)",
    "--badge-letter-spacing": "-0.06em",
    "--marquee-height": "clamp(56px, 7vw, 70px)",
    "--marquee-speed": "50s",
    "--marquee-bg": "rgb(255, 248, 189)",
    "--marquee-border": "var(--color-brand)",
    "--marquee-text": "var(--color-brand)",
    "--marquee-font-size": "clamp(20px, 3.5vw, 30px)",
    "--marquee-font-weight": "900",
    "--marquee-letter-spacing": "0.03em",
    "--marquee-gap": "clamp(50px, 8vw, 80px)",
    "--marquee-pad-x": "0px",
    "--pill-marquee-speed": "60s",
    "--listicle-card-gap": "40px",
    "--listicle-card-radius": "5px",
    "--listicle-card-border": "0.5px solid var(--color-brand)",
    "--listicle-media-width": "320px",
    "--listicle-media-min-height": "300px",
    "--listicle-media-min-height-mobile": "220px",
    "--listicle-media-placeholder-bg": "rgba(6, 26, 112, 0.08)",
    "--listicle-number-size": "50px",
    "--listicle-number-offset": "16px",
    "--listicle-number-bg": "var(--color-brand)",
    "--listicle-number-fg": "#ffffff",
    "--listicle-number-font-size": "32px",
    "--listicle-content-pad-x": "40px",
    "--listicle-content-pad-y": "40px",
    "--listicle-content-pad-x-mobile": "20px",
    "--listicle-content-pad-y-mobile": "30px",
    "--listicle-title-font": "AwesomeSerif, serif",
    "--listicle-title-size": "40px",
    "--listicle-title-size-mobile": "40px",
    "--listicle-title-line": "1.2",
    "--listicle-title-color": "rgb(0, 27, 116)",
    "--listicle-title-margin-bottom": "20px",
    "--listicle-title-letter-spacing": "-0.06em",
    "--listicle-body-size": "clamp(16px, 2.3vw, 20px)",
    "--listicle-body-line": "1.5",
    "--listicle-body-gap": "18px",
    "--reviews-pad-y": "64px",
    "--reviews-gap": "34px",
    "--reviews-height": "440px",
    "--reviews-card-width": "460px",
    "--reviews-card-radius": "36px",
    "--reviews-card-bg": "#f3ece6",
    "--reviews-card-pad": "46px 44px 38px",
    "--reviews-quote-size": "64px",
    "--reviews-quote-color": "#7b6a5d",
    "--reviews-quote-top": "18px",
    "--reviews-quote-left": "34px",
    "--reviews-stars-top": "22px",
    "--reviews-star-size": "22px",
    "--reviews-star-color": "#f59a3b",
    "--reviews-text-size": "22px",
    "--reviews-text-line": "1.45",
    "--reviews-text-color": "rgba(11, 11, 11, 0.72)",
    "--reviews-author-color": "rgba(11, 11, 11, 0.8)",
    "--reviews-verified-bg": "rgba(0, 0, 0, 0.08)",
    "--reviews-verified-border": "0",
    "--reviews-verified-color": "rgba(0, 0, 0, 0.75)",
    "--reviews-media-main-width": "1fr",
    "--reviews-media-slim-width": "140px",
    "--reviews-media-gap": "16px",
    "--reviews-media-radius": "26px",
    "--reviews-media-placeholder-bg": "rgba(0, 0, 0, 0.06)",
    "--reviews-nav-size": "40px",
    "--reviews-nav-offset": "10px",
    "--reviews-nav-bg": "#ffffff",
    "--reviews-nav-border": "1px solid rgba(6, 26, 112, 0.18)",
    "--reviews-nav-color": "var(--color-brand)",
    "--reviews-nav-shadow": "0 10px 22px rgba(0, 0, 0, 0.12)",
    "--reviews-dots-top": "18px",
    "--reviews-dot-gap": "10px",
    "--reviews-dot-size": "6px",
    "--reviews-dot-bg": "rgba(0, 0, 0, 0.14)",
    "--reviews-dot-active-width": "24px",
    "--reviews-dot-active-bg": "#7b6a5d",
    "--pitch-bg": "#e9fbff",
    "--pitch-pad-y": "80px",
    "--pitch-gap": "60px",
    "--pitch-content-max": "560px",
    "--pitch-title-size": "clamp(35px, 2.2vw, 50px)",
    "--pitch-title-line": "var(--heading-line)",
    "--pitch-title-color": "var(--color-brand)",
    "--pitch-title-letter-spacing": "-0.06em",
    "--pitch-title-weight": "var(--heading-weight)",
    "--pitch-bullets-top": "28px",
    "--pitch-bullets-bottom": "30px",
    "--pitch-bullet-gap": "18px",
    "--pitch-bullet-size": "16px",
    "--pitch-bullet-line": "1.4",
    "--pitch-bullet-strong-weight": "600",
    "--pitch-text-color": "var(--color-brand)",
    "--pitch-check-size": "22px",
    "--pitch-check-gap": "14px",
    "--pitch-check-bg": "transparent",
    "--pitch-check-border": "2px solid var(--color-brand)",
    "--pitch-check-icon-size": "14px",
    "--pitch-check-color": "var(--color-brand)",
    "--pitch-media-max": "560px",
    "--pitch-media-radius": "4px",
    "--pitch-media-border": "1px solid rgba(6, 26, 112, 0.55)",
    "--pitch-media-bg": "rgba(255, 255, 255, 0.25)",
    "--pitch-media-shadow": "0 18px 42px rgba(0, 0, 0, 0.12)",
    "--cta-shell-pad": "10px",
    "--cta-shell-shadow": "0 16px 44px rgba(0, 0, 0, 0.16)",
    "--cta-icon-size": "var(--cta-icon-size-lg)",
    "--cta-height-lg": "62px",
    "--cta-height-md": "58px",
    "--cta-height-sm": "48px",
    "--cta-min-width-lg": "420px",
    "--cta-min-width-md": "360px",
    "--cta-min-width-sm": "260px",
    "--cta-pad-x-lg": "34px",
    "--cta-pad-x-md": "30px",
    "--cta-pad-x-sm": "22px",
    "--cta-font-size-lg": "18px",
    "--cta-font-size-md": "17px",
    "--cta-font-size-sm": "15px",
    "--cta-letter-spacing": "0.06em",
    "--cta-font-weight": "900",
    "--cta-circle-size-lg": "40px",
    "--cta-circle-size-md": "38px",
    "--cta-circle-size-sm": "34px",
    "--cta-icon-size-lg": "18px",
    "--cta-icon-size-md": "18px",
    "--cta-icon-size-sm": "16px",
    "--wall-pad-y": "80px",
    "--wall-pad-top": "var(--wall-pad-y)",
    "--wall-title-size": "var(--hero-title-size)",
    "--wall-title-line": "var(--hero-title-line)",
    "--wall-title-weight": "var(--hero-title-weight)",
    "--wall-title-letter-spacing": "var(--hero-title-letter-spacing)",
    "--wall-button-bg": "rgb(255, 248, 189)",
    "--wall-button-text": "var(--color-brand)",
    "--wall-button-font-size": "12px",
    "--wall-button-weight": "700",
    "--wall-button-letter-spacing": "0",
    "--wall-button-pad": "8px 20px",
    "--wall-button-radius": "999px",
    "--wall-height": "clamp(500px, 70vh, 600px)",
    "--wall-scroll-duration": "60s",
    "--wall-gap": "clamp(8px, 1.2vw, 15px)",
    "--wall-pad-x": "clamp(8px, 1.1vw, 10px)",
    "--wall-fade-height": "150px",
    "--wall-card-radius": "0px",
    "--wall-card-bg": "#ffffff",
    "--wall-card-border": "1px solid rgba(0, 0, 0, 0.06)",
    "--wall-card-shadow": "0 18px 44px rgba(0, 0, 0, 0.08)",
    "--wall-card-pad": "16px 16px 14px",
    "--wall-author-size": "15px",
    "--wall-text-size": "14px",
    "--wall-muted": "rgba(0, 0, 0, 0.44)",
    "--wall-author-color": "rgba(0, 0, 0, 0.72)",
    "--wall-verified-color": "rgba(0, 0, 0, 0.56)",
    "--wall-check-color": "rgba(0, 0, 0, 0.45)",
    "--wall-text-color": "rgba(0, 0, 0, 0.66)",
    "--modal-overlay-bg": "rgba(2, 10, 18, 0.62)",
    "--modal-shadow": "0 18px 60px rgba(0, 0, 0, 0.45)",
    "--modal-z": "100",
    "--footer-bg": "var(--pdp-surface-soft)",
    "--footer-border": "1px solid var(--color-brand)",
    "--footer-pad-y": "48px",
    "--footer-logo-height": "54px",
    "--footer-gap": "18px",
    "--floating-cta-bottom": "18px",
    "--floating-cta-z": "50",
    "--pdp-brand-strong": "rgb(0, 27, 116)",
    "--pdp-brand-05": "rgba(6, 26, 112, 0.05)",
    "--pdp-brand-08": "rgba(6, 26, 112, 0.08)",
    "--pdp-brand-12": "rgba(6, 26, 112, 0.12)",
    "--pdp-brand-14": "rgba(6, 26, 112, 0.14)",
    "--pdp-brand-22": "rgba(6, 26, 112, 0.22)",
    "--pdp-brand-32": "rgba(6, 26, 112, 0.32)",
    "--pdp-brand-35": "rgba(6, 26, 112, 0.35)",
    "--pdp-brand-45": "rgba(6, 26, 112, 0.45)",
    "--pdp-brand-55": "rgba(0, 27, 116, 0.55)",
    "--pdp-brand-85": "rgba(6, 26, 112, 0.85)",
    "--pdp-brand-90": "rgba(6, 26, 112, 0.9)",
    "--pdp-black-03": "rgba(0, 0, 0, 0.03)",
    "--pdp-black-05": "rgba(0, 0, 0, 0.05)",
    "--pdp-black-06": "rgba(0, 0, 0, 0.06)",
    "--pdp-black-08": "rgba(0, 0, 0, 0.08)",
    "--pdp-black-10": "rgba(0, 0, 0, 0.1)",
    "--pdp-black-12": "rgba(0, 0, 0, 0.12)",
    "--pdp-black-18": "rgba(0, 0, 0, 0.18)",
    "--pdp-black-25": "rgba(0, 0, 0, 0.25)",
    "--pdp-black-28": "rgba(0, 0, 0, 0.28)",
    "--pdp-black-55": "rgba(0, 0, 0, 0.55)",
    "--pdp-black-60": "rgba(0, 0, 0, 0.6)",
    "--pdp-black-65": "rgba(0, 0, 0, 0.65)",
    "--pdp-black-70": "rgba(0, 0, 0, 0.7)",
    "--pdp-surface-soft": "rgb(255, 240, 228)",
    "--pdp-surface-muted": "#f3f4f6",
    "--pdp-swatch-bg": "#e5e7eb",
    "--pdp-white-92": "rgba(255, 255, 255, 0.92)",
    "--pdp-white-95": "rgba(255, 255, 255, 0.95)",
    "--pdp-white-96": "rgba(255, 255, 255, 0.96)",
    "--pdp-transparent": "rgba(0, 0, 0, 0)",
    "--pdp-cta-bg": "var(--color-cta)",
    "--pdp-check-bg": "var(--color-cta)",
    "--pdp-video-bg": "#111827",
    "--pdp-warning-bg": "#ff3b30",
    "--pdp-rating-color": "#f59e0b",
    "--pdp-rating-muted": "rgba(245, 158, 11, 0.25)",
    "--pdp-stock-bg": "rgba(255, 0, 0, 0.06)",
    "--pdp-stock-border": "rgba(255, 0, 0, 0.18)",
    "--pdp-compare-at": "rgba(255, 0, 0, 0.7)",
    "--pdp-urgency-bg": "#fdecef",
    "--pdp-urgency-border": "#f7d7de",
    "--pdp-urgency-muted-bg": "#f8f1f3",
    "--pdp-comparison-good": "#16a34a",
    "--pdp-comparison-bad": "#ef4444",
    "--pdp-radius-2": "2px",
    "--pdp-radius-3": "3px",
    "--pdp-radius-5": "5px",
    "--pdp-radius-8": "8px",
    "--pdp-radius-12": "12px",
    "--pdp-radius-pill": "999px",
    "--pdp-radius-tab": "0 0 2px 2px",
    "--pdp-shadow-gift-card": "0 10px 26px var(--pdp-black-05)",
    "--pdp-shadow-option": "var(--pdp-black-06) 0 4px 10px 0",
    "--pdp-shadow-story": "0 18px 40px var(--pdp-black-08)",
    "--pdp-shadow-hint": "0 18px 40px var(--pdp-black-12)",
    "--pdp-shadow-review": "0 18px 50px var(--pdp-black-06)"
  },
  "funnelDefaults": {
    "containerWidth": "lg",
    "sectionPadding": "md"
  },
  "brand": {
    "name": "Acme",
    "logoAssetPublicId": ""
  }
}`;

const DEFAULT_TOKENS = (() => {
  try {
    return JSON.parse(DESIGN_SYSTEM_TEMPLATE) as Record<string, unknown>;
  } catch {
    return { cssVars: {} } as Record<string, unknown>;
  }
})();

const DESIGN_SYSTEM_PROMPT = `Update our DESIGN SYSTEM TEMPLATE for a specific brand.
- Output ONLY valid JSON (no markdown).
- Start from the provided template JSON and change ONLY a small set of tokens needed to match the brand.
- Keep dataTheme: "light" (do not generate dark mode tokens).
- Keep layout/geometry tokens (sizes/spacing/radii/type scale) unchanged unless explicitly requested.
- Prefer minimal "accent swaps" first:
  - CTA: --color-cta, --color-cta-icon (and only if needed: --color-cta-text, --pdp-cta-bg, --pdp-check-bg)
  - Marquee: --marquee-bg, --marquee-text
  - Badges: --badge-strip-bg, --badge-text-color, --badge-strip-border
  - Section backgrounds: --hero-bg, --pitch-bg (optional: --color-page-bg)
- Maintain accessibility: CTA text must stay readable on the CTA background; marquee text must stay readable on marquee background; keep surfaces light.
Brand details: [describe your brand, industry, vibe, and any required colors/fonts].
Return the full updated tokens JSON (same shape/keys as the template).`;

function formatTokens(tokens: unknown) {
  const value = tokens && typeof tokens === "object" ? tokens : DEFAULT_TOKENS;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return JSON.stringify(DEFAULT_TOKENS, null, 2);
  }
}

function countCssVars(tokens: unknown) {
  if (!tokens || typeof tokens !== "object") return 0;
  const vars = (tokens as { cssVars?: Record<string, unknown> }).cssVars;
  return vars && typeof vars === "object" ? Object.keys(vars).length : 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeCssVars(tokens: unknown): Record<string, string> {
  if (!isRecord(tokens)) return {};
  const vars = tokens.cssVars;
  if (!isRecord(vars)) return {};
  const normalized: Record<string, string> = {};
  for (const [key, value] of Object.entries(vars)) {
    if (typeof value === "string" || typeof value === "number") {
      normalized[key] = String(value);
    }
  }
  return normalized;
}

function normalizeFontUrls(tokens: unknown): string[] {
  if (!isRecord(tokens) || !Array.isArray(tokens.fontUrls)) return [];
  return tokens.fontUrls
    .filter((url) => typeof url === "string")
    .map((url) => url.trim())
    .filter(Boolean);
}

function normalizeBrand(tokens: unknown): { name?: string; logoAssetPublicId?: string; logoAlt?: string } {
  if (!isRecord(tokens) || !isRecord(tokens.brand)) return {};
  const brand = tokens.brand;
  const name = typeof brand.name === "string" && brand.name.trim() ? brand.name.trim() : undefined;
  const logoAssetPublicId =
    typeof brand.logoAssetPublicId === "string" && brand.logoAssetPublicId.trim()
      ? brand.logoAssetPublicId.trim()
      : undefined;
  const logoAlt = typeof brand.logoAlt === "string" && brand.logoAlt.trim() ? brand.logoAlt.trim() : undefined;
  return { name, logoAssetPublicId, logoAlt };
}

function applyLogoPublicIdToTokens(
  tokens: unknown,
  logoPublicId: string,
  defaultLogoAlt?: string
): { value?: Record<string, unknown>; error?: string } {
  if (!isRecord(tokens)) {
    return { error: "Design system tokens must be a JSON object." };
  }
  const nextTokens: Record<string, unknown> = { ...tokens };
  const brand = nextTokens.brand;
  if (brand !== undefined && !isRecord(brand)) {
    return { error: "Design system tokens.brand must be a JSON object." };
  }
  const nextBrand: Record<string, unknown> = isRecord(brand) ? { ...brand } : {};
  nextBrand.logoAssetPublicId = logoPublicId;
  if (
    defaultLogoAlt &&
    !(typeof nextBrand.logoAlt === "string" && nextBrand.logoAlt.trim())
  ) {
    nextBrand.logoAlt = defaultLogoAlt;
  }
  nextTokens.brand = nextBrand;
  return { value: nextTokens };
}

function isColorLikeCssValue(raw: string): boolean {
  const value = raw.trim().toLowerCase();
  if (!value) return false;
  if (value === "transparent" || value === "currentcolor") return true;
  if (value.startsWith("#")) return true;
  if (value.startsWith("rgb(") || value.startsWith("rgba(")) return true;
  if (value.startsWith("hsl(") || value.startsWith("hsla(")) return true;
  if (value.startsWith("color-mix(")) return true;
  const varMatch = value.match(/^var\((--[^,\s)]+)/);
  if (!varMatch) return false;
  const ref = varMatch[1] || "";
  return (
    ref.includes("color") ||
    ref.includes("bg") ||
    ref.includes("text") ||
    ref.includes("border") ||
    ref.includes("foreground") ||
    ref.includes("surface") ||
    ref.includes("overlay") ||
    ref.includes("ring") ||
    ref.includes("outline") ||
    ref.includes("pdp-")
  );
}

function parseTokens(raw: string): { value?: Record<string, unknown>; error?: string } {
  if (!raw.trim()) {
    return { error: "Tokens JSON cannot be empty." };
  }
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: "Tokens must be a JSON object." };
    }
    return { value: parsed };
  } catch {
    return { error: "Invalid JSON. Check for missing commas or quotes." };
  }
}

function parseStringMap(raw: string, label: string): { value?: Record<string, string>; error?: string } {
  if (!raw.trim()) return { value: {} };
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: `${label} must be a JSON object.` };
    }
    const normalized: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof key !== "string" || !key.trim()) {
        return { error: `${label} keys must be non-empty strings.` };
      }
      if (typeof value !== "string" || !value.trim()) {
        return { error: `${label} values must be non-empty strings.` };
      }
      normalized[key.trim()] = value.trim();
    }
    return { value: normalized };
  } catch {
    return { error: `${label} must be valid JSON.` };
  }
}

function parseSlotPathList(raw: string): { value?: string[]; error?: string } {
  if (!raw.trim()) return { value: [] };
  const normalized: string[] = [];
  const seen = new Set<string>();
  const duplicatePaths: string[] = [];
  const segments = raw
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  for (const segment of segments) {
    if (seen.has(segment)) {
      duplicatePaths.push(segment);
      continue;
    }
    seen.add(segment);
    normalized.push(segment);
  }
  if (duplicatePaths.length) {
    return {
      error: `Duplicate slot path(s) in generation scope: ${duplicatePaths.join(", ")}`,
    };
  }
  return { value: normalized };
}

function humanizeSlotToken(raw: string): string {
  const normalized = raw
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_./-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "Image Slot";
  return normalized
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function deriveImageSlotBaseLabel(slot: ClientShopifyThemeTemplateImageSlot): string {
  const haystack = `${slot.role} ${slot.key} ${slot.path}`.toLowerCase();
  if (haystack.includes("feature")) return "Feature";
  if (haystack.includes("hero") && (haystack.includes("icon") || haystack.includes("badge"))) {
    return "Hero Icon";
  }
  if (haystack.includes("hero")) return "Hero Image";
  if (haystack.includes("gallery")) return "Gallery Image";
  if (haystack.includes("review") || haystack.includes("testimonial")) return "Review";

  if (slot.role.trim()) return humanizeSlotToken(slot.role);
  if (slot.key.trim()) return humanizeSlotToken(slot.key);

  const pathLeaf = slot.path.split(".").pop() || slot.path;
  return humanizeSlotToken(pathLeaf);
}

function buildImageSlotReadableLabelMap(
  slots: ClientShopifyThemeTemplateImageSlot[]
): Map<string, string> {
  const baseByPath = slots.map((slot) => ({
    path: slot.path,
    baseLabel: deriveImageSlotBaseLabel(slot),
  }));
  const totalsByBase = new Map<string, number>();
  for (const entry of baseByPath) {
    totalsByBase.set(entry.baseLabel, (totalsByBase.get(entry.baseLabel) || 0) + 1);
  }
  const seenByBase = new Map<string, number>();
  const labelsByPath = new Map<string, string>();
  for (const entry of baseByPath) {
    const total = totalsByBase.get(entry.baseLabel) || 0;
    if (total <= 1) {
      labelsByPath.set(entry.path, entry.baseLabel);
      continue;
    }
    const nextIndex = (seenByBase.get(entry.baseLabel) || 0) + 1;
    seenByBase.set(entry.baseLabel, nextIndex);
    labelsByPath.set(entry.path, `${entry.baseLabel} ${nextIndex}`);
  }
  return labelsByPath;
}

function deriveTextSlotBaseLabel(slot: ClientShopifyThemeTemplateTextSlot): string {
  const haystack = `${slot.key} ${slot.path}`.toLowerCase();
  if (haystack.includes("headline") || haystack.includes("heading") || haystack.includes("title")) {
    return "Headline";
  }
  if (haystack.includes("subheading") || haystack.includes("subtitle")) {
    return "Subheadline";
  }
  if (haystack.includes("feature")) return "Feature Copy";
  if (haystack.includes("body") || haystack.includes("description")) return "Body Copy";
  if (haystack.includes("cta") || haystack.includes("button")) return "CTA Label";
  if (haystack.includes("review") || haystack.includes("testimonial")) return "Review Copy";
  if (slot.key.trim()) return humanizeSlotToken(slot.key);
  const pathLeaf = slot.path.split(".").pop() || slot.path;
  return humanizeSlotToken(pathLeaf);
}

function buildTextSlotReadableLabelMap(
  slots: ClientShopifyThemeTemplateTextSlot[]
): Map<string, string> {
  const baseByPath = slots.map((slot) => ({
    path: slot.path,
    baseLabel: deriveTextSlotBaseLabel(slot),
  }));
  const totalsByBase = new Map<string, number>();
  for (const entry of baseByPath) {
    totalsByBase.set(entry.baseLabel, (totalsByBase.get(entry.baseLabel) || 0) + 1);
  }
  const seenByBase = new Map<string, number>();
  const labelsByPath = new Map<string, string>();
  for (const entry of baseByPath) {
    const total = totalsByBase.get(entry.baseLabel) || 0;
    if (total <= 1) {
      labelsByPath.set(entry.path, entry.baseLabel);
      continue;
    }
    const nextIndex = (seenByBase.get(entry.baseLabel) || 0) + 1;
    seenByBase.set(entry.baseLabel, nextIndex);
    labelsByPath.set(entry.path, `${entry.baseLabel} ${nextIndex}`);
  }
  return labelsByPath;
}

function normalizePromptContextValue(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

function readPromptContextMap(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const normalized: Record<string, string> = {};
  for (const [rawPath, rawValue] of Object.entries(raw)) {
    if (typeof rawPath !== "string" || !rawPath.trim()) continue;
    if (typeof rawValue !== "string") continue;
    const cleanedValue = normalizePromptContextValue(rawValue);
    if (!cleanedValue) continue;
    normalized[rawPath.trim()] = cleanedValue;
  }
  return normalized;
}

function buildTemplateImageGenerationGeneralContext(
  draftData: ClientShopifyThemeTemplateDraftData,
  product: Product | null
): string {
  const segments: string[] = [];
  if (draftData.workspaceName.trim()) segments.push(`Workspace: ${draftData.workspaceName.trim()}.`);
  if (draftData.brandName.trim()) segments.push(`Brand: ${draftData.brandName.trim()}.`);
  if (draftData.themeName.trim()) segments.push(`Theme: ${draftData.themeName.trim()}.`);
  if (draftData.themeRole.trim()) segments.push(`Theme role: ${draftData.themeRole.trim()}.`);

  if (product) {
    if (product.title?.trim()) segments.push(`Product: ${product.title.trim()}.`);
    if (product.product_type?.trim()) segments.push(`Product type: ${product.product_type.trim()}.`);
    if (product.description?.trim()) segments.push(`Product summary: ${product.description.trim()}.`);
    if (product.primary_benefits?.length) {
      segments.push(`Primary benefits: ${product.primary_benefits.filter(Boolean).slice(0, 4).join("; ")}.`);
    }
    if (product.feature_bullets?.length) {
      segments.push(`Feature points: ${product.feature_bullets.filter(Boolean).slice(0, 4).join("; ")}.`);
    }
  }

  const colorBrand = draftData.cssVars?.["--color-brand"];
  if (typeof colorBrand === "string" && colorBrand.trim()) {
    segments.push(`Primary brand color: ${colorBrand.trim()}.`);
  }
  const colorCta = draftData.cssVars?.["--color-cta"];
  if (typeof colorCta === "string" && colorCta.trim()) {
    segments.push(`CTA color: ${colorCta.trim()}.`);
  }

  return normalizePromptContextValue(segments.join(" "));
}

function buildTemplateImageGenerationSlotContextByPath(
  draftData: ClientShopifyThemeTemplateDraftData,
  imageSlotReadableLabelByPath: Map<string, string>
): Record<string, string> {
  const textValuesByPath = new Map<string, string>();
  for (const slot of draftData.textSlots) {
    const rawValue = draftData.componentTextValues[slot.path] || slot.currentValue || "";
    const cleaned = normalizePromptContextValue(rawValue);
    if (!cleaned) continue;
    textValuesByPath.set(slot.path, cleaned);
  }
  for (const [rawPath, rawValue] of Object.entries(draftData.componentTextValues || {})) {
    if (typeof rawPath !== "string" || !rawPath.trim()) continue;
    if (typeof rawValue !== "string") continue;
    const cleaned = normalizePromptContextValue(rawValue);
    if (!cleaned) continue;
    textValuesByPath.set(rawPath.trim(), cleaned);
  }

  const sortedTextEntries = Array.from(textValuesByPath.entries()).sort(([a], [b]) => a.localeCompare(b));
  const contextByPath: Record<string, string> = {};

  for (const slot of draftData.imageSlots) {
    const path = slot.path;
    const label =
      imageSlotReadableLabelByPath.get(path) || humanizeSlotToken(path.split(".").pop() || path);
    const segments: string[] = [
      `Purpose: ${label}.`,
      `Slot role: ${slot.role || "generic"}.`,
      `Target key: ${slot.key || "image"}.`,
      `Preferred aspect: ${slot.recommendedAspect || "any"}.`,
    ];

    const sectionPrefix = path.includes(".settings.")
      ? `${path.split(".settings.")[0]}.settings.`
      : "";
    if (sectionPrefix) {
      const relatedValues: string[] = [];
      for (const [textPath, value] of sortedTextEntries) {
        if (!textPath.startsWith(sectionPrefix)) continue;
        if (relatedValues.includes(value)) continue;
        relatedValues.push(value);
        if (relatedValues.length >= 2) break;
      }
      if (relatedValues.length) {
        segments.push(`Related copy context: ${relatedValues.join(" ")}.`);
      }
    }

    const normalizedContext = normalizePromptContextValue(segments.join(" "));
    if (normalizedContext) {
      contextByPath[path] = normalizedContext;
    }
  }

  return contextByPath;
}

export function BrandDesignSystemPage() {
  const { workspace } = useWorkspace();
  const { data: client } = useClient(workspace?.id);
  const {
    data: shopifyStatus,
    isLoading: isLoadingShopifyStatus,
    refetch: refetchShopifyStatus,
    error: shopifyStatusError,
  } = useClientShopifyStatus(workspace?.id);
  const { data: designSystems = [], isLoading } = useDesignSystems(workspace?.id);
  const updateClient = useUpdateClient();
  const createShopifyInstallUrl = useCreateClientShopifyInstallUrl(workspace?.id || "");
  const setDefaultShop = useSetClientShopifyDefaultShop(workspace?.id || "");
  const updateShopifyInstallation = useUpdateClientShopifyInstallation(workspace?.id || "");
  const disconnectShopifyInstallation = useDisconnectClientShopifyInstallation(workspace?.id || "");
  const createDesignSystem = useCreateDesignSystem();
  const updateDesignSystem = useUpdateDesignSystem();
  const uploadDesignSystemLogo = useUploadDesignSystemLogo();
  const deleteDesignSystem = useDeleteDesignSystem();
  const syncCompliancePolicyPages = useSyncComplianceShopifyPolicyPages(workspace?.id);
  const enqueueShopifyThemeTemplateBuildJob = useEnqueueClientShopifyThemeTemplateBuildJob(workspace?.id);
  const generateShopifyThemeTemplateImages = useGenerateClientShopifyThemeTemplateImages(workspace?.id);
  const publishShopifyThemeTemplateDraft = usePublishClientShopifyThemeTemplateDraft(workspace?.id);
  const updateShopifyThemeTemplateDraft = useUpdateClientShopifyThemeTemplateDraft(workspace?.id);
  const { data: shopifyThemeTemplateDrafts = [] } = useListClientShopifyThemeTemplateDrafts(workspace?.id);
  const auditShopifyThemeBrand = useAuditClientShopifyThemeBrand(workspace?.id);
  const { data: workspaceProducts = [] } = useProducts(workspace?.id);
  const { data: logoAssets = [], isLoading: isLoadingLogoAssets } = useAssets(
    { clientId: workspace?.id, assetKind: "image", statuses: ["approved", "qa_passed"] },
    { enabled: Boolean(workspace?.id) }
  );
  const {
    data: workspaceImageAssets = [],
    isLoading: isLoadingWorkspaceImageAssets,
    refetch: refetchWorkspaceImageAssets,
  } = useAssets({ clientId: workspace?.id, assetKind: "image" }, { enabled: Boolean(workspace?.id) });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<DesignSystem | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftTokens, setDraftTokens] = useState(formatTokens(DEFAULT_TOKENS));
  const [tokensError, setTokensError] = useState<string | null>(null);

  const [previewDesignSystemId, setPreviewDesignSystemId] = useState("");
  const [varsFilter, setVarsFilter] = useState("");
  const [logoErrored, setLogoErrored] = useState(false);
  const [selectedLogoPublicId, setSelectedLogoPublicId] = useState("");
  const [shopifyShopDomainDraft, setShopifyShopDomainDraft] = useState("");
  const [defaultShopDomainDraft, setDefaultShopDomainDraft] = useState("");
  const [storefrontAccessTokenDraft, setStorefrontAccessTokenDraft] = useState("");
  const [shopifySyncShopDomain, setShopifySyncShopDomain] = useState("");
  const [themeSyncDesignSystemId, setThemeSyncDesignSystemId] = useState("");
  const [themeSyncThemeName, setThemeSyncThemeName] = useState("futrgroup2-0theme");
  const [themeSyncProductId, setThemeSyncProductId] = useState("");
  const [selectedTemplateDraftId, setSelectedTemplateDraftId] = useState("");
  const [templateImageGenerationGeneralContextInput, setTemplateImageGenerationGeneralContextInput] = useState("");
  const [templateImageGenerationSlotContextByPath, setTemplateImageGenerationSlotContextByPath] = useState<
    Record<string, string>
  >({});
  const [templateImageGenerationSlotPathsInput, setTemplateImageGenerationSlotPathsInput] = useState("");
  const [templateDraftImageMapInput, setTemplateDraftImageMapInput] = useState("{}");
  const [templateDraftTextValuesInput, setTemplateDraftTextValuesInput] = useState("{}");
  const [templateDraftEditError, setTemplateDraftEditError] = useState<string | null>(null);
  const [activeTemplateBuildJobId, setActiveTemplateBuildJobId] = useState("");
  const [lastHandledTemplateBuildJobId, setLastHandledTemplateBuildJobId] = useState("");
  const [templateAssetUploadProductId, setTemplateAssetUploadProductId] = useState("");
  const [templateAssetSearchQuery, setTemplateAssetSearchQuery] = useState("");
  const [templateSlotAssetQueryByPath, setTemplateSlotAssetQueryByPath] = useState<Record<string, string>>({});
  const [templateAssetPickerImageErrorsByPublicId, setTemplateAssetPickerImageErrorsByPublicId] = useState<Record<string, boolean>>({});
  const [templatePreviewDialogOpen, setTemplatePreviewDialogOpen] = useState(false);
  const [templatePreviewImageMap, setTemplatePreviewImageMap] = useState<Record<string, string>>({});
  const [templatePreviewTextValues, setTemplatePreviewTextValues] = useState<Record<string, string>>({});
  const [templatePreviewImageErrorsByPath, setTemplatePreviewImageErrorsByPath] = useState<Record<string, boolean>>({});
  const [templatePublishResult, setTemplatePublishResult] = useState<ClientShopifyThemeTemplatePublishResponse | null>(null);
  const [themeAuditResult, setThemeAuditResult] = useState<ClientShopifyThemeBrandAuditResponse | null>(null);
  const [policySyncResult, setPolicySyncResult] = useState<ComplianceShopifyPolicySyncResponse | null>(null);
  const logoUploadInputRef = useRef<HTMLInputElement | null>(null);
  const templateAssetUploadInputRef = useRef<HTMLInputElement | null>(null);
  const uploadTemplateProductAssets = useUploadProductAssets(templateAssetUploadProductId || "");
  const { data: activeTemplateBuildJobStatus } = useClientShopifyThemeTemplateBuildJobStatus(
    workspace?.id,
    activeTemplateBuildJobId || undefined,
    { enabled: Boolean(activeTemplateBuildJobId) }
  );

  const designSystemOptions = useMemo(
    () => [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ],
    [designSystems]
  );
  const shopDomainOptions = useMemo(() => {
    const candidates = new Set<string>();
    const addCandidate = (shopDomain: string | null | undefined) => {
      if (typeof shopDomain !== "string") return;
      const normalized = shopDomain.trim().toLowerCase();
      if (!normalized) return;
      candidates.add(normalized);
    };

    addCandidate(shopifyStatus?.selectedShopDomain);
    addCandidate(shopifyStatus?.shopDomain);
    (shopifyStatus?.shopDomains || []).forEach((shopDomain) => addCandidate(shopDomain));

    return Array.from(candidates)
      .sort((a, b) => a.localeCompare(b))
      .map((shopDomain) => ({ label: shopDomain, value: shopDomain }));
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomain, shopifyStatus?.shopDomains]);
  const hasShopifyConnectionTarget = shopDomainOptions.length > 0;
  const shopifyState = shopifyStatus?.state || "error";
  const shopifyStatusTone = useMemo(() => {
    if (shopifyState === "ready") return "success" as const;
    if (shopifyState === "not_connected" || shopifyState === "installed_missing_storefront_token") return "neutral" as const;
    return "danger" as const;
  }, [shopifyState]);
  const shopifyStatusLabel = useMemo(() => {
    if (shopifyState === "ready") return "Ready";
    if (shopifyState === "not_connected") return "Not connected";
    if (shopifyState === "installed_missing_storefront_token") return "Missing token";
    if (shopifyState === "multiple_installations_conflict") return "Store conflict";
    return "Error";
  }, [shopifyState]);
  const shopifyStatusMessage = useMemo(() => {
    if (shopifyStatus?.message) return shopifyStatus.message;
    if (shopifyStatusError && typeof shopifyStatusError === "object" && "message" in shopifyStatusError) {
      const message = (shopifyStatusError as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    const fallbackErrorMessage = String(shopifyStatusError ?? "").trim();
    if (fallbackErrorMessage) return fallbackErrorMessage;
    return "Checking Shopify connection status.";
  }, [shopifyStatus?.message, shopifyStatusError]);
  const isShopifyConnectionMutating =
    createShopifyInstallUrl.isPending ||
    updateShopifyInstallation.isPending ||
    disconnectShopifyInstallation.isPending ||
    setDefaultShop.isPending;
  const activeTemplateBuildJobState = activeTemplateBuildJobStatus?.status || null;
  const isTemplateBuildJobRunning =
    activeTemplateBuildJobState === "queued" || activeTemplateBuildJobState === "running";

  useEffect(() => {
    setPreviewDesignSystemId("");
    setVarsFilter("");
    setLogoErrored(false);
    setSelectedLogoPublicId("");
    setShopifyShopDomainDraft("");
    setDefaultShopDomainDraft("");
    setStorefrontAccessTokenDraft("");
    setShopifySyncShopDomain("");
    setThemeSyncDesignSystemId("");
    setThemeSyncThemeName("futrgroup2-0theme");
    setThemeSyncProductId("");
    setSelectedTemplateDraftId("");
    setTemplateImageGenerationGeneralContextInput("");
    setTemplateImageGenerationSlotContextByPath({});
    setTemplateImageGenerationSlotPathsInput("");
    setTemplateDraftImageMapInput("{}");
    setTemplateDraftTextValuesInput("{}");
    setTemplateDraftEditError(null);
    setActiveTemplateBuildJobId("");
    setLastHandledTemplateBuildJobId("");
    setTemplateAssetUploadProductId("");
    setTemplateAssetSearchQuery("");
    setTemplateSlotAssetQueryByPath({});
    setTemplateAssetPickerImageErrorsByPublicId({});
    setTemplatePreviewDialogOpen(false);
    setTemplatePreviewImageMap({});
    setTemplatePreviewTextValues({});
    setTemplatePreviewImageErrorsByPath({});
    setTemplatePublishResult(null);
    setThemeAuditResult(null);
    setPolicySyncResult(null);
  }, [workspace?.id]);

  useEffect(() => {
    const connectedShopDomainCandidates = [
      shopifyStatus?.selectedShopDomain,
      shopifyStatus?.shopDomain,
      ...(shopifyStatus?.shopDomains || []),
    ];
    const nextConnectedShopDomain =
      connectedShopDomainCandidates.find(
        (candidate): candidate is string => typeof candidate === "string" && Boolean(candidate.trim())
      ) || "";
    if (!nextConnectedShopDomain) return;
    setShopifyShopDomainDraft((current) => (current.trim() ? current : nextConnectedShopDomain));
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomain, shopifyStatus?.shopDomains]);

  useEffect(() => {
    if (!shopifyStatus?.shopDomains?.length) return;
    setDefaultShopDomainDraft((current) => {
      if (current.trim()) return current;
      if (shopifyStatus.selectedShopDomain) return shopifyStatus.selectedShopDomain;
      return shopifyStatus.shopDomains[0] || "";
    });
  }, [shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomains]);

  useEffect(() => {
    if (!shopDomainOptions.length) {
      setShopifySyncShopDomain("");
      return;
    }
    const resolveNextShopDomain = (current: string) => {
      if (current && shopDomainOptions.some((option) => option.value === current)) return current;
      const selectedShopDomain = shopifyStatus?.selectedShopDomain?.trim().toLowerCase();
      if (selectedShopDomain && shopDomainOptions.some((option) => option.value === selectedShopDomain)) {
        return selectedShopDomain;
      }
      const readyShopDomain = shopifyStatus?.shopDomain?.trim().toLowerCase();
      if (readyShopDomain && shopDomainOptions.some((option) => option.value === readyShopDomain)) {
        return readyShopDomain;
      }
      return shopDomainOptions[0]?.value || "";
    };
    setShopifySyncShopDomain(resolveNextShopDomain);
  }, [shopDomainOptions, shopifyStatus?.selectedShopDomain, shopifyStatus?.shopDomain]);

  useEffect(() => {
    if (!designSystems.length) return;
    setPreviewDesignSystemId((current) => {
      if (current) return current;
      const active = client?.design_system_id || "";
      return active || designSystems[0]?.id || "";
    });
  }, [client?.design_system_id, designSystems]);

  useEffect(() => {
    if (!designSystems.length) {
      setThemeSyncDesignSystemId("");
      return;
    }
    setThemeSyncDesignSystemId((current) => {
      if (current && designSystems.some((ds) => ds.id === current)) return current;
      return "";
    });
  }, [client?.design_system_id, designSystems]);

  const templateDraftOptions = useMemo(
    () =>
      shopifyThemeTemplateDrafts.map((draft) => ({
        label: `${draft.themeName} · v${draft.latestVersion?.versionNumber ?? 0}`,
        value: draft.id,
      })),
    [shopifyThemeTemplateDrafts]
  );

  useEffect(() => {
    if (!shopifyThemeTemplateDrafts.length) {
      setSelectedTemplateDraftId("");
      return;
    }
    setSelectedTemplateDraftId((current) => {
      if (current && shopifyThemeTemplateDrafts.some((draft) => draft.id === current)) return current;
      return shopifyThemeTemplateDrafts[0]?.id || "";
    });
  }, [shopifyThemeTemplateDrafts]);

  const selectedTemplateDraft = useMemo(
    () => shopifyThemeTemplateDrafts.find((draft) => draft.id === selectedTemplateDraftId) ?? null,
    [shopifyThemeTemplateDrafts, selectedTemplateDraftId]
  );

  useEffect(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) {
      setTemplateDraftImageMapInput("{}");
      setTemplateDraftTextValuesInput("{}");
      setTemplateImageGenerationGeneralContextInput("");
      setTemplateImageGenerationSlotContextByPath({});
      setTemplateDraftEditError(null);
      return;
    }
    setTemplateDraftImageMapInput(
      JSON.stringify(latestVersion.data.componentImageAssetMap || {}, null, 2)
    );
    setTemplateDraftTextValuesInput(
      JSON.stringify(latestVersion.data.componentTextValues || {}, null, 2)
    );
    const metadata = latestVersion.data.metadata || {};
    const metadataGeneralContextRaw = metadata["imagePromptGeneralContext"];
    const metadataGeneralContext =
      typeof metadataGeneralContextRaw === "string"
        ? normalizePromptContextValue(metadataGeneralContextRaw)
        : "";
    const metadataCustomSlotContext = readPromptContextMap(
      metadata["imagePromptCustomSlotContextByPath"]
    );
    setTemplateImageGenerationGeneralContextInput(
      metadataGeneralContext || templateImageGenerationDefaultGeneralContext
    );
    setTemplateImageGenerationSlotContextByPath(metadataCustomSlotContext);
    setTemplateImageGenerationSlotPathsInput("");
    setTemplateDraftEditError(null);
    setTemplateAssetSearchQuery("");
    setTemplateSlotAssetQueryByPath({});
    setTemplateAssetPickerImageErrorsByPublicId({});
  }, [selectedTemplateDraft?.id, selectedTemplateDraft?.latestVersion?.id]);

  useEffect(() => {
    if (!workspaceProducts.length) {
      setTemplateAssetUploadProductId("");
      return;
    }
    setTemplateAssetUploadProductId((current) => {
      if (current && workspaceProducts.some((product) => product.id === current)) return current;
      const draftProductId =
        selectedTemplateDraft?.productId ||
        selectedTemplateDraft?.latestVersion?.data.productId ||
        themeSyncProductId.trim();
      if (draftProductId && workspaceProducts.some((product) => product.id === draftProductId)) {
        return draftProductId;
      }
      return workspaceProducts[0]?.id || "";
    });
  }, [
    workspaceProducts,
    selectedTemplateDraft?.id,
    selectedTemplateDraft?.productId,
    selectedTemplateDraft?.latestVersion?.data.productId,
    themeSyncProductId,
  ]);

  useEffect(() => {
    const statusPayload = activeTemplateBuildJobStatus;
    if (!statusPayload) return;
    if (!activeTemplateBuildJobId || statusPayload.jobId !== activeTemplateBuildJobId) return;
    if (lastHandledTemplateBuildJobId === statusPayload.jobId) return;

    if (statusPayload.status === "succeeded") {
      if (!statusPayload.result) return;
      const response = statusPayload.result;
      setSelectedTemplateDraftId(response.draft.id);
      setTemplateDraftImageMapInput(
        JSON.stringify(response.version.data.componentImageAssetMap || {}, null, 2)
      );
      setTemplateDraftTextValuesInput(
        JSON.stringify(response.version.data.componentTextValues || {}, null, 2)
      );
      setTemplateDraftEditError(null);
      setLastHandledTemplateBuildJobId(statusPayload.jobId);
      setActiveTemplateBuildJobId("");
      toast.success(
        `Built template draft v${response.version.versionNumber} for ${response.draft.themeName}`
      );
      return;
    }

    if (statusPayload.status === "failed") {
      const errorMessage = statusPayload.error?.trim() || "Shopify template build failed.";
      setLastHandledTemplateBuildJobId(statusPayload.jobId);
      setActiveTemplateBuildJobId("");
      toast.error(errorMessage);
    }
  }, [
    activeTemplateBuildJobId,
    activeTemplateBuildJobStatus,
    lastHandledTemplateBuildJobId,
  ]);

  const previewDesignSystem = useMemo(
    () => designSystems.find((ds) => ds.id === previewDesignSystemId) ?? null,
    [designSystems, previewDesignSystemId]
  );
  const previewTokens = previewDesignSystem?.tokens;
  const previewCssVars = useMemo(() => normalizeCssVars(previewTokens), [previewTokens]);
  const previewCssVarEntries = useMemo(
    () => Object.entries(previewCssVars).sort(([a], [b]) => a.localeCompare(b)),
    [previewCssVars]
  );
  const previewFilteredCssVarEntries = useMemo(() => {
    const term = varsFilter.trim().toLowerCase();
    if (!term) return previewCssVarEntries;
    return previewCssVarEntries.filter(([key, value]) => {
      const hay = `${key} ${value}`.toLowerCase();
      return hay.includes(term);
    });
  }, [previewCssVarEntries, varsFilter]);

  const previewBrand = useMemo(() => normalizeBrand(previewTokens), [previewTokens]);
  const previewFontUrls = useMemo(() => normalizeFontUrls(previewTokens), [previewTokens]);

  useEffect(() => {
    setLogoErrored(false);
  }, [previewBrand.logoAssetPublicId, previewDesignSystemId]);

  useEffect(() => {
    setSelectedLogoPublicId(previewBrand.logoAssetPublicId || "");
  }, [previewBrand.logoAssetPublicId, previewDesignSystemId]);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const publicAssetBaseUrl = apiBaseUrl?.replace(/\/$/, "");
  const productById = useMemo(
    () => new Map(workspaceProducts.map((product) => [product.id, product])),
    [workspaceProducts]
  );
  const templateAssetUploadProductOptions = useMemo(
    () =>
      workspaceProducts.map((product) => ({
        label: product.title,
        value: product.id,
      })),
    [workspaceProducts]
  );
  const workspaceProductImageAssets = useMemo(
    () =>
      workspaceImageAssets
        .filter((asset) => asset.product_id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [workspaceImageAssets]
  );
  const workspaceProductImageAssetEntries = useMemo(
    () =>
      workspaceProductImageAssets.map((asset) => {
        const productTitle = asset.product_id ? productById.get(asset.product_id)?.title : undefined;
        const createdAt = new Date(asset.created_at);
        const createdAtLabel = Number.isNaN(createdAt.getTime())
          ? asset.created_at
          : createdAt.toLocaleDateString();
        const dimensions =
          typeof asset.width === "number" && typeof asset.height === "number"
            ? `${asset.width}x${asset.height}`
            : "size unknown";
        const tagsLabel = asset.tags?.length ? asset.tags.join(", ") : "";
        const optionLabel = `${productTitle || "Unknown product"} · ${asset.public_id.slice(0, 8)} · ${dimensions} · ${createdAtLabel}`;
        const searchText = [
          productTitle || "",
          asset.product_id || "",
          asset.public_id,
          dimensions,
          asset.status,
          asset.file_status || "",
          asset.format,
          tagsLabel,
        ]
          .join(" ")
          .toLowerCase();
        return {
          asset,
          productTitle: productTitle || "Unknown product",
          createdAtLabel,
          dimensions,
          tagsLabel,
          optionLabel,
          searchText,
        };
      }),
    [productById, workspaceProductImageAssets]
  );
  const normalizedTemplateAssetSearchQuery = templateAssetSearchQuery.trim().toLowerCase();
  const filteredWorkspaceProductImageAssetEntries = useMemo(() => {
    if (!normalizedTemplateAssetSearchQuery) return workspaceProductImageAssetEntries;
    return workspaceProductImageAssetEntries.filter((entry) =>
      entry.searchText.includes(normalizedTemplateAssetSearchQuery)
    );
  }, [workspaceProductImageAssetEntries, normalizedTemplateAssetSearchQuery]);
  const workspaceProductImageAssetByPublicId = useMemo(
    () => new Map(workspaceProductImageAssetEntries.map((entry) => [entry.asset.public_id, entry])),
    [workspaceProductImageAssetEntries]
  );
  const previewLogoSrc =
    previewBrand.logoAssetPublicId && apiBaseUrl
      ? `${apiBaseUrl.replace(/\/$/, "")}/public/assets/${previewBrand.logoAssetPublicId}`
      : undefined;
  const parsedTemplateDraftImageMapResult = useMemo(
    () => parseStringMap(templateDraftImageMapInput, "Image map"),
    [templateDraftImageMapInput]
  );
  const parsedTemplateDraftImageMap = parsedTemplateDraftImageMapResult.value || {};
  const parsedTemplateDraftTextValuesResult = useMemo(
    () => parseStringMap(templateDraftTextValuesInput, "Text values"),
    [templateDraftTextValuesInput]
  );
  const parsedTemplateDraftTextValues = parsedTemplateDraftTextValuesResult.value || {};
  const templateImageSlotReadableLabelByPath = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return new Map<string, string>();
    return buildImageSlotReadableLabelMap(latestVersion.data.imageSlots);
  }, [selectedTemplateDraft?.latestVersion?.id]);
  const templateTextSlotReadableLabelByPath = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return new Map<string, string>();
    return buildTextSlotReadableLabelMap(latestVersion.data.textSlots);
  }, [selectedTemplateDraft?.latestVersion?.id]);
  const templateImageGenerationProduct = useMemo(() => {
    const draftProductId =
      selectedTemplateDraft?.latestVersion?.data.productId ||
      selectedTemplateDraft?.productId ||
      templateAssetUploadProductId ||
      themeSyncProductId.trim() ||
      "";
    if (!draftProductId) return null;
    return productById.get(draftProductId) || null;
  }, [
    selectedTemplateDraft?.id,
    selectedTemplateDraft?.latestVersion?.id,
    selectedTemplateDraft?.latestVersion?.data.productId,
    selectedTemplateDraft?.productId,
    templateAssetUploadProductId,
    themeSyncProductId,
    productById,
  ]);
  const templateImageGenerationDefaultGeneralContext = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return "";
    return buildTemplateImageGenerationGeneralContext(
      latestVersion.data,
      templateImageGenerationProduct
    );
  }, [selectedTemplateDraft?.latestVersion?.id, templateImageGenerationProduct]);
  const templateImageGenerationDefaultSlotContextByPath = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return {} as Record<string, string>;
    return buildTemplateImageGenerationSlotContextByPath(
      latestVersion.data,
      templateImageSlotReadableLabelByPath
    );
  }, [selectedTemplateDraft?.latestVersion?.id, templateImageSlotReadableLabelByPath]);
  const templateImageGenerationEffectiveSlotContextByPath = useMemo(
    () => ({
      ...templateImageGenerationDefaultSlotContextByPath,
      ...templateImageGenerationSlotContextByPath,
    }),
    [templateImageGenerationDefaultSlotContextByPath, templateImageGenerationSlotContextByPath]
  );
  const templatePreviewImageItems = useMemo(() => {
    const latestVersion = selectedTemplateDraft?.latestVersion;
    if (!latestVersion) return [];

    const slotByPath = new Map(
      latestVersion.data.imageSlots.map((slot) => [slot.path, slot])
    );
    const seenPaths = new Set<string>();
    const items: Array<{
      path: string;
      assetPublicId: string;
      role?: string;
      recommendedAspect?: string;
      hasKnownSlot: boolean;
    }> = [];

    for (const slot of latestVersion.data.imageSlots) {
      const path = slot.path;
      seenPaths.add(path);
      items.push({
        path,
        assetPublicId: templatePreviewImageMap[path] || "",
        role: slot.role,
        recommendedAspect: slot.recommendedAspect,
        hasKnownSlot: true,
      });
    }

    for (const [path, assetPublicId] of Object.entries(templatePreviewImageMap)) {
      if (seenPaths.has(path)) continue;
      const slot = slotByPath.get(path);
      items.push({
        path,
        assetPublicId,
        role: slot?.role,
        recommendedAspect: slot?.recommendedAspect,
        hasKnownSlot: false,
      });
    }

    return items;
  }, [selectedTemplateDraft?.latestVersion, templatePreviewImageMap]);
  const templatePreviewTextEntries = useMemo(
    () => Object.entries(templatePreviewTextValues).sort(([a], [b]) => a.localeCompare(b)),
    [templatePreviewTextValues]
  );
  const logoAssetOptions = useMemo(
    () =>
      [...logoAssets]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((asset) => {
          const createdAt = new Date(asset.created_at);
          const createdAtLabel = Number.isNaN(createdAt.getTime())
            ? asset.created_at
            : createdAt.toLocaleDateString();
          return {
            label: `${asset.public_id.slice(0, 8)} · ${createdAtLabel}`,
            value: asset.public_id,
          };
        }),
    [logoAssets]
  );

  const applySelectedLogoAsset = () => {
    if (!workspace?.id) return;
    if (!previewDesignSystem) {
      toast.error("Select a design system first.");
      return;
    }
    if (!selectedLogoPublicId) {
      toast.error("Select a logo asset first.");
      return;
    }
    const patched = applyLogoPublicIdToTokens(
      previewDesignSystem.tokens,
      selectedLogoPublicId,
      previewBrand.logoAlt || previewBrand.name || previewDesignSystem.name
    );
    if (!patched.value) {
      toast.error(patched.error || "Unable to update design system logo.");
      return;
    }
    updateDesignSystem.mutate({
      designSystemId: previewDesignSystem.id,
      payload: { tokens: patched.value },
      clientId: workspace.id,
    }, {
      onSuccess: () => setLogoErrored(false),
    });
  };

  const handleConnectShopify = async () => {
    if (!workspace?.id) {
      toast.error("Select a workspace before connecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const response = await createShopifyInstallUrl.mutateAsync({ shopDomain: nextDomain });
    if (!response.installUrl) {
      throw new Error("Install URL is missing from response.");
    }
    window.location.assign(response.installUrl);
  };

  const handleSetStorefrontToken = async () => {
    if (!workspace?.id) {
      toast.error("Select a workspace before updating Shopify installation.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    const nextToken = storefrontAccessTokenDraft.trim();
    if (!nextToken) {
      toast.error("Storefront access token is required.");
      return;
    }
    await updateShopifyInstallation.mutateAsync({
      shopDomain: nextDomain,
      storefrontAccessToken: nextToken,
    });
    setStorefrontAccessTokenDraft("");
    await refetchShopifyStatus();
  };

  const handleSetDefaultShop = async () => {
    if (!workspace?.id) {
      toast.error("Select a workspace before setting default Shopify store.");
      return;
    }
    const nextDomain = defaultShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Select a Shopify shop domain.");
      return;
    }
    await setDefaultShop.mutateAsync({ shopDomain: nextDomain });
    await refetchShopifyStatus();
  };

  const handleDisconnectShopify = async () => {
    if (!workspace?.id) {
      toast.error("Select a workspace before disconnecting Shopify.");
      return;
    }
    const nextDomain = shopifyShopDomainDraft.trim();
    if (!nextDomain) {
      toast.error("Shop domain is required.");
      return;
    }
    await disconnectShopifyInstallation.mutateAsync({ shopDomain: nextDomain });
    setStorefrontAccessTokenDraft("");
    await refetchShopifyStatus();
  };

  const handleBuildShopifyThemeTemplateDraft = async () => {
    if (!workspace?.id) return;
    const cleanedThemeName = themeSyncThemeName.trim();
    const cleanedProductId = themeSyncProductId.trim();
    if (!cleanedThemeName) {
      toast.error("Enter a Shopify theme name.");
      return;
    }
    const payload: {
      draftId?: string;
      designSystemId?: string;
      shopDomain?: string;
      productId?: string;
      themeName: string;
    } = {
      themeName: cleanedThemeName,
    };
    if (selectedTemplateDraftId) payload.draftId = selectedTemplateDraftId;
    if (themeSyncDesignSystemId) payload.designSystemId = themeSyncDesignSystemId;
    if (shopifySyncShopDomain) payload.shopDomain = shopifySyncShopDomain;
    if (cleanedProductId) payload.productId = cleanedProductId;
    try {
      const startResponse = await enqueueShopifyThemeTemplateBuildJob.mutateAsync(payload);
      setLastHandledTemplateBuildJobId("");
      setActiveTemplateBuildJobId(startResponse.jobId);
      toast.success(`Template build job queued (${startResponse.jobId.slice(0, 8)})`);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleSaveTemplateDraftEdits = async () => {
    if (!workspace?.id) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    setTemplateDraftEditError(null);
    try {
      await updateShopifyThemeTemplateDraft.mutateAsync({
        draftId: selectedTemplateDraftId,
        payload: {
          componentImageAssetMap: parsedImageMap.value,
          componentTextValues: parsedTextValues.value,
        },
      });
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleGenerateTemplateDraftImages = async () => {
    if (!workspace?.id) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    const parsedSlotPathList = parseSlotPathList(templateImageGenerationSlotPathsInput);
    if (!parsedSlotPathList.value) {
      setTemplateDraftEditError(parsedSlotPathList.error || "Invalid image generation slot paths.");
      return;
    }
    const payload: {
      draftId: string;
      productId?: string;
      slotPaths?: string[];
      generalContext?: string;
      slotContextByPath?: Record<string, string>;
    } = {
      draftId: selectedTemplateDraftId,
    };
    const explicitProductId = templateAssetUploadProductId.trim() || themeSyncProductId.trim();
    if (explicitProductId) payload.productId = explicitProductId;
    if (parsedSlotPathList.value.length) payload.slotPaths = parsedSlotPathList.value;
    const cleanedGeneralContext = normalizePromptContextValue(
      templateImageGenerationGeneralContextInput
    );
    if (cleanedGeneralContext) {
      payload.generalContext = cleanedGeneralContext;
    }
    if (selectedTemplateDraft.latestVersion) {
      const knownSlotPathSet = new Set(
        selectedTemplateDraft.latestVersion.data.imageSlots.map((slot) => slot.path)
      );
      const nextSlotContextByPath: Record<string, string> = {};
      for (const [path, rawContext] of Object.entries(
        templateImageGenerationSlotContextByPath
      )) {
        if (!knownSlotPathSet.has(path)) continue;
        const cleanedSlotContext = normalizePromptContextValue(rawContext);
        if (!cleanedSlotContext) continue;
        nextSlotContextByPath[path] = cleanedSlotContext;
      }
      if (Object.keys(nextSlotContextByPath).length) {
        payload.slotContextByPath = nextSlotContextByPath;
      }
    }
    setTemplateDraftEditError(null);

    try {
      const response = await generateShopifyThemeTemplateImages.mutateAsync(payload);
      setSelectedTemplateDraftId(response.draft.id);
      setTemplateDraftImageMapInput(
        JSON.stringify(response.version.data.componentImageAssetMap || {}, null, 2)
      );
      setTemplateDraftTextValuesInput(
        JSON.stringify(response.version.data.componentTextValues || {}, null, 2)
      );
      const generatedProductId = response.version.data.productId?.trim();
      if (generatedProductId) {
        setTemplateAssetUploadProductId(generatedProductId);
      }
      setTemplateDraftEditError(null);
      await refetchWorkspaceImageAssets();
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleClearTemplateDraftImageMappings = async () => {
    if (!workspace?.id) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    try {
      await updateShopifyThemeTemplateDraft.mutateAsync({
        draftId: selectedTemplateDraftId,
        payload: {
          componentImageAssetMap: {},
          notes: "Cleared mapped image slots.",
        },
      });
      setTemplateDraftImageMapInput("{}");
      setTemplateSlotAssetQueryByPath({});
      setTemplateAssetPickerImageErrorsByPublicId({});
      setTemplateDraftEditError(null);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleTemplateDraftSlotAssetChange = (path: string, assetPublicId: string) => {
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const nextImageMap = { ...parsedImageMap.value };
    const cleanedAssetPublicId = assetPublicId.trim();
    if (cleanedAssetPublicId) {
      nextImageMap[path] = cleanedAssetPublicId;
    } else {
      delete nextImageMap[path];
    }
    setTemplateDraftImageMapInput(JSON.stringify(nextImageMap, null, 2));
    setTemplateDraftEditError(null);
  };

  const handleTemplateDraftSlotTextValueChange = (path: string, nextValue: string) => {
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    const nextTextValues = { ...parsedTextValues.value };
    if (nextValue.trim()) {
      nextTextValues[path] = nextValue;
    } else {
      delete nextTextValues[path];
    }
    setTemplateDraftTextValuesInput(JSON.stringify(nextTextValues, null, 2));
    setTemplateDraftEditError(null);
  };

  const handleTemplateImageGenerationSlotContextChange = (
    path: string,
    nextValue: string
  ) => {
    setTemplateImageGenerationSlotContextByPath((current) => {
      const next = { ...current };
      const cleanedValue = normalizePromptContextValue(nextValue);
      if (!cleanedValue) {
        delete next[path];
        return next;
      }
      next[path] = nextValue;
      return next;
    });
    setTemplateDraftEditError(null);
  };

  const handleResetTemplateImagePromptContextsToDefault = () => {
    setTemplateImageGenerationGeneralContextInput(
      templateImageGenerationDefaultGeneralContext
    );
    setTemplateImageGenerationSlotContextByPath({});
    setTemplateDraftEditError(null);
  };

  const handleTemplateImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      toast.error("No files selected.");
      event.currentTarget.value = "";
      return;
    }
    if (!templateAssetUploadProductId.trim()) {
      toast.error("Select a product before uploading images.");
      event.currentTarget.value = "";
      return;
    }
    const nonImageFiles = files.filter((file) => !file.type.toLowerCase().startsWith("image/"));
    if (nonImageFiles.length) {
      toast.error("Only image files are allowed in this uploader.");
      event.currentTarget.value = "";
      return;
    }
    try {
      await uploadTemplateProductAssets.mutateAsync(files);
      await refetchWorkspaceImageAssets();
    } finally {
      event.currentTarget.value = "";
    }
  };

  const handleOpenTemplatePreview = () => {
    if (!selectedTemplateDraft?.latestVersion) {
      toast.error("Build or select a template draft first.");
      return;
    }
    const parsedImageMap = parseStringMap(templateDraftImageMapInput, "Image map");
    if (!parsedImageMap.value) {
      setTemplateDraftEditError(parsedImageMap.error || "Invalid image map.");
      return;
    }
    const parsedTextValues = parseStringMap(templateDraftTextValuesInput, "Text values");
    if (!parsedTextValues.value) {
      setTemplateDraftEditError(parsedTextValues.error || "Invalid text values.");
      return;
    }
    setTemplateDraftEditError(null);
    setTemplatePreviewImageMap(parsedImageMap.value);
    setTemplatePreviewTextValues(parsedTextValues.value);
    setTemplatePreviewImageErrorsByPath({});
    setTemplatePreviewDialogOpen(true);
  };

  const handlePublishTemplateDraft = async () => {
    if (!workspace?.id) return;
    if (!selectedTemplateDraftId) {
      toast.error("Select a template draft first.");
      return;
    }
    try {
      const response = await publishShopifyThemeTemplateDraft.mutateAsync({
        draftId: selectedTemplateDraftId,
      });
      setTemplatePublishResult(response);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleAuditShopifyThemeBrand = async () => {
    if (!workspace?.id) return;
    const cleanedThemeName = themeSyncThemeName.trim();
    if (!cleanedThemeName) {
      toast.error("Enter a Shopify theme name.");
      return;
    }
    const payload: { designSystemId?: string; shopDomain?: string; themeName: string } = {
      themeName: cleanedThemeName,
    };
    if (themeSyncDesignSystemId) payload.designSystemId = themeSyncDesignSystemId;
    if (shopifySyncShopDomain) payload.shopDomain = shopifySyncShopDomain;
    try {
      const response = await auditShopifyThemeBrand.mutateAsync(payload);
      setThemeAuditResult(response);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleSyncCompliancePolicyPages = async () => {
    if (!workspace?.id) return;
    const payload = shopifySyncShopDomain ? { shopDomain: shopifySyncShopDomain } : {};
    try {
      const response = await syncCompliancePolicyPages.mutateAsync(payload);
      setPolicySyncResult(response);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const handleLogoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    if (!workspace?.id) {
      toast.error("Select a workspace first.");
      return;
    }
    if (!previewDesignSystem) {
      toast.error("Select a design system first.");
      return;
    }
    try {
      const uploaded = await uploadDesignSystemLogo.mutateAsync({
        designSystemId: previewDesignSystem.id,
        clientId: workspace.id,
        file,
      });
      setSelectedLogoPublicId(uploaded.publicId);
      setLogoErrored(false);
    } catch {
      // Error toast is emitted by the mutation hook.
    }
  };

  const coreColorKeys = useMemo(
    () => [
      "--color-page-bg",
      "--color-brand",
      "--color-bg",
      "--color-text",
      "--color-muted",
      "--color-border",
      "--color-soft",
      "--focus-outline-color",
      "--color-cta",
      "--color-cta-text",
      "--color-cta-shell",
      "--color-cta-icon",
      "--hero-bg",
      "--marquee-bg",
      "--wall-button-bg",
      "--reviews-card-bg",
    ],
    []
  );
  const coreColors = useMemo(
    () =>
      coreColorKeys
        .map((key) => ({ key, value: previewCssVars[key] }))
        .filter((entry) => typeof entry.value === "string" && entry.value),
    [coreColorKeys, previewCssVars]
  );
  const allColorVars = useMemo(
    () =>
      previewCssVarEntries.filter(([key, value]) => {
        const keyLower = key.toLowerCase();
        const keySignals =
          keyLower.includes("color") ||
          keyLower.includes("-bg") ||
          keyLower.includes("bg") ||
          keyLower.includes("border") ||
          keyLower.includes("text") ||
          keyLower.includes("foreground") ||
          keyLower.includes("muted") ||
          keyLower.includes("overlay") ||
          keyLower.includes("ring") ||
          keyLower.includes("outline");
        return keySignals && isColorLikeCssValue(value);
      }),
    [previewCssVarEntries]
  );

  const openCreate = () => {
    setEditing(null);
    setDraftName("");
    setDraftTokens(formatTokens(DEFAULT_TOKENS));
    setTokensError(null);
    setDialogOpen(true);
  };

  const openEdit = (ds: DesignSystem) => {
    setEditing(ds);
    setDraftName(ds.name);
    setDraftTokens(formatTokens(ds.tokens));
    setTokensError(null);
    setDialogOpen(true);
  };

  const copyToClipboard = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error(`Unable to copy ${label.toLowerCase()}`);
    }
  };

  const handleSave = () => {
    if (!workspace?.id) return;
    const parsed = parseTokens(draftTokens);
    if (!parsed.value) {
      setTokensError(parsed.error || "Invalid tokens JSON.");
      return;
    }
    if (editing) {
      updateDesignSystem.mutate(
        {
          designSystemId: editing.id,
          clientId: workspace.id,
          payload: { name: draftName || editing.name, tokens: parsed.value },
        },
        { onSuccess: () => setDialogOpen(false) }
      );
      return;
    }
    createDesignSystem.mutate(
      { name: draftName || "New design system", tokens: parsed.value, clientId: workspace.id },
      { onSuccess: () => setDialogOpen(false) }
    );
  };

  if (!workspace) {
    return (
      <div className="space-y-4">
        <PageHeader title="Brand design system" description="Select a workspace to manage brand tokens." />
        <div className="ds-card ds-card--md ds-card--empty text-center text-sm">
          Choose a workspace from the sidebar to manage its brand styles.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Brand design system"
        description={workspace.industry ? `${workspace.name} · ${workspace.industry}` : workspace.name}
        actions={
          <Button size="sm" onClick={openCreate}>
            New design system
          </Button>
        }
      />

      <div className="ds-card ds-card--md space-y-3">
        <div className="text-sm font-semibold text-content">Workspace default</div>
        <div className="grid gap-2 md:grid-cols-[280px_minmax(0,1fr)]">
          <Select
            value={client?.design_system_id || ""}
            onValueChange={(value) => {
              if (!workspace.id) return;
              updateClient.mutate({ clientId: workspace.id, payload: { designSystemId: value || null } });
            }}
            options={designSystemOptions}
            disabled={updateClient.isPending || !designSystems.length}
          />
          <div className="text-xs text-content-muted md:flex md:items-center">
            This design system powers funnel pages unless a funnel or page overrides it.
          </div>
        </div>
      </div>

      <div className="ds-card ds-card--md space-y-4">
        <div>
          <div className="text-sm font-semibold text-content">Shopify sync</div>
          <div className="text-xs text-content-muted">
            Sync both theme brand tokens and compliance policy pages to Shopify from one place.
          </div>
        </div>

        <div className="rounded-md border border-divider p-3 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Shopify connection</div>
              <div className="text-xs text-content-muted">
                Connect the store and verify setup before running theme or policy sync.
              </div>
            </div>
            <Badge tone={shopifyStatusTone}>{isLoadingShopifyStatus ? "Checking…" : shopifyStatusLabel}</Badge>
          </div>
          <div className="text-xs text-content-muted">{shopifyStatusMessage}</div>
          {shopifyStatus?.missingScopes?.length ? (
            <div className="text-xs text-danger">Missing scopes: {shopifyStatus.missingScopes.join(", ")}</div>
          ) : null}
          {shopifyStatus?.shopDomains?.length ? (
            <div className="text-xs text-content-muted">Connected stores: {shopifyStatus.shopDomains.join(", ")}</div>
          ) : null}
          {shopifyState === "multiple_installations_conflict" && shopifyStatus?.shopDomains?.length ? (
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
              <select
                className="w-full rounded-md border border-input-border bg-input px-3 py-2 text-sm text-content shadow-sm"
                value={defaultShopDomainDraft}
                onChange={(e) => setDefaultShopDomainDraft(e.target.value)}
                disabled={setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
              >
                {shopifyStatus.shopDomains.map((shopDomain) => (
                  <option key={shopDomain} value={shopDomain}>
                    {shopDomain}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void handleSetDefaultShop()}
                disabled={!defaultShopDomainDraft.trim() || setDefaultShop.isPending || disconnectShopifyInstallation.isPending}
              >
                {setDefaultShop.isPending ? "Saving…" : "Set default shop"}
              </Button>
            </div>
          ) : null}
          {hasShopifyConnectionTarget ? (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void refetchShopifyStatus()}
                disabled={isLoadingShopifyStatus || isShopifyConnectionMutating}
              >
                Refresh
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => void handleDisconnectShopify()}
                disabled={!workspace?.id || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
              >
                {disconnectShopifyInstallation.isPending ? "Disconnecting…" : "Disconnect Shopify"}
              </Button>
            </div>
          ) : (
            <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto]">
              <Input
                placeholder="example-shop.myshopify.com"
                value={shopifyShopDomainDraft}
                onChange={(e) => setShopifyShopDomainDraft(e.target.value)}
                disabled={isShopifyConnectionMutating}
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void refetchShopifyStatus()}
                disabled={isLoadingShopifyStatus || isShopifyConnectionMutating}
              >
                Refresh
              </Button>
              <Button
                size="sm"
                onClick={() => void handleConnectShopify()}
                disabled={!workspace?.id || !shopifyShopDomainDraft.trim() || isShopifyConnectionMutating}
              >
                {createShopifyInstallUrl.isPending ? "Redirecting…" : "Connect Shopify"}
              </Button>
            </div>
          )}
          <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
            <Input
              type="password"
              placeholder="Storefront access token"
              value={storefrontAccessTokenDraft}
              onChange={(e) => setStorefrontAccessTokenDraft(e.target.value)}
              disabled={isShopifyConnectionMutating}
            />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void handleSetStorefrontToken()}
              disabled={
                !workspace?.id ||
                !shopifyShopDomainDraft.trim() ||
                !storefrontAccessTokenDraft.trim() ||
                isShopifyConnectionMutating
              }
            >
              {updateShopifyInstallation.isPending ? "Saving…" : "Set storefront token"}
            </Button>
          </div>
        </div>

        <div className="rounded-md border border-divider p-3 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Theme template workflow</div>
              <div className="text-xs text-content-muted">
                Job 1 builds an editable template draft in mOS. Job 2 publishes the approved draft to Shopify.
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  void handleAuditShopifyThemeBrand();
                }}
                disabled={
                  auditShopifyThemeBrand.isPending ||
                  !hasShopifyConnectionTarget ||
                  !themeSyncThemeName.trim()
                }
              >
                {auditShopifyThemeBrand.isPending ? "Auditing…" : "Audit theme"}
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  void handleBuildShopifyThemeTemplateDraft();
                }}
                disabled={
                  enqueueShopifyThemeTemplateBuildJob.isPending ||
                  isTemplateBuildJobRunning ||
                  !hasShopifyConnectionTarget ||
                  !themeSyncThemeName.trim()
                }
              >
                {enqueueShopifyThemeTemplateBuildJob.isPending
                  ? "Queueing…"
                  : isTemplateBuildJobRunning
                    ? "Building…"
                    : "Job 1: Build template draft"}
              </Button>
            </div>
          </div>
          {activeTemplateBuildJobStatus ? (
            <div className="rounded-md border border-divider bg-surface-2 px-3 py-2 text-xs text-content-muted">
              Build job <span className="font-mono text-content">{activeTemplateBuildJobStatus.jobId}</span>:{" "}
              <span className="font-semibold text-content">{activeTemplateBuildJobStatus.status}</span>
              {activeTemplateBuildJobStatus.progress?.message ? (
                <span> · {activeTemplateBuildJobStatus.progress.message}</span>
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-2 md:grid-cols-[280px_minmax(0,1fr)]">
            <Input
              value={themeSyncThemeName}
              onChange={(event) => setThemeSyncThemeName(event.target.value)}
              placeholder="futrgroup2-0theme"
            />
            <div className="text-xs text-content-muted md:flex md:items-center">
              Target Shopify theme name. This is used when building or auditing drafts.
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-[280px_minmax(0,1fr)]">
            <Input
              value={themeSyncProductId}
              onChange={(event) => setThemeSyncProductId(event.target.value)}
              placeholder="Optional product ID"
            />
            <div className="text-xs text-content-muted md:flex md:items-center">
              Optional product ID for product-specific image/text planning in Job 1.
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-[280px_minmax(0,1fr)]">
            <Select
              value={themeSyncDesignSystemId}
              onValueChange={(value) => setThemeSyncDesignSystemId(value)}
              options={
                designSystems.length
                  ? [
                      { label: "Workspace default", value: "" },
                      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
                    ]
                  : [{ label: isLoading ? "Loading design systems…" : "No design systems", value: "" }]
              }
              disabled={!designSystems.length}
            />
            <div className="text-xs text-content-muted md:flex md:items-center">
              Leave as workspace default, or pick a specific design system override for Job 1.
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-[280px_minmax(0,1fr)]">
            <Select
              value={selectedTemplateDraftId}
              onValueChange={(value) => setSelectedTemplateDraftId(value)}
              options={
                templateDraftOptions.length
                  ? templateDraftOptions
                  : [{ label: "No template drafts yet", value: "" }]
              }
              disabled={!templateDraftOptions.length}
            />
            <div className="text-xs text-content-muted md:flex md:items-center">
              Select a draft to review/edit in mOS before publishing.
            </div>
          </div>

          {selectedTemplateDraft?.latestVersion ? (
            <div className="space-y-3 rounded-md border border-divider p-3">
              <div className="text-xs text-content-muted">
                Editing draft <span className="font-semibold text-content">{selectedTemplateDraft.themeName}</span> · v
                <span className="font-semibold text-content">{selectedTemplateDraft.latestVersion.versionNumber}</span>
              </div>
              {/*
              <div className="space-y-3 rounded-md border border-divider p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-content">Image asset picker</div>
                    <div className="text-xs text-content-muted">
                      Search workspace product images, then map each template image slot.
                    </div>
                  </div>
                  <div className="w-full space-y-2 lg:w-auto lg:min-w-[520px]">
                    <Input
                      value={templateAssetSearchQuery}
                      onChange={(event) => setTemplateAssetSearchQuery(event.target.value)}
                      placeholder="Search by product, asset ID, size, status, tag"
                    />
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                      <Select
                        value={templateAssetUploadProductId}
                        onValueChange={(value) => setTemplateAssetUploadProductId(value)}
                        options={
                          templateAssetUploadProductOptions.length
                            ? templateAssetUploadProductOptions
                            : [{ label: "No products in this workspace", value: "" }]
                        }
                        disabled={!templateAssetUploadProductOptions.length || uploadTemplateProductAssets.isPending}
                      />
                      <div className="flex items-center gap-2">
                        <input
                          ref={templateAssetUploadInputRef}
                          className="hidden"
                          type="file"
                          multiple
                          accept="image/*"
                          onChange={handleTemplateImageUpload}
                        />
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => templateAssetUploadInputRef.current?.click()}
                          disabled={!templateAssetUploadProductOptions.length || uploadTemplateProductAssets.isPending}
                        >
                          {uploadTemplateProductAssets.isPending ? "Uploading…" : "Upload images"}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                {!publicAssetBaseUrl ? (
                  <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                    Missing `VITE_API_BASE_URL`; picker image previews cannot be loaded.
                  </div>
                ) : null}

                {parsedTemplateDraftImageMapResult.error ? (
                  <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                    {parsedTemplateDraftImageMapResult.error}
                  </div>
                ) : isLoadingWorkspaceImageAssets ? (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    Loading product image assets…
                  </div>
                ) : !workspaceProductImageAssetEntries.length ? (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    No product image assets were found for this workspace.
                  </div>
                ) : !selectedTemplateDraft.latestVersion.data.imageSlots.length ? (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    This draft has no image slots to map.
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="text-xs text-content-muted">
                      Showing{" "}
                      <span className="font-semibold text-content">{filteredWorkspaceProductImageAssetEntries.length}</span> of{" "}
                      <span className="font-semibold text-content">{workspaceProductImageAssetEntries.length}</span> product image assets.
                    </div>
                    <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                        {selectedTemplateDraft.latestVersion.data.imageSlots.map((slot) => {
                          const selectedAssetPublicId = parsedTemplateDraftImageMap[slot.path] || "";
                          const selectedAssetEntry =
                            selectedAssetPublicId
                              ? workspaceProductImageAssetByPublicId.get(selectedAssetPublicId)
                              : undefined;
                          const readableSlotLabel =
                            templateImageSlotReadableLabelByPath.get(slot.path) ||
                            humanizeSlotToken(slot.path.split(".").pop() || slot.path);
                          const slotAssetQuery = templateSlotAssetQueryByPath[slot.path] ?? selectedAssetPublicId;
                          const normalizedSlotAssetQuery = slotAssetQuery.trim().toLowerCase();
                          const slotMatchEntries = normalizedSlotAssetQuery
                            ? workspaceProductImageAssetEntries
                                .filter((entry) => entry.searchText.includes(normalizedSlotAssetQuery))
                                .slice(0, 6)
                            : [];
                          const selectedImageUrl =
                            publicAssetBaseUrl && selectedAssetPublicId
                              ? `${publicAssetBaseUrl}/public/assets/${selectedAssetPublicId}`
                              : undefined;
                          const selectedImageErrored = Boolean(
                            selectedAssetPublicId && templateAssetPickerImageErrorsByPublicId[selectedAssetPublicId]
                          );
                          return (
                            <div key={slot.path} className="space-y-2 rounded-md border border-border bg-surface p-2">
                              <div className="text-xs font-semibold text-content">{readableSlotLabel}</div>
                              <div className="text-[11px] font-mono break-all text-content">{slot.path}</div>
                              <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                                {slot.role ? <span>role: {slot.role}</span> : null}
                                {slot.recommendedAspect ? <span>aspect: {slot.recommendedAspect}</span> : null}
                              </div>
                              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
                                <Input
                                  value={slotAssetQuery}
                                  onChange={(event) => {
                                    const nextValue = event.target.value;
                                    setTemplateSlotAssetQueryByPath((current) => ({
                                      ...current,
                                      [slot.path]: nextValue,
                                    }));
                                    setTemplateDraftEditError(null);
                                  }}
                                  placeholder="Type asset UUID/public_id or product name"
                                />
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => {
                                    const normalizedQuery = slotAssetQuery.trim().toLowerCase();
                                    if (!normalizedQuery) {
                                      handleTemplateDraftSlotAssetChange(slot.path, "");
                                      setTemplateSlotAssetQueryByPath((current) => ({
                                        ...current,
                                        [slot.path]: "",
                                      }));
                                      return;
                                    }
                                    const exactPublicIdMatch = workspaceProductImageAssetEntries.find(
                                      (entry) => entry.asset.public_id.toLowerCase() === normalizedQuery
                                    );
                                    if (exactPublicIdMatch) {
                                      handleTemplateDraftSlotAssetChange(slot.path, exactPublicIdMatch.asset.public_id);
                                      setTemplateSlotAssetQueryByPath((current) => ({
                                        ...current,
                                        [slot.path]: exactPublicIdMatch.asset.public_id,
                                      }));
                                      return;
                                    }
                                    if (slotMatchEntries.length === 1) {
                                      handleTemplateDraftSlotAssetChange(slot.path, slotMatchEntries[0].asset.public_id);
                                      setTemplateSlotAssetQueryByPath((current) => ({
                                        ...current,
                                        [slot.path]: slotMatchEntries[0].asset.public_id,
                                      }));
                                      return;
                                    }
                                    if (!slotMatchEntries.length) {
                                      setTemplateDraftEditError(`No asset matched "${slotAssetQuery.trim()}".`);
                                      return;
                                    }
                                    setTemplateDraftEditError("Multiple assets matched. Select one from suggestions below.");
                                  }}
                                >
                                  Apply
                                </Button>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => {
                                    handleTemplateDraftSlotAssetChange(slot.path, "");
                                    setTemplateSlotAssetQueryByPath((current) => ({
                                      ...current,
                                      [slot.path]: "",
                                    }));
                                  }}
                                >
                                  Clear
                                </Button>
                              </div>
                              {normalizedSlotAssetQuery ? (
                                slotMatchEntries.length ? (
                                  <div className="space-y-1 rounded-md border border-border bg-surface-2 p-2">
                                    <div className="text-[11px] font-semibold text-content">
                                      Matches ({slotMatchEntries.length})
                                    </div>
                                    {slotMatchEntries.map((entry) => (
                                      <button
                                        key={`${slot.path}-${entry.asset.id}`}
                                        type="button"
                                        className={cn(
                                          "w-full rounded border px-2 py-1 text-left text-[11px] transition",
                                          "border-border bg-surface hover:bg-surface-2"
                                        )}
                                        onClick={() => {
                                          handleTemplateDraftSlotAssetChange(slot.path, entry.asset.public_id);
                                          setTemplateSlotAssetQueryByPath((current) => ({
                                            ...current,
                                            [slot.path]: entry.asset.public_id,
                                          }));
                                        }}
                                      >
                                        <div className="truncate font-semibold text-content">{entry.productTitle}</div>
                                        <div className="font-mono text-content-muted">{entry.asset.public_id}</div>
                                      </button>
                                    ))}
                                  </div>
                                ) : (
                                  <div className="text-[11px] text-danger">No assets match this input.</div>
                                )
                              ) : null}
                              {selectedAssetPublicId ? (
                                <div className="space-y-1 rounded-md border border-border bg-surface-2 p-2">
                                  <div className="rounded-md border border-border bg-white p-1">
                                    {selectedImageUrl && !selectedImageErrored ? (
                                      <img
                                        src={selectedImageUrl}
                                        alt={slot.path}
                                        className="h-28 w-full rounded object-contain"
                                        onError={() =>
                                          setTemplateAssetPickerImageErrorsByPublicId((current) => ({
                                            ...current,
                                            [selectedAssetPublicId]: true,
                                          }))
                                        }
                                      />
                                    ) : (
                                      <div className="grid h-28 place-items-center text-xs text-content-muted">
                                        Preview unavailable.
                                      </div>
                                    )}
                                  </div>
                                  {selectedAssetEntry ? (
                                    <div className="text-[11px] text-content-muted">
                                      {selectedAssetEntry.productTitle} · {selectedAssetEntry.dimensions} ·{" "}
                                      {selectedAssetEntry.createdAtLabel}
                                    </div>
                                  ) : (
                                    <div className="text-[11px] text-content-muted">
                                      Asset is not in the current workspace product image list.
                                    </div>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>

                      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                        <div className="text-xs font-semibold text-content">Search results</div>
                        {filteredWorkspaceProductImageAssetEntries.length ? (
                          filteredWorkspaceProductImageAssetEntries.map((entry) => {
                            const { asset } = entry;
                            const assetImageUrl = publicAssetBaseUrl
                              ? `${publicAssetBaseUrl}/public/assets/${asset.public_id}`
                              : undefined;
                            const assetImageErrored = Boolean(
                              templateAssetPickerImageErrorsByPublicId[asset.public_id]
                            );
                            return (
                              <div
                                key={asset.id}
                                className="grid grid-cols-[88px_minmax(0,1fr)] gap-2 rounded-md border border-border bg-surface p-2"
                              >
                                <div className="rounded-md border border-border bg-white p-1">
                                  {assetImageUrl && !assetImageErrored ? (
                                    <img
                                      src={assetImageUrl}
                                      alt={asset.public_id}
                                      className="h-20 w-full rounded object-contain"
                                      onError={() =>
                                        setTemplateAssetPickerImageErrorsByPublicId((current) => ({
                                          ...current,
                                          [asset.public_id]: true,
                                        }))
                                      }
                                    />
                                  ) : (
                                    <div className="grid h-20 place-items-center text-[11px] text-content-muted">
                                      No preview
                                    </div>
                                  )}
                                </div>
                                <div className="min-w-0 space-y-1">
                                  <div className="text-xs font-semibold text-content truncate">{entry.productTitle}</div>
                                  <div className="text-[11px] font-mono text-content break-all">
                                    {asset.public_id}
                                  </div>
                                  <div className="text-[11px] text-content-muted">
                                    {entry.dimensions} · {entry.createdAtLabel} · {asset.status}
                                  </div>
                                  {entry.tagsLabel ? (
                                    <div className="text-[11px] text-content-muted truncate">tags: {entry.tagsLabel}</div>
                                  ) : null}
                                </div>
                              </div>
                            );
                          })
                        ) : (
                          <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                            No assets match this search.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              */}
              <div className="space-y-3 rounded-md border border-divider p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold text-content">
                      Image prompt context (experiment)
                    </div>
                    <div className="text-xs text-content-muted">
                      Edit shared brand/product context and per-slot objectives used by Shopify
                      template image generation.
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleResetTemplateImagePromptContextsToDefault}
                  >
                    Reset to defaults
                  </Button>
                </div>
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-content">General context</div>
                  <textarea
                    rows={4}
                    value={templateImageGenerationGeneralContextInput}
                    onChange={(event) => {
                      setTemplateImageGenerationGeneralContextInput(event.target.value);
                      setTemplateDraftEditError(null);
                    }}
                    placeholder="General brand and product context for all generated images."
                    className={cn(
                      "w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content shadow-sm",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                    )}
                  />
                  <div className="text-[11px] text-content-muted">
                    {templateImageGenerationGeneralContextInput.trim().length} characters
                  </div>
                </div>
                {!selectedTemplateDraft.latestVersion.data.imageSlots.length ? (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    This draft has no image slots.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                    {selectedTemplateDraft.latestVersion.data.imageSlots.map((slot) => {
                      const readableSlotLabel =
                        templateImageSlotReadableLabelByPath.get(slot.path) ||
                        humanizeSlotToken(slot.path.split(".").pop() || slot.path);
                      const slotContextValue =
                        templateImageGenerationEffectiveSlotContextByPath[slot.path] || "";
                      const hasCustomSlotContext = Object.prototype.hasOwnProperty.call(
                        templateImageGenerationSlotContextByPath,
                        slot.path
                      );
                      return (
                        <div
                          key={`prompt-context-${slot.path}`}
                          className="space-y-2 rounded-md border border-border bg-surface p-2"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="text-xs font-semibold text-content">
                              {readableSlotLabel}
                            </div>
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() =>
                                setTemplateImageGenerationSlotContextByPath((current) => {
                                  const next = { ...current };
                                  delete next[slot.path];
                                  return next;
                                })
                              }
                              disabled={!hasCustomSlotContext}
                            >
                              Use default
                            </Button>
                          </div>
                          <div className="text-[11px] font-mono break-all text-content">
                            {slot.path}
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                            <span>role: {slot.role || "generic"}</span>
                            <span>aspect: {slot.recommendedAspect || "any"}</span>
                            <span>{hasCustomSlotContext ? "custom" : "default"}</span>
                          </div>
                          <textarea
                            rows={3}
                            value={slotContextValue}
                            onChange={(event) =>
                              handleTemplateImageGenerationSlotContextChange(
                                slot.path,
                                event.target.value
                              )
                            }
                            placeholder={`Context for ${readableSlotLabel}`}
                            className={cn(
                              "w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content shadow-sm",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                            )}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              <div className="space-y-3 rounded-md border border-divider p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-xs font-semibold text-content">Image generation scope (optional)</div>
                    <div className="text-xs text-content-muted">
                      Leave blank to generate all unmapped slots. To target specific images, enter slot paths (one per line).
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        setTemplateImageGenerationSlotPathsInput(
                          selectedTemplateDraft.latestVersion.data.imageSlots.map((slot) => slot.path).join("\n")
                        )
                      }
                    >
                      Use all slot paths
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setTemplateImageGenerationSlotPathsInput("")}
                    >
                      Clear scope
                    </Button>
                  </div>
                </div>
                <textarea
                  rows={4}
                  value={templateImageGenerationSlotPathsInput}
                  onChange={(event) => {
                    setTemplateImageGenerationSlotPathsInput(event.target.value);
                    setTemplateDraftEditError(null);
                  }}
                  placeholder="templates/index.json.sections.hero.settings.image"
                  className={cn(
                    "w-full rounded-md border border-border bg-surface px-3 py-2 text-[11px] font-mono text-content shadow-sm",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                  )}
                />
                <div className="rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] text-content-muted">
                  Known image slots: {selectedTemplateDraft.latestVersion.data.imageSlots.length}
                </div>
              </div>
              <div className="space-y-3 rounded-md border border-divider p-3">
                <div>
                  <div className="text-xs font-semibold text-content">Text values</div>
                  <div className="text-xs text-content-muted">
                    Edit each discovered text slot directly. Mapped values override the theme's current values.
                  </div>
                </div>
                {parsedTemplateDraftTextValuesResult.error ? (
                  <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                    {parsedTemplateDraftTextValuesResult.error}
                  </div>
                ) : !selectedTemplateDraft.latestVersion.data.textSlots.length ? (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    This draft has no text slots to map.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                    {selectedTemplateDraft.latestVersion.data.textSlots.map((slot) => {
                      const readableSlotLabel =
                        templateTextSlotReadableLabelByPath.get(slot.path) ||
                        humanizeSlotToken(slot.path.split(".").pop() || slot.path);
                      const mappedValue = parsedTemplateDraftTextValues[slot.path] || "";
                      const currentThemeValue = slot.currentValue || "";
                      return (
                        <div key={slot.path} className="space-y-2 rounded-md border border-border bg-surface p-2">
                          <div className="text-xs font-semibold text-content">{readableSlotLabel}</div>
                          <div className="text-[11px] font-mono break-all text-content">{slot.path}</div>
                          <div className="text-[11px] text-content-muted">key: {slot.key}</div>
                          <textarea
                            rows={3}
                            value={mappedValue}
                            onChange={(event) => handleTemplateDraftSlotTextValueChange(slot.path, event.target.value)}
                            placeholder={currentThemeValue || "Enter mapped text value for this slot"}
                            className={cn(
                              "w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content shadow-sm",
                              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                            )}
                          />
                          <div className="rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] text-content-muted">
                            Current theme value: {currentThemeValue || "None"}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
              {templateDraftEditError ? <div className="text-xs text-danger">{templateDraftEditError}</div> : null}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => {
                    void handleClearTemplateDraftImageMappings();
                  }}
                  disabled={updateShopifyThemeTemplateDraft.isPending}
                >
                  {updateShopifyThemeTemplateDraft.isPending ? "Clearing…" : "Clear all mapped image slots"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    void handleGenerateTemplateDraftImages();
                  }}
                  disabled={generateShopifyThemeTemplateImages.isPending}
                >
                  {generateShopifyThemeTemplateImages.isPending ? "Generating…" : "Generate template images"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    void handleSaveTemplateDraftEdits();
                  }}
                  disabled={updateShopifyThemeTemplateDraft.isPending}
                >
                  {updateShopifyThemeTemplateDraft.isPending ? "Saving…" : "Save draft edits"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleOpenTemplatePreview}
                >
                  Preview mapped content
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    void handlePublishTemplateDraft();
                  }}
                  disabled={publishShopifyThemeTemplateDraft.isPending}
                >
                  {publishShopifyThemeTemplateDraft.isPending ? "Publishing…" : "Job 2: Publish template"}
                </Button>
              </div>
              <div className="text-xs text-content-muted">
                Slots: {selectedTemplateDraft.latestVersion.data.imageSlots.length} image ·{" "}
                {selectedTemplateDraft.latestVersion.data.textSlots.length} text
              </div>
            </div>
          ) : null}

          {templatePublishResult ? (
            <div className="space-y-2 rounded-md border border-divider p-3">
              <div className="text-xs text-content-muted">
                Last publish: <span className="font-semibold text-content">{templatePublishResult.sync.shopDomain}</span> ·{" "}
                <span className="font-semibold text-content">{templatePublishResult.sync.themeName}</span>
              </div>
              <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                <TableBody>
                  <TableRow>
                    <TableCell className="w-[240px] text-xs text-content-muted">Draft</TableCell>
                    <TableCell className="text-xs text-content break-all">
                      {templatePublishResult.draft.id} · v{templatePublishResult.version.versionNumber}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">CSS asset</TableCell>
                    <TableCell className="text-xs text-content break-all">{templatePublishResult.sync.cssFilename}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Settings file</TableCell>
                    <TableCell className="text-xs text-content break-all">
                      {templatePublishResult.sync.settingsFilename || "n/a"}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Coverage</TableCell>
                    <TableCell className="text-xs text-content">
                      {templatePublishResult.sync.coverage.requiredThemeVars.length} required theme vars ·{" "}
                      {templatePublishResult.sync.coverage.missingThemeVars.length} missing
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Settings paths</TableCell>
                    <TableCell className="text-xs text-content">
                      {templatePublishResult.sync.settingsSync.updatedPaths.length} updated ·{" "}
                      {templatePublishResult.sync.settingsSync.missingPaths.length} missing
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Job ID</TableCell>
                    <TableCell className="text-xs text-content break-all">{templatePublishResult.sync.jobId || "n/a"}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          ) : null}

          {themeAuditResult ? (
            <div className="space-y-2 rounded-md border border-divider p-3">
              <div className="text-xs text-content-muted">
                Last audit: <span className="font-semibold text-content">{themeAuditResult.shopDomain}</span> ·{" "}
                <span className="font-semibold text-content">{themeAuditResult.themeName}</span>
              </div>
              <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                <TableBody>
                  <TableRow>
                    <TableCell className="w-[240px] text-xs text-content-muted">Status</TableCell>
                    <TableCell className={cn("text-xs font-semibold", themeAuditResult.isReady ? "text-emerald-600" : "text-amber-600")}>
                      {themeAuditResult.isReady ? "Ready" : "Has gaps"}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Marker block</TableCell>
                    <TableCell className="text-xs text-content">{themeAuditResult.hasManagedMarkerBlock ? "Present" : "Missing/invalid"}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Managed CSS asset</TableCell>
                    <TableCell className="text-xs text-content">
                      {themeAuditResult.managedCssAssetExists ? "Found" : "Missing"} ·{" "}
                      {themeAuditResult.layoutIncludesManagedCssAsset ? "Linked in layout" : "Not linked in layout"}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Coverage gaps</TableCell>
                    <TableCell className="text-xs text-content">
                      {themeAuditResult.coverage.missingSourceVars.length + themeAuditResult.coverage.missingThemeVars.length}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Settings gaps</TableCell>
                    <TableCell className="text-xs text-content">
                      {themeAuditResult.settingsAudit.missingPaths.length + themeAuditResult.settingsAudit.mismatchedPaths.length}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="text-xs text-content-muted">Component style gaps</TableCell>
                    <TableCell className="text-xs text-content">
                      {themeAuditResult.settingsAudit.semanticMismatchedPaths.length +
                        themeAuditResult.settingsAudit.unmappedColorPaths.length +
                        themeAuditResult.settingsAudit.unmappedTypographyPaths.length}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>

        <div className="rounded-md border border-divider p-3 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Compliance policy pages</div>
              <div className="text-xs text-content-muted">
                Generate and sync brand/workspace policy pages to Shopify using your configured compliance profile.
              </div>
            </div>
            <Button
              size="sm"
              onClick={() => {
                void handleSyncCompliancePolicyPages();
              }}
              disabled={syncCompliancePolicyPages.isPending || !hasShopifyConnectionTarget}
            >
              {syncCompliancePolicyPages.isPending ? "Generating…" : "Generate policy pages"}
            </Button>
          </div>

          {policySyncResult ? (
            <div className="space-y-2">
              <div className="text-xs text-content-muted">
                Last sync: <span className="font-semibold text-content">{policySyncResult.shopDomain}</span> ·{" "}
                <span className="font-semibold text-content">{policySyncResult.pages.length}</span> page(s)
              </div>
              <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                <TableHeader>
                  <TableRow>
                    <TableHeadCell className="w-[220px]">Page</TableHeadCell>
                    <TableHeadCell>URL</TableHeadCell>
                    <TableHeadCell className="w-[120px]">Operation</TableHeadCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {policySyncResult.pages.map((page) => (
                    <TableRow key={page.pageId}>
                      <TableCell className="text-xs text-content">{page.title}</TableCell>
                      <TableCell className="text-xs">
                        <a href={page.url} target="_blank" rel="noreferrer" className="break-all text-accent hover:underline">
                          {page.url}
                        </a>
                      </TableCell>
                      <TableCell className="text-xs text-content-muted">{page.operation}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
      </div>

      <div className="ds-card ds-card--md space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Design system visualizer</div>
            <div className="text-xs text-content-muted">
              Visualize logo, colors, and typography for a specific token set without changing workspace defaults.
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-[260px]">
              <Select
                value={previewDesignSystemId}
                onValueChange={(value) => setPreviewDesignSystemId(value)}
                options={[{ label: "Select design system…", value: "" }, ...designSystems.map((ds) => ({ label: ds.name, value: ds.id }))]}
                disabled={isLoading || !designSystems.length}
              />
            </div>
            {previewDesignSystem ? (
              <Button variant="secondary" size="sm" onClick={() => openEdit(previewDesignSystem)}>
                Edit
              </Button>
            ) : null}
          </div>
        </div>

        {previewDesignSystemId && !previewDesignSystem ? (
          <div className="rounded-md border border-border bg-surface-2 p-3 text-sm text-danger">
            Selected design system not found. It may have been deleted.
          </div>
        ) : null}

        {!previewDesignSystem ? (
          <div className="rounded-md border border-dashed border-border bg-surface-2 p-4 text-sm text-content-muted">
            {isLoading
              ? "Loading design systems…"
              : designSystems.length
                ? "Select a design system to preview."
                : "Create a design system to preview its tokens here."}
          </div>
        ) : (
          <Tabs defaultValue="preview">
            <TabsList className="shadow-none">
              <TabsTrigger value="preview" className="data-[selected]:shadow-none">
                Preview
              </TabsTrigger>
              <TabsTrigger value="tokens" className="data-[selected]:shadow-none">
                CSS vars
              </TabsTrigger>
            </TabsList>

            <TabsContent value="preview" flush>
              <DesignSystemProvider tokens={previewTokens}>
                <div
                  className="rounded-md overflow-hidden"
                  style={{
                    backgroundColor: "var(--color-page-bg)",
                    color: "var(--color-text)",
                  }}
                >
                  <div className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="flex items-start gap-3">
                        <div
                          className="grid size-14 place-items-center overflow-hidden border"
                          style={{
                            borderColor: "var(--color-border)",
                            borderRadius: "var(--radius-md)",
                            backgroundColor: "var(--color-bg)",
                          }}
                        >
                          {previewLogoSrc && !logoErrored ? (
                            <img
                              src={previewLogoSrc}
                              alt={previewBrand.logoAlt || previewBrand.name || "Logo"}
                              className="h-full w-full object-contain"
                              onError={() => setLogoErrored(true)}
                            />
                          ) : (
                            <div
                              className="px-2 text-center text-[11px] font-semibold"
                              style={{ color: "var(--color-muted)" }}
                            >
                              Logo
                            </div>
                          )}
                        </div>

                        <div className="min-w-[240px]">
                          <div className="text-lg font-semibold" style={{ fontFamily: "var(--font-heading)" }}>
                            {previewBrand.name || previewDesignSystem.name}
                          </div>
                          <div className="mt-1 space-y-1 text-[11px]" style={{ color: "var(--color-muted)" }}>
                            <div>
                              <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                                logoAssetPublicId:
                              </span>{" "}
                              <span className="font-mono" style={{ color: "var(--color-text)" }}>
                                {previewBrand.logoAssetPublicId || "Not set"}
                              </span>
                            </div>
                            {!apiBaseUrl ? (
                              <div className="text-danger">
                                Missing `VITE_API_BASE_URL` so the logo image preview cannot be loaded.
                              </div>
                            ) : logoErrored && previewBrand.logoAssetPublicId ? (
                              <div className="text-danger">
                                Unable to load logo from <span className="font-mono">{previewLogoSrc}</span>
                              </div>
                            ) : null}
                          </div>
                          <div className="mt-3 space-y-2">
                            <input
                              ref={logoUploadInputRef}
                              className="hidden"
                              type="file"
                              accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
                              onChange={handleLogoUpload}
                            />
                            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
                              <select
                                className="w-full rounded-md border border-input-border bg-input px-2 py-2 text-xs text-content shadow-sm"
                                value={selectedLogoPublicId}
                                onChange={(e) => setSelectedLogoPublicId(e.target.value)}
                                disabled={isLoadingLogoAssets || !logoAssetOptions.length}
                              >
                                <option value="">
                                  {isLoadingLogoAssets
                                    ? "Loading image assets…"
                                    : logoAssetOptions.length
                                      ? "Select existing image asset"
                                      : "No image assets available"}
                                </option>
                                {logoAssetOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                              <Button
                                size="sm"
                                onClick={applySelectedLogoAsset}
                                disabled={!selectedLogoPublicId || updateDesignSystem.isPending}
                              >
                                {updateDesignSystem.isPending ? "Applying…" : "Set logo"}
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => logoUploadInputRef.current?.click()}
                                disabled={uploadDesignSystemLogo.isPending}
                              >
                                {uploadDesignSystemLogo.isPending ? "Uploading…" : "Upload logo"}
                              </Button>
                            </div>
                            <div className="text-[11px]" style={{ color: "var(--color-muted)" }}>
                              Selecting or uploading a logo updates this design system token automatically.
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="text-xs" style={{ color: "var(--color-muted)" }}>
                        <div>
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                            Theme:
                          </span>{" "}
                          <span className="font-mono">
                            {(isRecord(previewTokens) &&
                              typeof previewTokens.dataTheme === "string" &&
                              previewTokens.dataTheme) ||
                              "unspecified"}
                          </span>
                        </div>
                        <div className="mt-1">
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                            Fonts:
                          </span>{" "}
                          <span className="font-mono">{previewFontUrls.length || 0}</span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <div
                        className="inline-flex items-center justify-center px-6 py-3 font-semibold"
                        style={{
                          backgroundColor: "var(--color-cta)",
                          color: "var(--color-cta-text)",
                          borderRadius: "999px",
                          fontFamily: "var(--font-cta)",
                          fontWeight: "var(--cta-font-weight)",
                          letterSpacing: "var(--cta-letter-spacing)",
                        }}
                      >
                        CTA preview
                      </div>
                      <div
                        className="inline-flex items-center justify-center px-4 py-3 font-semibold"
                        style={{
                          backgroundColor: "var(--color-soft)",
                          color: "var(--color-brand)",
                          borderRadius: "999px",
                          border: "1px solid var(--color-border)",
                          fontFamily: "var(--font-sans)",
                        }}
                      >
                        Secondary
                      </div>
                    </div>
                  </div>

                  <div className="border-t" style={{ borderColor: "var(--color-border)" }} />

                  <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                    <div className="p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-semibold" style={{ color: "var(--color-text)" }}>
                          Core palette
                        </div>
                        <div className="text-[11px]" style={{ color: "var(--color-muted)" }}>
                          {coreColors.length} tokens
                        </div>
                      </div>
                      {coreColors.length ? (
                        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {coreColors.map(({ key, value }) => (
                            <div
                              key={key}
                              className="rounded-lg border p-3"
                              style={{ borderColor: "var(--color-border)", backgroundColor: "var(--color-bg)" }}
                            >
                              <div
                                className="h-10 w-full rounded-md"
                                style={{
                                  backgroundColor: `var(${key})`,
                                  border: "1px solid var(--color-border)",
                                }}
                              />
                              <div className="mt-2">
                                <div className="font-mono text-[11px]" style={{ color: "var(--color-text)" }}>
                                  {key}
                                </div>
                                <div className="font-mono text-[11px] break-all" style={{ color: "var(--color-muted)" }}>
                                  {value}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm" style={{ color: "var(--color-muted)" }}>
                          No core color tokens found.
                        </div>
                      )}
                    </div>

                    <div className="p-4 lg:border-l" style={{ borderColor: "var(--color-border)" }}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-semibold" style={{ color: "var(--color-text)" }}>
                          Typography
                        </div>
                        <div className="text-[11px]" style={{ color: "var(--color-muted)" }}>
                          <span className="font-mono">
                            {previewCssVars["--font-sans"] ? "fonts set" : "fonts missing"}
                          </span>
                        </div>
                      </div>

                      <div className="mt-3 space-y-3">
                        <div
                          style={{
                            fontFamily: "var(--font-heading)",
                            fontSize: "var(--h2)",
                            lineHeight: "var(--heading-line)",
                            fontWeight: "var(--heading-weight)",
                            letterSpacing: "var(--hero-title-letter-spacing)",
                            color: "var(--color-brand)",
                          }}
                        >
                          Heading preview
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--font-sans)",
                            fontSize: "var(--text-base)",
                            lineHeight: "var(--line)",
                            color: "var(--color-text)",
                          }}
                        >
                          Body preview. This is a quick way to sanity check font pairing, base size, and line height.
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--font-sans)",
                            fontSize: "var(--hero-subtitle-size)",
                            lineHeight: "var(--hero-subtitle-line)",
                            fontWeight: "var(--hero-subtitle-weight)",
                            color: "var(--color-muted)",
                          }}
                        >
                          Subtitle preview
                        </div>
                      </div>

                      <div className="mt-4 grid gap-2 text-[11px]" style={{ color: "var(--color-muted)" }}>
                        <div>
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                            --font-sans:
                          </span>{" "}
                          <span className="font-mono break-all">{previewCssVars["--font-sans"] || "Not set"}</span>
                        </div>
                        <div>
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                            --font-heading:
                          </span>{" "}
                          <span className="font-mono break-all">{previewCssVars["--font-heading"] || "Not set"}</span>
                        </div>
                        <div>
                          <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                            --font-cta:
                          </span>{" "}
                          <span className="font-mono break-all">{previewCssVars["--font-cta"] || "Not set"}</span>
                        </div>
                      </div>

                      <div className="mt-6">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-xs font-semibold" style={{ color: "var(--color-text)" }}>
                            Spacing, radius, shadow
                          </div>
                          <div className="text-[11px]" style={{ color: "var(--color-muted)" }}>
                            <span className="font-mono">{previewCssVars["--radius-md"] || "unset"}</span>
                          </div>
                        </div>

                        <div className="mt-3 space-y-2">
                          {([
                            "--space-1",
                            "--space-2",
                            "--space-3",
                            "--space-4",
                            "--space-5",
                            "--space-6",
                            "--space-7",
                            "--space-8",
                          ] as const)
                            .filter((key) => Boolean(previewCssVars[key]))
                            .slice(0, 6)
                            .map((key) => (
                              <div key={key} className="flex items-center gap-3">
                                <div className="w-24 font-mono text-[11px]" style={{ color: "var(--color-muted)" }}>
                                  {key}
                                </div>
                                <div className="w-16 font-mono text-[11px]" style={{ color: "var(--color-muted)" }}>
                                  {previewCssVars[key]}
                                </div>
                                <div
                                  className="h-2 rounded-full"
                                  style={{ width: `var(${key})`, backgroundColor: "var(--color-brand)" }}
                                />
                              </div>
                            ))}
                        </div>

                        <div className="mt-4 grid grid-cols-3 gap-3">
                          {(["--radius-sm", "--radius-md", "--radius-lg"] as const)
                            .filter((key) => Boolean(previewCssVars[key]))
                            .map((key) => (
                              <div
                                key={key}
                                className="h-16 border"
                                style={{
                                  borderColor: "var(--color-border)",
                                  backgroundColor: "var(--color-soft)",
                                  borderRadius: `var(${key})`,
                                }}
                                title={`${key}: ${previewCssVars[key]}`}
                              />
                            ))}
                        </div>

                        {previewCssVars["--shadow-sm"] ? (
                          <div className="mt-4 text-[11px]" style={{ color: "var(--color-muted)" }}>
                            <span className="font-semibold" style={{ color: "var(--color-text)" }}>
                              --shadow-sm:
                            </span>{" "}
                            <span className="font-mono break-all">{previewCssVars["--shadow-sm"]}</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  {allColorVars.length ? (
                    <details className="border-t" style={{ borderColor: "var(--color-border)" }}>
                      <summary
                        className="cursor-pointer px-4 py-3 text-xs font-semibold"
                        style={{ color: "var(--color-text)" }}
                      >
                        All color-like vars ({allColorVars.length})
                      </summary>
                      <div className="px-4 pb-4">
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {allColorVars.slice(0, 60).map(([key, value]) => (
                            <div
                              key={key}
                              className="rounded-lg border p-3"
                              style={{ borderColor: "var(--color-border)", backgroundColor: "var(--color-bg)" }}
                            >
                              <div
                                className="h-10 w-full rounded-md"
                                style={{
                                  backgroundColor: `var(${key})`,
                                  border: "1px solid var(--color-border)",
                                }}
                              />
                              <div className="mt-2">
                                <div className="font-mono text-[11px]" style={{ color: "var(--color-text)" }}>
                                  {key}
                                </div>
                                <div className="font-mono text-[11px] break-all" style={{ color: "var(--color-muted)" }}>
                                  {value}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                        {allColorVars.length > 60 ? (
                          <div className="mt-2 text-xs" style={{ color: "var(--color-muted)" }}>
                            Showing first 60. Use the CSS vars tab to filter and view all tokens.
                          </div>
                        ) : null}
                      </div>
                    </details>
                  ) : null}
                </div>
              </DesignSystemProvider>
            </TabsContent>

            <TabsContent value="tokens" flush>
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs text-content-muted">
                    <span className="font-semibold text-content">{previewFilteredCssVarEntries.length}</span>{" "}
                    vars
                    {varsFilter.trim() ? (
                      <>
                        {" "}
                        (filtered from{" "}
                        <span className="font-semibold text-content">{previewCssVarEntries.length}</span>)
                      </>
                    ) : null}
                  </div>
                  <div className="w-full sm:w-[360px]">
                    <Input
                      value={varsFilter}
                      onChange={(e) => setVarsFilter(e.target.value)}
                      placeholder="Filter (e.g. color, hero, radius, cta)"
                    />
                  </div>
                </div>

                {!previewCssVarEntries.length ? (
                  <div className="rounded-md border border-border bg-surface-2 p-4 text-sm text-danger">
                    This design system has no `cssVars` object.
                  </div>
                ) : (
                  <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                    <TableHeader>
                      <TableRow>
                        <TableHeadCell className="w-[300px]">Variable</TableHeadCell>
                        <TableHeadCell>Value</TableHeadCell>
                        <TableHeadCell className="w-[120px]">Action</TableHeadCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {previewFilteredCssVarEntries.map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell className="font-mono text-[11px] text-content">{key}</TableCell>
                          <TableCell className="font-mono text-[11px] text-content-muted break-all">{value}</TableCell>
                          <TableCell>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => copyToClipboard(`${key}: ${value}`, "CSS var")}
                            >
                              Copy
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </TabsContent>
          </Tabs>
        )}
      </div>

      <div className="ds-card ds-card--md space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Design systems</div>
            <div className="text-xs text-content-muted">
              Manage token sets for this workspace. Use overrides to apply a different system per funnel or page.
            </div>
          </div>
        </div>
        {isLoading ? (
          <div className="text-sm text-content-muted">Loading design systems…</div>
        ) : designSystems.length ? (
          <div className="space-y-2">
            {designSystems.map((ds) => (
              <div key={ds.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface px-3 py-3">
                <div>
                  <div className="text-sm font-semibold text-content">{ds.name}</div>
                  <div className="text-xs text-content-muted">{countCssVars(ds.tokens)} CSS vars</div>
                </div>
                <Menu>
                  <MenuTrigger
                    className={cn(
                      "inline-flex items-center justify-center rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs text-content transition",
                      "hover:bg-surface hover:text-content"
                    )}
                  >
                    Actions
                  </MenuTrigger>
                  <MenuContent>
                    <MenuItem onClick={() => openEdit(ds)}>Edit</MenuItem>
                    <MenuItem
                      onClick={() =>
                        createDesignSystem.mutate({
                          name: `${ds.name} copy`,
                          tokens: ds.tokens || DEFAULT_TOKENS,
                          clientId: workspace.id,
                        })
                      }
                    >
                      Duplicate
                    </MenuItem>
                    <MenuSeparator />
                    <MenuItem
                      className="text-danger"
                      onClick={() => {
                        if (!window.confirm(`Delete "${ds.name}"? This will clear any overrides using it.`)) return;
                        deleteDesignSystem.mutate({ designSystemId: ds.id, clientId: workspace.id });
                      }}
                    >
                      Delete
                    </MenuItem>
                  </MenuContent>
                </Menu>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border bg-surface-2 p-4 text-sm text-content-muted">
            No design systems yet. Create one to set brand tokens.
          </div>
        )}
      </div>

      <DialogRoot open={templatePreviewDialogOpen} onOpenChange={setTemplatePreviewDialogOpen}>
        <DialogContent className="max-w-5xl">
          <div className="space-y-2">
            <DialogTitle>Template Draft Preview</DialogTitle>
            <DialogDescription>
              Review mapped images and text before publishing this template to Shopify.
            </DialogDescription>
          </div>

          {!selectedTemplateDraft?.latestVersion ? (
            <div className="mt-4 rounded-md border border-border bg-surface-2 p-4 text-sm text-content-muted">
              Select a template draft to preview.
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              {!publicAssetBaseUrl ? (
                <div className="rounded-md border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                  Missing `VITE_API_BASE_URL`; image previews cannot be loaded.
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="text-xs font-semibold text-content">Mapped images</div>
                {templatePreviewImageItems.length ? (
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 max-h-[48vh] overflow-y-auto pr-1">
                    {templatePreviewImageItems.map((item) => {
                      const imageUrl =
                        publicAssetBaseUrl && item.assetPublicId
                          ? `${publicAssetBaseUrl}/public/assets/${item.assetPublicId}`
                          : undefined;
                      const loadErrored = Boolean(templatePreviewImageErrorsByPath[item.path]);
                      const readableSlotLabel =
                        templateImageSlotReadableLabelByPath.get(item.path) ||
                        humanizeSlotToken(item.path.split(".").pop() || item.path);
                      return (
                        <div key={item.path} className="rounded-md border border-border bg-surface p-3 space-y-2">
                          <div className="text-xs font-semibold text-content">{readableSlotLabel}</div>
                          <div className="text-[11px] font-mono break-all text-content">{item.path}</div>
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-content-muted">
                            {item.role ? <span>role: {item.role}</span> : null}
                            {item.recommendedAspect ? <span>aspect: {item.recommendedAspect}</span> : null}
                            {!item.hasKnownSlot ? <span>custom path</span> : null}
                          </div>
                          <div className="rounded-md border border-border bg-surface-2 p-2">
                            {imageUrl && !loadErrored ? (
                              <img
                                src={imageUrl}
                                alt={item.path}
                                className="h-44 w-full rounded object-contain bg-white"
                                onError={() =>
                                  setTemplatePreviewImageErrorsByPath((current) => ({
                                    ...current,
                                    [item.path]: true,
                                  }))
                                }
                              />
                            ) : (
                              <div className="grid h-44 place-items-center text-xs text-content-muted">
                                {item.assetPublicId
                                  ? "Image could not be loaded."
                                  : "No mapped asset for this slot."}
                              </div>
                            )}
                          </div>
                          <div className="text-[11px] text-content-muted break-all">
                            asset: <span className="font-mono text-content">{item.assetPublicId || "n/a"}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    No image mappings found in this draft.
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-content">Mapped text values</div>
                {templatePreviewTextEntries.length ? (
                  <Table variant="ghost" size={1} layout="fixed" containerClassName="rounded-md border border-divider">
                    <TableHeader>
                      <TableRow>
                        <TableHeadCell className="w-[55%]">Path</TableHeadCell>
                        <TableHeadCell>Value</TableHeadCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {templatePreviewTextEntries.map(([path, value]) => (
                        <TableRow key={path}>
                          <TableCell className="font-mono text-[11px] text-content break-all">{path}</TableCell>
                          <TableCell className="text-xs text-content break-all">{value}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="rounded-md border border-dashed border-border bg-surface-2 p-3 text-xs text-content-muted">
                    No text mappings found in this draft.
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </DialogRoot>

      <DialogRoot open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-3xl">
          <div className="space-y-2">
            <DialogTitle>{editing ? "Edit design system" : "New design system"}</DialogTitle>
            <DialogDescription>
              Update the CSS variables that control your funnel theme. These tokens cascade into every template.
            </DialogDescription>
          </div>
          <div className="mt-4 space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Name</label>
              <Input value={draftName} onChange={(e) => setDraftName(e.target.value)} placeholder="Acme brand" />
            </div>
            <div className="space-y-2 rounded-md border border-border bg-surface-2 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-content">Template (JSON)</div>
                  <div className="text-xs text-content-muted">Copy this and tweak, or feed it to your LLM.</div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setDraftTokens(DESIGN_SYSTEM_TEMPLATE)}
                  >
                    Use template
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => copyToClipboard(DESIGN_SYSTEM_TEMPLATE, "Template")}
                  >
                    Copy template
                  </Button>
                </div>
              </div>
              <pre className="max-h-44 overflow-auto rounded-md border border-border bg-surface px-3 py-2 text-[11px] text-content">
                {DESIGN_SYSTEM_TEMPLATE}
              </pre>
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <div className="text-xs text-content-muted">Prompt for LLMs</div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => copyToClipboard(DESIGN_SYSTEM_PROMPT, "Prompt")}
                >
                  Copy prompt
                </Button>
              </div>
              <textarea
                rows={4}
                value={DESIGN_SYSTEM_PROMPT}
                readOnly
                className={cn(
                  "w-full rounded-md border border-border bg-surface px-3 py-2 text-xs text-content shadow-sm",
                  "focus-visible:outline-none"
                )}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Tokens JSON</label>
              <textarea
                rows={14}
                value={draftTokens}
                onChange={(e) => {
                  setDraftTokens(e.target.value);
                  setTokensError(null);
                }}
                className={cn(
                  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
                )}
              />
              {tokensError ? <div className="text-xs text-danger">{tokensError}</div> : null}
            </div>
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={createDesignSystem.isPending || updateDesignSystem.isPending}>
              {editing ? (updateDesignSystem.isPending ? "Saving…" : "Save") : createDesignSystem.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </DialogContent>
      </DialogRoot>
    </div>
  );
}
