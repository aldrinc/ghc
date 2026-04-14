import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  buildPublicFunnelPath,
  getStandaloneDefaultPageRoute,
  isStandaloneBundleMode,
} from "@/funnels/runtimeRouting";

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
      buildPublicFunnelPath({
        productSlug: defaultRoute.productSlug,
        funnelSlug: defaultRoute.funnelSlug,
        slug: defaultRoute.slug,
        bundleMode,
      }),
      { replace: true },
    );
  }, [bundleMode, navigate]);

  return (
    <div className="min-h-screen bg-surface px-6 py-10 text-sm text-content-muted">
      {error ? <div className="mx-auto w-full max-w-xl">{error}</div> : "Loading funnel…"}
    </div>
  );
}
