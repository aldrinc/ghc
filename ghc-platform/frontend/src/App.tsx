import type { ReactNode } from "react";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import { Navigate, Route, Routes, BrowserRouter } from "react-router-dom";
import { AppShell } from "@/app/AppShell";
import { DocumentsPage } from "@/pages/research/DocumentsPage";
import { CompetitorsPage } from "@/pages/research/CompetitorsPage";
import { AdLibraryPage } from "@/pages/research/AdLibraryPage";
import { FunnelsPage } from "@/pages/research/FunnelsPage";
import { FunnelDetailPage } from "@/pages/research/funnels/FunnelDetailPage";
import { FunnelPageEditorPage } from "@/pages/research/funnels/FunnelPageEditorPage";
import { ExploreAdsPage } from "@/pages/explore/ExploreAdsPage";
import { ExploreBrandsPage } from "@/pages/explore/ExploreBrandsPage";
import { StrategySheetPage } from "@/pages/strategy/StrategySheetPage";
import { ExperimentsPage } from "@/pages/experiments/ExperimentsPage";
import { CreativeLibraryPage } from "@/pages/library/CreativeLibraryPage";
import { WorkspacesPage } from "@/pages/workspaces/WorkspacesPage";
import { WorkspaceOnboardingPage } from "@/pages/workspaces/WorkspaceOnboardingPage";
import { WorkspaceOverviewPage } from "@/pages/workspaces/WorkspaceOverviewPage";
import { WorkflowsPage } from "@/pages/workflows/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/workflows/WorkflowDetailPage";
import { ResearchDetailPage } from "@/pages/workflows/ResearchDetailPage";
import { CampaignsPage } from "@/pages/campaigns/CampaignsPage";
import { CampaignDetailPage } from "@/pages/campaigns/CampaignDetailPage";
import { WorkspaceProvider } from "@/contexts/WorkspaceContext";
import { PublicFunnelEntryRedirectPage } from "@/pages/public/PublicFunnelEntryRedirectPage";
import { PublicFunnelPage } from "@/pages/public/PublicFunnelPage";

function RequireAuth({ children }: { children: ReactNode }) {
  return (
    <>
      <SignedIn>
        <WorkspaceProvider>{children}</WorkspaceProvider>
      </SignedIn>
      <SignedOut>
        <Navigate to="/sign-in" replace />
      </SignedOut>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/f/:publicId" element={<PublicFunnelEntryRedirectPage />} />
        <Route path="/f/:publicId/:slug" element={<PublicFunnelPage />} />
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
        <Route
          path="/workspaces"
          element={
            <RequireAuth>
              <WorkspacesPage />
            </RequireAuth>
          }
        />
        <Route
          path="/workspaces/new"
          element={
            <RequireAuth>
              <WorkspaceOnboardingPage />
            </RequireAuth>
          }
        />
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
          <Route path="research/documents" element={<DocumentsPage />} />
          <Route path="research/competitors" element={<CompetitorsPage />} />
          <Route path="research/ad-library" element={<AdLibraryPage />} />
          <Route path="research/funnels" element={<FunnelsPage />} />
          <Route path="research/funnels/:funnelId" element={<FunnelDetailPage />} />
          <Route path="research/funnels/:funnelId/pages/:pageId" element={<FunnelPageEditorPage />} />
          <Route path="explore/ads" element={<ExploreAdsPage />} />
          <Route path="explore/brands" element={<ExploreBrandsPage />} />
          <Route path="strategy-sheet" element={<StrategySheetPage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="creative-library" element={<CreativeLibraryPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
          <Route path="workflows/:workflowId/research/:stepKey" element={<ResearchDetailPage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/workspaces" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
