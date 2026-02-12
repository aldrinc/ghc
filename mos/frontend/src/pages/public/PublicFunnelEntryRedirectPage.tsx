import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { PublicFunnelMeta } from "@/types/funnels";
import { buildPublicFunnelPath, isStandaloneRootModeForPublicId } from "@/funnels/runtimeRouting";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";

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
  const { publicId } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureNoIndex();
  }, []);

  useEffect(() => {
    if (!publicId) return;
    setError(null);
    fetch(`${apiBaseUrl}/public/funnels/${publicId}/meta`)
      .then(async (resp) => {
        if (!resp.ok) {
          const text = await resp.text();
          throw new Error(text || resp.statusText);
        }
        return (await resp.json()) as PublicFunnelMeta;
      })
      .then((meta) => {
        navigate(
          buildPublicFunnelPath({
            publicId,
            slug: meta.entrySlug,
            entrySlug: meta.entrySlug,
            rootMode: isStandaloneRootModeForPublicId(publicId),
          }),
          { replace: true },
        );
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unable to load funnel");
      });
  }, [navigate, publicId]);

  return (
    <div className="min-h-screen bg-surface px-6 py-10 text-sm text-content-muted">
      {error ? <div className="mx-auto w-full max-w-xl">This funnel is unavailable. {error}</div> : "Loading funnel…"}
    </div>
  );
}
