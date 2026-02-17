import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { OnboardingWizard } from "@/components/clients/OnboardingWizard";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useProductContext } from "@/contexts/ProductContext";

export function WorkspaceOnboardingPage() {
  const navigate = useNavigate();
  const { selectWorkspace } = useWorkspace();
  const { selectProduct } = useProductContext();

  const handleComplete = ({
    clientId,
    clientName,
    productId,
    productName,
  }: {
    clientId: string;
    clientName?: string;
    productId: string;
    productName?: string;
  }) => {
    selectWorkspace(clientId, { name: clientName });
    selectProduct(productId, { name: productName, client_id: clientId });
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
            Create the client record and kick off onboarding. We’ll run research and generate canon, strategy, and angle plans.
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
                "Capture key details and goals",
                "Run baseline research and canon generation",
                "Prepare strategy + angle scaffolds",
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 text-sm text-content">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 text-accent" />
                  <span className="text-content-muted">{item}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-surface p-6 shadow-none lg:h-[clamp(560px,calc(100vh-240px),760px)] lg:overflow-hidden">
            <OnboardingWizard variant="page" triggerLabel="Start onboarding" onCompleted={handleComplete} />
          </div>
        </div>
      </div>
    </div>
  );
}
