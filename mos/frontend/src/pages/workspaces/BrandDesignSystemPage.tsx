import { useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useDesignSystems, useCreateDesignSystem, useUpdateDesignSystem, useDeleteDesignSystem } from "@/api/designSystems";
import { useClient, useUpdateClient } from "@/api/clients";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DialogContent, DialogDescription, DialogRoot, DialogTitle } from "@/components/ui/dialog";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import type { DesignSystem } from "@/types/designSystems";
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

const DESIGN_SYSTEM_PROMPT = `Create a comprehensive design system JSON for our Sales PDP template.
- Output ONLY valid JSON.
- Match this schema: { dataTheme, fontUrls, cssVars, funnelDefaults, brand }.
- Use the cssVars keys from the template exactly.
- Prefer values as strings with units when needed.
Brand details: [describe your brand here].`;

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

export function BrandDesignSystemPage() {
  const { workspace } = useWorkspace();
  const { data: client } = useClient(workspace?.id);
  const { data: designSystems = [], isLoading } = useDesignSystems(workspace?.id);
  const updateClient = useUpdateClient();
  const createDesignSystem = useCreateDesignSystem();
  const updateDesignSystem = useUpdateDesignSystem();
  const deleteDesignSystem = useDeleteDesignSystem();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<DesignSystem | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftTokens, setDraftTokens] = useState(formatTokens(DEFAULT_TOKENS));
  const [tokensError, setTokensError] = useState<string | null>(null);

  const designSystemOptions = useMemo(
    () => [
      { label: "Workspace default", value: "" },
      ...designSystems.map((ds) => ({ label: ds.name, value: ds.id })),
    ],
    [designSystems]
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
          <div className="text-xs text-content-muted">
            This design system powers funnel pages unless a funnel or page overrides it.
          </div>
        </div>
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
