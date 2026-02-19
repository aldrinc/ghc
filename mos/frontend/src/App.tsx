import type { ReactNode } from "react";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import { Navigate, Route, Routes, BrowserRouter } from "react-router-dom";
import { AppShell } from "@/app/AppShell";
import { DocumentsPage } from "@/pages/research/DocumentsPage";
import { ResearchPage } from "@/pages/research/ResearchPage";
import { FunnelsPage } from "@/pages/research/FunnelsPage";
import { FunnelDetailPage } from "@/pages/research/funnels/FunnelDetailPage";
import { FunnelPageEditorPage } from "@/pages/research/funnels/FunnelPageEditorPage";
import { CreativeLibraryPage } from "@/pages/library/CreativeLibraryPage";
import { WorkspacesPage } from "@/pages/workspaces/WorkspacesPage";
import { WorkspaceOnboardingPage } from "@/pages/workspaces/WorkspaceOnboardingPage";
import { WorkspaceOverviewPage } from "@/pages/workspaces/WorkspaceOverviewPage";
import { BrandDesignSystemPage } from "@/pages/workspaces/BrandDesignSystemPage";
import { ProductsPage } from "@/pages/workspaces/ProductsPage";
import { ProductDetailPage } from "@/pages/workspaces/ProductDetailPage";
import { WorkflowsPage } from "@/pages/workflows/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/workflows/WorkflowDetailPage";
import { ResearchDetailPage } from "@/pages/workflows/ResearchDetailPage";
import { CampaignsPage } from "@/pages/campaigns/CampaignsPage";
import { CampaignDetailPage } from "@/pages/campaigns/CampaignDetailPage";
import { WorkspaceProvider } from "@/contexts/WorkspaceContext";
import { ProductProvider } from "@/contexts/ProductContext";
import { ClaudeChatPage } from "@/pages/claude/ClaudeChatPage";
import { PublicFunnelEntryRedirectPage } from "@/pages/public/PublicFunnelEntryRedirectPage";
import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";
import { isStandaloneBundleMode } from "@/funnels/runtimeRouting";

function RequireAuth({ children }: { children: ReactNode }) {
  return (
    <>
      <SignedIn>
        <WorkspaceProvider>
          <ProductProvider>{children}</ProductProvider>
        </WorkspaceProvider>
      </SignedIn>
      <SignedOut>
        <Navigate to="/sign-in" replace />
      </SignedOut>
    </>
  );
}

function App() {
  const standaloneBundleMode = isStandaloneBundleMode();

  return (
    <BrowserRouter>
      <Routes>
        {standaloneBundleMode ? <Route path="/" element={<PublicFunnelPage />} /> : null}
        {standaloneBundleMode ? <Route path="/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} /> : null}
        {standaloneBundleMode ? <Route path="/:funnelSlug/:slug" element={<PublicFunnelPage />} /> : null}
        <Route path="/f/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} />
        <Route path="/f/:funnelSlug/:slug" element={<PublicFunnelPage />} />
        {standaloneBundleMode ? null : <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />}
        {standaloneBundleMode ? null : (
          <Route
            path="/workspaces"
            element={
              <RequireAuth>
                <WorkspacesPage />
              </RequireAuth>
            }
          />
        )}
        {standaloneBundleMode ? null : (
          <Route
            path="/workspaces/new"
            element={
              <RequireAuth>
                <WorkspaceOnboardingPage />
              </RequireAuth>
            }
          />
        )}
        {standaloneBundleMode ? null : (
          <Route
            path="/"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/workspaces/overview" replace />} />
            <Route path="workspaces/overview" element={<WorkspaceOverviewPage />} />
            <Route path="workspaces/brand" element={<BrandDesignSystemPage />} />
            <Route path="workspaces/products" element={<ProductsPage />} />
            <Route path="workspaces/products/:productId" element={<ProductDetailPage />} />
            <Route path="research/documents" element={<DocumentsPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="research/competitors" element={<Navigate to="/research?tab=brands" replace />} />
            <Route path="research/ad-library" element={<Navigate to="/research?tab=ads" replace />} />
            <Route path="research/funnels" element={<FunnelsPage />} />
            <Route path="research/funnels/:funnelId" element={<FunnelDetailPage />} />
            <Route path="research/funnels/:funnelId/pages/:pageId" element={<FunnelPageEditorPage />} />
            <Route path="explore/ads" element={<Navigate to="/research?tab=ads" replace />} />
            <Route path="explore/brands" element={<Navigate to="/research?tab=brands" replace />} />
            <Route path="creative-library" element={<CreativeLibraryPage />} />
            <Route path="claude-chat" element={<ClaudeChatPage />} />
            <Route path="workflows" element={<WorkflowsPage />} />
            <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
            <Route path="workflows/:workflowId/research/:stepKey" element={<ResearchDetailPage />} />
            <Route path="campaigns" element={<CampaignsPage />} />
            <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
          </Route>
        )}
        <Route path="*" element={<Navigate to={standaloneBundleMode ? "/" : "/workspaces"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
