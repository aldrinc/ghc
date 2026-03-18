import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { PlatformPreviewProps } from "@/types/adPlatform";

function readDestinationLabel(value?: string | null): string | null {
  if (!value) return null;
  try {
    const base =
      typeof window !== "undefined" && window.location?.origin ? window.location.origin : undefined;
    const url = base ? new URL(value, base) : new URL(value);
    return url.hostname.replace(/^www\./i, "") || url.pathname || null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Placement types
// ---------------------------------------------------------------------------

type Placement = "fb_desktop" | "fb_mobile" | "instagram";

const PLACEMENTS: { id: Placement; label: string }[] = [
  { id: "fb_desktop", label: "Facebook Desktop" },
  { id: "fb_mobile", label: "Facebook Mobile" },
  { id: "instagram", label: "Instagram" },
];

// ---------------------------------------------------------------------------
// Platform colour tokens
// ---------------------------------------------------------------------------

const fb = {
  bg: "#FFFFFF",
  textPrimary: "#050505",
  textSecondary: "#65676B",
  border: "#CED0D4",
  linkBg: "#F0F2F5",
  ctaBg: "#E4E6EB",
  avatarBg: "#E4E6EB",
} as const;

const ig = {
  bg: "#FFFFFF",
  textPrimary: "#262626",
  textSecondary: "#8E8E8E",
  border: "#DBDBDB",
  ctaBlue: "#0095F6",
  avatarGradient: "linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)",
} as const;

const TEXT_COLLAPSE_LEN = 200;
const TEXT_COLLAPSE_LEN_MOBILE = 125;

// ---------------------------------------------------------------------------
// Shared SVG icons — Facebook
// ---------------------------------------------------------------------------

function ThumbsUpIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M5.25 16.5H3C2.17157 16.5 1.5 15.8284 1.5 15V9.75C1.5 8.92157 2.17157 8.25 3 8.25H5.25M10.5 6.75V3.75C10.5 2.50736 9.49264 1.5 8.25 1.5L5.25 8.25V16.5H13.635C14.3765 16.5082 15.0131 15.9597 15.12 15.225L16.02 9.225C16.0838 8.79279 15.9607 8.35354 15.6832 8.01561C15.4058 7.67768 14.9999 7.47397 14.5635 7.47H10.5" stroke={fb.textSecondary} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function FbCommentIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M15.75 8.625C15.7529 9.60687 15.5277 10.5763 15.0938 11.4562C14.5782 12.5103 13.7877 13.4007 12.8018 14.0355C11.8159 14.6703 10.6734 15.0261 9.49875 15.0625C8.51688 15.0654 7.54738 14.8402 6.6675 14.4062L2.25 15.75L3.59375 11.3325C3.15979 10.4526 2.93462 9.48312 2.9375 8.50125C2.97389 7.32664 3.32972 6.18407 3.96449 5.1982C4.59927 4.21233 5.48968 3.42183 6.54375 2.90625C7.42363 2.47229 8.39313 2.24712 9.375 2.25H9.75C11.3082 2.33653 12.7817 2.9935 13.8941 4.10593C15.0065 5.21836 15.6635 6.69184 15.75 8.25V8.625Z" stroke={fb.textSecondary} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function FbShareIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M2.25 9L8.0625 2.25V6C13.5 6.75 15.75 10.5 15.75 15C13.875 12.375 11.25 11.175 8.0625 11.175V15.75L2.25 9Z" stroke={fb.textSecondary} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill={fb.textSecondary}>
      <path d="M6 0.5C2.9625 0.5 0.5 2.9625 0.5 6C0.5 9.0375 2.9625 11.5 6 11.5C9.0375 11.5 11.5 9.0375 11.5 6C11.5 2.9625 9.0375 0.5 6 0.5ZM9.925 3.75H8.275C8.09375 2.9875 7.8375 2.2625 7.50625 1.6125C8.49375 2.0125 9.33125 2.775 9.925 3.75ZM6 1.525C6.45 2.225 6.8125 2.9625 7.05 3.75H4.95C5.1875 2.9625 5.55 2.225 6 1.525ZM1.625 7.25C1.5375 6.85 1.5 6.4375 1.5 6C1.5 5.5625 1.5375 5.15 1.625 4.75H3.5C3.4625 5.1625 3.425 5.575 3.425 6C3.425 6.425 3.4625 6.8375 3.5 7.25H1.625ZM2.075 8.25H3.725C3.90625 9.0125 4.1625 9.7375 4.49375 10.3875C3.50625 9.9875 2.66875 9.225 2.075 8.25ZM3.725 3.75H2.075C2.66875 2.775 3.50625 2.0125 4.49375 1.6125C4.1625 2.2625 3.90625 2.9875 3.725 3.75ZM6 10.475C5.55 9.775 5.1875 9.0375 4.95 8.25H7.05C6.8125 9.0375 6.45 9.775 6 10.475ZM7.275 7.25H4.725C4.6875 6.8375 4.65 6.425 4.65 6C4.65 5.575 4.6875 5.1625 4.725 4.75H7.275C7.3125 5.1625 7.35 5.575 7.35 6C7.35 6.425 7.3125 6.8375 7.275 7.25ZM7.50625 10.3875C7.8375 9.7375 8.09375 9.0125 8.275 8.25H9.925C9.33125 9.225 8.49375 9.9875 7.50625 10.3875ZM8.5 7.25C8.5375 6.8375 8.575 6.425 8.575 6C8.575 5.575 8.5375 5.1625 8.5 4.75H10.375C10.4625 5.15 10.5 5.5625 10.5 6C10.5 6.4375 10.4625 6.85 10.375 7.25H8.5Z"/>
    </svg>
  );
}

function MoreIcon({ color = fb.textSecondary }: { color?: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill={color}>
      <circle cx="4" cy="10" r="1.5" />
      <circle cx="10" cy="10" r="1.5" />
      <circle cx="16" cy="10" r="1.5" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Instagram SVG icons
// ---------------------------------------------------------------------------

function IgHeartIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={ig.textPrimary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
    </svg>
  );
}

function IgCommentIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={ig.textPrimary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
    </svg>
  );
}

function IgSendIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={ig.textPrimary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13"/>
      <polygon points="22 2 15 22 11 13 2 9 22 2"/>
    </svg>
  );
}

function IgBookmarkIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={ig.textPrimary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

interface PreviewData {
  imageUrl: string | null;
  imageAlt: string;
  primaryText?: string | null;
  headline?: string | null;
  description?: string | null;
  cta?: string | null;
  destinationLabel: string | null;
}

function useTruncatedText(text: string | null | undefined, limit: number) {
  const [expanded, setExpanded] = useState(false);
  const shouldTruncate = text && text.length > limit && !expanded;
  const displayText = shouldTruncate
    ? text!.slice(0, limit).replace(/\s+\S*$/, "")
    : text;
  return { displayText, shouldTruncate, expand: () => setExpanded(true) };
}

// ---------------------------------------------------------------------------
// Facebook feed card (shared between desktop & mobile)
// ---------------------------------------------------------------------------

function FacebookFeedCard({ data, mobile }: { data: PreviewData; mobile?: boolean }) {
  const collapseLen = mobile ? TEXT_COLLAPSE_LEN_MOBILE : TEXT_COLLAPSE_LEN;
  const { displayText, shouldTruncate, expand } = useTruncatedText(data.primaryText, collapseLen);

  return (
    <div
      className="overflow-hidden rounded-lg border text-sm"
      style={{ background: fb.bg, borderColor: fb.border, color: fb.textPrimary }}
    >
      {/* Page header */}
      <div className="flex items-center gap-2 px-4 pt-3 pb-2">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[15px] font-bold"
          style={{ background: fb.avatarBg, color: fb.textSecondary }}
        >
          B
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold leading-5" style={{ color: fb.textPrimary }}>
            Brand Page
          </div>
          <div className="flex items-center gap-1 text-[13px] leading-4" style={{ color: fb.textSecondary }}>
            <span>Sponsored</span>
            <span>·</span>
            <GlobeIcon />
          </div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full">
          <MoreIcon />
        </div>
      </div>

      {/* Primary text */}
      <div className="px-4 pb-3">
        <div className="whitespace-pre-wrap text-[15px] leading-5" style={{ color: fb.textPrimary }}>
          {displayText || "Primary text missing from prepared spec."}
          {shouldTruncate && (
            <button
              type="button"
              className="ml-1 font-semibold hover:underline"
              style={{ color: fb.textSecondary }}
              onClick={expand}
            >
              See more
            </button>
          )}
        </div>
      </div>

      {/* Image — full bleed */}
      {data.imageUrl ? (
        <img
          src={data.imageUrl}
          alt={data.imageAlt}
          className="block w-full"
          style={{ borderTop: `1px solid ${fb.border}`, borderBottom: `1px solid ${fb.border}` }}
          loading="lazy"
        />
      ) : (
        <div
          className="flex h-[320px] items-center justify-center text-sm"
          style={{
            background: fb.linkBg,
            color: fb.textSecondary,
            borderTop: `1px solid ${fb.border}`,
            borderBottom: `1px solid ${fb.border}`,
          }}
        >
          Generated remix preview missing.
        </div>
      )}

      {/* Link preview bar */}
      <div
        className="flex items-center gap-4 px-4 py-3"
        style={{ background: fb.linkBg }}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] uppercase" style={{ color: fb.textSecondary }}>
            {data.destinationLabel || "destination url missing"}
          </div>
          <div
            className="mt-0.5 line-clamp-2 text-[15px] font-semibold leading-5"
            style={{ color: fb.textPrimary }}
          >
            {data.headline || "Headline missing from prepared spec."}
          </div>
          {data.description && (
            <div className="mt-0.5 truncate text-[13px]" style={{ color: fb.textSecondary }}>
              {data.description}
            </div>
          )}
        </div>
        <div
          className="shrink-0 rounded-md px-4 py-2 text-[15px] font-semibold"
          style={{ background: fb.ctaBg, color: fb.textPrimary }}
        >
          {data.cta || "Learn More"}
        </div>
      </div>

      {/* Engagement bar */}
      <div
        className="flex items-center justify-around px-2 py-1"
        style={{ borderTop: `1px solid ${fb.border}` }}
      >
        {[
          { icon: <ThumbsUpIcon />, label: "Like" },
          { icon: <FbCommentIcon />, label: "Comment" },
          { icon: <FbShareIcon />, label: "Share" },
        ].map(({ icon, label }) => (
          <div
            key={label}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-[13px] font-semibold"
            style={{ color: fb.textSecondary }}
          >
            {icon}
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Instagram feed card
// ---------------------------------------------------------------------------

function InstagramFeedCard({ data }: { data: PreviewData }) {
  const { displayText, shouldTruncate, expand } = useTruncatedText(data.primaryText, TEXT_COLLAPSE_LEN_MOBILE);

  return (
    <div
      className="overflow-hidden rounded-lg border text-sm"
      style={{ background: ig.bg, borderColor: ig.border, color: ig.textPrimary }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
          style={{ background: ig.avatarGradient }}
        >
          B
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-4" style={{ color: ig.textPrimary }}>
            brand_page
          </div>
          <div className="text-[11px] leading-3" style={{ color: ig.textSecondary }}>
            Sponsored
          </div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center">
          <MoreIcon color={ig.textPrimary} />
        </div>
      </div>

      {/* Image — full bleed, square crop */}
      {data.imageUrl ? (
        <img
          src={data.imageUrl}
          alt={data.imageAlt}
          className="block w-full"
          loading="lazy"
        />
      ) : (
        <div
          className="flex aspect-square w-full items-center justify-center text-sm"
          style={{ background: "#FAFAFA", color: ig.textSecondary }}
        >
          Generated remix preview missing.
        </div>
      )}

      {/* CTA banner */}
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: `1px solid ${ig.border}` }}
      >
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-4" style={{ color: ig.textPrimary }}>
            {data.headline || "Headline missing"}
          </div>
          {data.destinationLabel && (
            <div className="truncate text-[11px]" style={{ color: ig.textSecondary }}>
              {data.destinationLabel}
            </div>
          )}
        </div>
        <div
          className="ml-3 shrink-0 rounded text-[13px] font-semibold"
          style={{ color: ig.ctaBlue }}
        >
          {data.cta || "Learn More"}
        </div>
      </div>

      {/* Action icons */}
      <div className="flex items-center px-3 py-2">
        <div className="flex items-center gap-4">
          <IgHeartIcon />
          <IgCommentIcon />
          <IgSendIcon />
        </div>
        <div className="ml-auto">
          <IgBookmarkIcon />
        </div>
      </div>

      {/* Caption */}
      <div className="px-3 pb-3">
        <div className="text-[13px] leading-[18px]" style={{ color: ig.textPrimary }}>
          <span className="font-semibold">brand_page</span>{" "}
          <span className="whitespace-pre-wrap">
            {displayText || "Caption missing from prepared spec."}
          </span>
          {shouldTruncate && (
            <button
              type="button"
              className="ml-1"
              style={{ color: ig.textSecondary }}
              onClick={expand}
            >
              more
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Format selector
// ---------------------------------------------------------------------------

function PlacementTabs({
  value,
  onChange,
}: {
  value: Placement;
  onChange: (p: Placement) => void;
}) {
  return (
    <div
      className="inline-flex rounded-md border p-0.5 text-[11px] font-medium"
      style={{ borderColor: fb.border, background: fb.linkBg }}
    >
      {PLACEMENTS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          className="rounded px-2.5 py-1 transition-colors"
          style={{
            background: value === id ? "#FFFFFF" : "transparent",
            color: value === id ? fb.textPrimary : fb.textSecondary,
            boxShadow: value === id ? "0 1px 2px rgba(0,0,0,0.08)" : "none",
          }}
          onClick={() => onChange(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MetaFeedPreview (public)
// ---------------------------------------------------------------------------

export function MetaFeedPreview({
  imageUrl,
  imageAlt,
  primaryText,
  headline,
  description,
  cta,
  destinationUrl,
  specReady,
}: PlatformPreviewProps) {
  const destinationLabel = readDestinationLabel(destinationUrl);
  const [placement, setPlacement] = useState<Placement>("fb_desktop");

  const data: PreviewData = {
    imageUrl,
    imageAlt,
    primaryText,
    headline,
    description,
    cta,
    destinationLabel,
  };

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PlacementTabs value={placement} onChange={setPlacement} />
        <Badge tone={specReady ? "success" : "accent"}>
          {specReady ? "Spec ready" : "Spec missing"}
        </Badge>
      </div>

      {/* Preview card */}
      {specReady ? (
        placement === "fb_mobile" ? (
          <div className="mx-auto w-full max-w-[375px]">
            <FacebookFeedCard data={data} mobile />
          </div>
        ) : placement === "instagram" ? (
          <div className="mx-auto w-full max-w-[375px]">
            <InstagramFeedCard data={data} />
          </div>
        ) : (
          <FacebookFeedCard data={data} />
        )
      ) : (
        <div
          className="flex min-h-[520px] items-center justify-center rounded-lg border px-6 py-10 text-center text-sm leading-6"
          style={{ borderColor: fb.border, color: fb.textSecondary, background: fb.bg }}
        >
          Prepare Meta review to render the exact upload preview for this asset.
        </div>
      )}
    </div>
  );
}
