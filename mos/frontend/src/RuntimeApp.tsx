import { Suspense, lazy, type ComponentType } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { PublicFunnelShellMessage } from "@/pages/public/publicFunnelShell";

function lazyNamed<TModule extends Record<string, unknown>, TName extends keyof TModule & string>(
  loader: () => Promise<TModule>,
  exportName: TName,
) {
  return lazy(async () => {
    const module = await loader();
    const component = module[exportName];
    if (!component) {
      throw new Error(`Missing export '${exportName}' from lazy module.`);
    }
    return { default: component as ComponentType };
  });
}

const PublicFunnelRootRedirectPage = lazyNamed(
  () => import("@/pages/public/PublicFunnelRootRedirectPage"),
  "PublicFunnelRootRedirectPage",
);
const PublicFunnelPage = lazyNamed(() => import("@/pages/public/PublicFunnelPage"), "PublicFunnelPage");
const PublicFunnelEntryRedirectPage = lazyNamed(
  () => import("@/pages/public/PublicFunnelEntryRedirectPage"),
  "PublicFunnelEntryRedirectPage",
);

export default function RuntimeApp() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PublicFunnelShellMessage>Loading funnel…</PublicFunnelShellMessage>}>
        <Routes>
          <Route path="/" element={<PublicFunnelRootRedirectPage />} />
          <Route path="/:productSlug/:slug" element={<PublicFunnelPage />} />
          <Route path="/:productSlug/:funnelSlug/:slug" element={<PublicFunnelPage />} />
          <Route path="/f/:productSlug/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} />
          <Route path="/f/:productSlug/:funnelSlug/:slug" element={<PublicFunnelPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
