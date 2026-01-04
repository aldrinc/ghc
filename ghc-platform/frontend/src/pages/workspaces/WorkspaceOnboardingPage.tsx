import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { OnboardingWizard } from "@/components/clients/OnboardingWizard";
import { useWorkspace } from "@/contexts/WorkspaceContext";

export function WorkspaceOnboardingPage() {
  const navigate = useNavigate();
  const { selectWorkspace } = useWorkspace();

  const handleComplete = (clientId: string, clientName?: string) => {
    selectWorkspace(clientId, { name: clientName });
    navigate("/workspaces/overview");
  };

  return (
    <div className="min-h-screen bg-background text-foreground px-6 py-10">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <button
          onClick={() => navigate("/workspaces")}
          className="inline-flex items-center gap-2 text-sm font-medium text-content-muted transition hover:text-content"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to workspaces
        </button>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
            Workspace onboarding
          </p>
          <h1 className="text-3xl font-bold leading-tight text-content">Start a new workspace</h1>
          <p className="max-w-3xl text-base text-content-muted">
            Create the client record and kick off onboarding. We’ll run research and generate canon, strategy, and experiment plans.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[320px,1fr]">
          <div className="rounded-xl border border-border bg-surface p-6 shadow-none">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-content">What we’ll do</div>
              <p className="text-sm text-content-muted">
                We’ll handle the data collection and generate a ready-to-run stack of research and strategy.
              </p>
            </div>

            <div className="mt-6 space-y-3">
              {[
                "Capture client details and goals",
                "Run baseline research and canon generation",
                "Prepare strategy + experiment scaffolds",
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 text-sm text-content">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 text-accent" />
                  <span className="text-content-muted">{item}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 rounded-lg border border-border-strong bg-surface-hover px-4 py-3 text-sm text-content-muted">
              <span className="font-semibold text-content">Tip:</span> You can rerun onboarding anytime to refresh research or adjust positioning.
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface p-6 shadow-none">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-content">Onboarding flow</div>
                <p className="text-sm text-content-muted">
                  We’ll set up the workspace and start the first workflow automatically.
                </p>
              </div>
              <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
                Step-by-step
              </span>
            </div>

            <div className="rounded-lg border border-border bg-surface-hover p-4">
              <OnboardingWizard variant="page" triggerLabel="Start onboarding" onCompleted={handleComplete} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
