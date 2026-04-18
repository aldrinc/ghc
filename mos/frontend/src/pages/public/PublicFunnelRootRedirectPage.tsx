import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  buildPublicFunnelPath,
  getStandaloneDefaultPageRoute,
  isStandaloneBundleMode,
} from "@/funnels/runtimeRouting";
import { PublicFunnelShellMessage } from "@/pages/public/publicFunnelShell";

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

export function PublicFunnelRootRedirectPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const bundleMode = isStandaloneBundleMode();

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    const defaultRoute = getStandaloneDefaultPageRoute();
    if (!defaultRoute) {
      setError("This deployment has no published standalone entry page configured.");
      return;
    }

    navigate(
      `${buildPublicFunnelPath({
        productSlug: defaultRoute.productSlug,
        funnelSlug: defaultRoute.funnelSlug,
        slug: defaultRoute.slug,
        bundleMode,
      })}${location.search}${location.hash}`,
      { replace: true },
    );
  }, [bundleMode, location.hash, location.search, navigate]);

  return <PublicFunnelShellMessage constrain={Boolean(error)}>{error || "Loading funnel…"}</PublicFunnelShellMessage>;
}
