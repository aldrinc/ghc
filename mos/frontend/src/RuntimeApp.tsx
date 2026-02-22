import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { PublicFunnelEntryRedirectPage } from "@/pages/public/PublicFunnelEntryRedirectPage";
import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";
import { PublicFunnelRootRedirectPage } from "@/pages/public/PublicFunnelRootRedirectPage";

export default function RuntimeApp() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PublicFunnelRootRedirectPage />} />
        <Route path="/:productSlug/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} />
        <Route path="/:productSlug/:funnelSlug/:slug" element={<PublicFunnelPage />} />
        <Route path="/f/:productSlug/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} />
        <Route path="/f/:productSlug/:funnelSlug/:slug" element={<PublicFunnelPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
