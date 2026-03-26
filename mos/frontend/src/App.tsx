import type { ReactNode } from "react";
import { SignedIn, SignedOut } from "@clerk/clerk-react";
import { SignInPage } from "@/pages/auth/SignInPage";
import { Navigate, Route, Routes, BrowserRouter, useParams } from "react-router-dom";
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
import { SitesPage } from "@/pages/workspaces/SitesPage";
import { SiteImportsPage } from "@/pages/workspaces/SiteImportsPage";
import { SiteDetailPage } from "@/pages/workspaces/SiteDetailPage";
import { SitePageEditorPage } from "@/pages/workspaces/SitePageEditorPage";
import { SiteFunnelDetailPage } from "@/pages/workspaces/sites/SiteFunnelDetailPage";
import { WorkflowsPage } from "@/pages/workflows/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/workflows/WorkflowDetailPage";
import { ResearchDetailPage } from "@/pages/workflows/ResearchDetailPage";
import { CampaignsPage } from "@/pages/campaigns/CampaignsPage";
import { CampaignLayout } from "@/pages/campaigns/CampaignLayout";
import { CampaignOverviewTab } from "@/pages/campaigns/tabs/CampaignOverviewTab";
import { CampaignStrategyTab } from "@/pages/campaigns/tabs/CampaignStrategyTab";
import { CampaignAnglesTab } from "@/pages/campaigns/tabs/CampaignAnglesTab";
import { CampaignCreativeTab } from "@/pages/campaigns/tabs/CampaignCreativeTab";
import { CampaignDeliveryTab } from "@/pages/campaigns/tabs/CampaignDeliveryTab";
import { CampaignPublishTab } from "@/pages/campaigns/tabs/CampaignPublishTab";
import { PlatformPublishWorkspace } from "@/pages/campaigns/tabs/PlatformPublishWorkspace";
import { WorkspaceProvider } from "@/contexts/WorkspaceContext";
import { ProductProvider } from "@/contexts/ProductContext";
import { ClaudeChatPage } from "@/pages/claude/ClaudeChatPage";
import { PublicFunnelEntryRedirectPage } from "@/pages/public/PublicFunnelEntryRedirectPage";
import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";
import { PublicFunnelRootRedirectPage } from "@/pages/public/PublicFunnelRootRedirectPage";
import { CommercePage } from "@/pages/commerce/CommercePage";
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

function LegacySiteImportRedirect() {
  const { importId } = useParams<{ importId: string }>();
  return <Navigate to={`/workspaces/sites/imports/${importId}`} replace />;
}

function App() {
  const standaloneBundleMode = isStandaloneBundleMode();

  return (
    <BrowserRouter>
      <Routes>
        {standaloneBundleMode ? <Route path="/" element={<PublicFunnelRootRedirectPage />} /> : null}
        {standaloneBundleMode ? <Route path="/:productSlug/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} /> : null}
        {standaloneBundleMode ? <Route path="/:productSlug/:funnelSlug/*" element={<PublicFunnelPage />} /> : null}
        <Route path="/f/:productSlug/:funnelSlug" element={<PublicFunnelEntryRedirectPage />} />
        <Route path="/f/:productSlug/:funnelSlug/*" element={<PublicFunnelPage />} />
        {standaloneBundleMode ? null : <Route path="/sign-in/*" element={<SignInPage />} />}
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
            {/* Sites - canonical workspace destination */}
            <Route path="workspaces/sites" element={<SitesPage />} />
            <Route path="workspaces/sites/templates" element={<SitesPage />} />
            <Route path="workspaces/sites/templates/:templateId" element={<SitesPage />} />
            <Route path="workspaces/sites/imports" element={<SiteImportsPage />} />
            <Route path="workspaces/sites/imports/:importId" element={<SiteImportsPage />} />
            <Route path="workspaces/sites/:siteId" element={<SiteDetailPage />} />
            <Route path="workspaces/sites/:siteId/pages/:pageId" element={<SitePageEditorPage />} />
            <Route path="workspaces/sites/:siteId/funnels" element={<SiteDetailPage />} />
            <Route path="workspaces/sites/:siteId/funnels/:funnelId" element={<SiteFunnelDetailPage />} />
            {/* Legacy redirects */}
            <Route path="workspaces/store-templates" element={<Navigate to="/workspaces/sites" replace />} />
            <Route path="workspaces/store-templates/import/:importId" element={<LegacySiteImportRedirect />} />
            <Route path="workspaces/imports/*" element={<Navigate to="/workspaces/sites/imports" replace />} />
            <Route path="workspaces/products" element={<ProductsPage />} />
            <Route path="workspaces/products/:productId" element={<ProductDetailPage />} />
            <Route path="research/documents" element={<DocumentsPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="research/competitors" element={<Navigate to="/research?tab=brands" replace />} />
            <Route path="research/ad-library" element={<Navigate to="/research?tab=ads" replace />} />
            {/* Research Funnels - cross-site funnel index */}
            <Route path="research/funnels" element={<FunnelsPage />} />
            <Route path="research/funnels/:funnelId" element={<FunnelDetailPage />} />
            <Route path="research/funnels/:funnelId/pages/:pageId" element={<FunnelPageEditorPage />} />
            <Route path="explore/ads" element={<Navigate to="/research?tab=ads" replace />} />
            <Route path="explore/brands" element={<Navigate to="/research?tab=brands" replace />} />
            <Route path="commerce" element={<CommercePage />} />
            <Route path="creative-library" element={<CreativeLibraryPage />} />
            <Route path="claude-chat" element={<ClaudeChatPage />} />
            {/* Strategy runs (renamed from workflows) */}
            <Route path="strategy" element={<WorkflowsPage />} />
            <Route path="strategy/:workflowId" element={<WorkflowDetailPage />} />
            <Route path="strategy/:workflowId/research/:stepKey" element={<ResearchDetailPage />} />
            {/* Legacy workflow redirects */}
            <Route path="workflows" element={<Navigate to="/strategy" replace />} />
            <Route path="workflows/:workflowId" element={<Navigate to="/strategy" replace />} />
            {/* Campaigns with layout shell */}
            <Route path="campaigns" element={<CampaignsPage />} />
            <Route path="campaigns/:campaignId" element={<CampaignLayout />}>
              <Route index element={<Navigate to="overview" replace />} />
              <Route path="overview" element={<CampaignOverviewTab />} />
              <Route path="strategy" element={<CampaignStrategyTab />} />
              <Route path="angles" element={<CampaignAnglesTab />} />
              <Route path="delivery" element={<CampaignDeliveryTab />} />
              <Route path="creative" element={<CampaignCreativeTab />} />
              <Route path="publish" element={<CampaignPublishTab />} />
              <Route path="publish/:platformId" element={<PlatformPublishWorkspace />} />
              {/* Legacy routes */}
              <Route path="meta" element={<Navigate to="../publish/meta" replace />} />
              <Route path="funnels" element={<Navigate to="../delivery" replace />} />
            </Route>
          </Route>
        )}
        <Route path="*" element={<Navigate to={standaloneBundleMode ? "/" : "/workspaces"} replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
