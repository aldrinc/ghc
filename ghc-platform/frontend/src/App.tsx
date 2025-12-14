import type { ReactNode } from "react";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import { Navigate, Route, Routes, BrowserRouter } from "react-router-dom";
import { AppShell } from "@/app/AppShell";
import { TasksPage } from "@/pages/tasks/TasksPage";
import { ClientsPage } from "@/pages/clients/ClientsPage";
import { ClientDetailPage } from "@/pages/clients/ClientDetailPage";
import { CampaignsPage } from "@/pages/campaigns/CampaignsPage";
import { CampaignDetailPage } from "@/pages/campaigns/CampaignDetailPage";
import { LibraryPage } from "@/pages/library/LibraryPage";
import { WorkflowsPage } from "@/pages/workflows/WorkflowsPage";
import { WorkflowDetailPage } from "@/pages/workflows/WorkflowDetailPage";
import { ResearchDetailPage } from "@/pages/workflows/ResearchDetailPage";

function RequireAuth({ children }: { children: ReactNode }) {
  return (
    <>
      <SignedIn>{children}</SignedIn>
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
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/:clientId" element={<ClientDetailPage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="campaigns/:campaignId" element={<CampaignDetailPage />} />
          <Route path="library" element={<LibraryPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="workflows/:workflowId" element={<WorkflowDetailPage />} />
          <Route path="workflows/:workflowId/research/:stepKey" element={<ResearchDetailPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
