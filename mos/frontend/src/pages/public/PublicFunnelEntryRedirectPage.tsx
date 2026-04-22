import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import type { PublicFunnelMeta } from "@/types/funnels";
import {
  buildPublicFunnelPath,
  isStandaloneBundleMode,
  resolvePreferredPublicFunnelSlug,
  resolvePublicApiBaseUrl,
} from "@/funnels/runtimeRouting";
import { PublicFunnelShellMessage } from "@/pages/public/publicFunnelShell";

const apiBaseUrl = resolvePublicApiBaseUrl();

function ensureNoIndex() {
  const name = "robots";
  const content = "noindex,nofollow";
  const existing = document.querySelector(`meta[name="${name}"]`);
  if (existing) {
    existing.setAttribute("content", content);
    return;
  }
  const meta = document.createElement("meta");
  meta.setAttribute("name", name);
  meta.setAttribute("content", content);
  document.head.appendChild(meta);
}

export function PublicFunnelEntryRedirectPage() {
  const { productSlug, funnelSlug } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const bundleMode = isStandaloneBundleMode();

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    if (!productSlug || !funnelSlug) return;
    setError(null);
    fetch(`${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/meta`)
      .then(async (resp) => {
        if (!resp.ok) {
          const text = await resp.text();
          throw new Error(text || resp.statusText);
        }
        return (await resp.json()) as PublicFunnelMeta;
      })
      .then((meta) => {
        const preferredSlug = resolvePreferredPublicFunnelSlug(meta);
        if (!preferredSlug) {
          throw new Error("This funnel has no redirectable page configured.");
        }
        const entryPath = buildPublicFunnelPath({
          productSlug,
          funnelSlug,
          slug: preferredSlug,
          bundleMode,
        });
        navigate(
          `${entryPath}${location.search}${location.hash}`,
          { replace: true },
        );
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load funnel");
      });
  }, [bundleMode, funnelSlug, location.hash, location.search, navigate, productSlug]);

  return (
    <PublicFunnelShellMessage constrain={Boolean(error)}>
      {error ? `This funnel is unavailable. ${error}` : "Loading funnel…"}
    </PublicFunnelShellMessage>
  );
}
