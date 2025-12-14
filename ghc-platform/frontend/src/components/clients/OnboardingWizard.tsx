import { useEffect, useMemo, useState } from "react";
import {
  DialogRoot,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import { Button, buttonClasses } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { FieldControl, FieldDescription, FieldError, FieldLabel, FieldRoot, FormRoot } from "@/components/ui/field";
import { useCreateClient, useStartOnboarding } from "@/api/clients";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { Client } from "@/types/common";

type WizardStep = {
  key: string;
  label: string;
  description?: string;
  requiredFields?: string[];
};

const steps: WizardStep[] = [
  { key: "basics", label: "Basics", description: "Business type and brand story", requiredFields: ["brand_story"] },
  { key: "markets", label: "Markets", description: "Primary markets and languages", requiredFields: ["primary_markets", "primary_languages"] },
  { key: "offers", label: "Offers", description: "Offers/products and goals", requiredFields: ["offers"] },
  { key: "constraints", label: "Constraints", description: "Constraints and competitors" },
  { key: "funnel", label: "Funnel", description: "Business model and funnel notes" },
  { key: "review", label: "Review", description: "Confirm and submit" },
];

type WizardState = {
  client_name: string;
  client_industry: string;
  business_type: "new" | "existing";
  brand_story: string;
  offers: string;
  primary_markets: string;
  primary_languages: string;
  constraints: string;
  competitor_domains: string;
  goals: string;
  funnel_notes: string;
  business_model: string;
};

const baseState: WizardState = {
  client_name: "",
  client_industry: "",
  business_type: "new",
  brand_story: "",
  offers: "",
  primary_markets: "",
  primary_languages: "",
  constraints: "",
  competitor_domains: "",
  goals: "",
  funnel_notes: "",
  business_model: "",
};

const initialState = (clientName?: string, clientIndustry?: string): WizardState => ({
  ...baseState,
  client_name: clientName || "",
  client_industry: clientIndustry || "",
});

type OnboardingWizardProps = {
  clientId?: string;
  clientName?: string;
  clientIndustry?: string;
  triggerLabel?: string;
  onCompleted?: (clientId: string) => void;
};

export function OnboardingWizard({
  clientId,
  clientName,
  clientIndustry,
  triggerLabel = "Start onboarding",
  onCompleted,
}: OnboardingWizardProps) {
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [state, setState] = useState<WizardState>(() => initialState(clientName, clientIndustry));
  const [activeClientId, setActiveClientId] = useState<string | null>(clientId ?? null);
  const onboarding = useStartOnboarding();
  const createClient = useCreateClient();

  useEffect(() => {
    if (!open) {
      setState(initialState(clientName, clientIndustry));
      setStepIndex(0);
      setActiveClientId(clientId ?? null);
    }
  }, [open, clientId, clientName, clientIndustry]);

  const currentStep = steps[stepIndex];
  const progress = Math.round(((stepIndex + 1) / steps.length) * 100);
  const requiresClientName = !activeClientId;
  const isSubmitting = onboarding.isPending || createClient.isPending;

  const canNext = useMemo(() => {
    const hasRequired = currentStep.requiredFields
      ? currentStep.requiredFields.every((field) => {
          const value = (state as Record<string, string>)[field];
          return typeof value === "string" && value.trim().length > 0;
        })
      : true;
    const needsName = currentStep.key === "basics" && requiresClientName;
    const hasName = !needsName || Boolean(state.client_name.trim());
    return hasRequired && hasName;
  }, [currentStep, requiresClientName, state]);

  const goNext = () => {
    if (stepIndex < steps.length - 1) setStepIndex((i) => i + 1);
  };
  const goPrev = () => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  };

  const resetWizard = () => {
    setState(initialState(clientName, clientIndustry));
    setStepIndex(0);
    setActiveClientId(clientId ?? null);
  };

  const ensureClient = async (): Promise<string> => {
    if (activeClientId) return activeClientId;
    const created = (await createClient.mutateAsync({
      name: state.client_name.trim(),
      industry: state.client_industry.trim() || undefined,
    })) as Client;
    if (!created?.id) {
      throw new Error("Client creation failed");
    }
    setActiveClientId(created.id);
    return created.id;
  };

  const handleSubmit = async () => {
    const requiredFields = ["brand_story", "offers", "primary_markets", "primary_languages"];
    const missing = requiredFields.filter((field) => !(state as Record<string, string>)[field]?.trim());
    if (missing.length) {
      toast.error("Please fill required fields before submitting.");
      return;
    }
    if (requiresClientName && !state.client_name.trim()) {
      toast.error("Client name is required.");
      return;
    }
    const payload = {
      business_type: state.business_type,
      brand_story: state.brand_story.trim(),
      offers: state.offers.split(",").map((o) => o.trim()).filter(Boolean),
      constraints: state.constraints ? state.constraints.split(",").map((c) => c.trim()).filter(Boolean) : undefined,
      competitor_domains: state.competitor_domains
        ? state.competitor_domains.split(",").map((c) => c.trim()).filter(Boolean)
        : undefined,
      funnel_notes: state.funnel_notes || undefined,
      business_model: state.business_model || undefined,
      primary_markets: state.primary_markets.split(",").map((m) => m.trim()).filter(Boolean),
      primary_languages: state.primary_languages.split(",").map((l) => l.trim()).filter(Boolean),
      goals: state.goals ? state.goals.split(",").map((g) => g.trim()).filter(Boolean) : undefined,
    };
    try {
      const ensuredClientId = await ensureClient();
      await onboarding.mutateAsync({ clientId: ensuredClientId, payload });
      resetWizard();
      setOpen(false);
      onCompleted?.(ensuredClientId);
    } catch (err) {
      // errors are surfaced via mutation onError handlers
    }
  };

  return (
    <DialogRoot open={open} onOpenChange={setOpen}>
      <DialogTrigger className={buttonClasses({ size: "sm" })}>{triggerLabel}</DialogTrigger>
      <DialogContent>
        <DialogTitle>Client onboarding</DialogTitle>
        <DialogDescription>Create the client record and capture onboarding details in one flow.</DialogDescription>
        <div className="mt-4 space-y-4">
          <Progress value={progress} />
          <div>
            <div className="text-sm font-semibold text-content">{currentStep.label}</div>
            {currentStep.description ? <div className="text-xs text-content-muted">{currentStep.description}</div> : null}
          </div>

          <FormRoot className="space-y-3">
            {currentStep.key === "basics" && (
              <>
                <FieldRoot name="client_name" required>
                  <FieldLabel>Client name</FieldLabel>
                  <FieldDescription>Creates the client before starting onboarding.</FieldDescription>
                  <Input
                    value={state.client_name}
                    onChange={(e) => setState((s) => ({ ...s, client_name: e.target.value }))}
                    required
                    placeholder="Acme Corp"
                    disabled={Boolean(activeClientId)}
                  />
                  <FieldError />
                </FieldRoot>
                <FieldRoot name="client_industry">
                  <FieldLabel>Industry</FieldLabel>
                  <FieldDescription>Optional context for filtering and reporting.</FieldDescription>
                  <Input
                    value={state.client_industry}
                    onChange={(e) => setState((s) => ({ ...s, client_industry: e.target.value }))}
                    placeholder="E-commerce"
                    disabled={Boolean(activeClientId)}
                  />
                </FieldRoot>
                <FieldRoot name="business_type">
                  <FieldLabel>Business type</FieldLabel>
                  <div className="flex gap-4 text-sm text-content">
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        checked={state.business_type === "new"}
                        onChange={() => setState((s) => ({ ...s, business_type: "new" }))}
                      />
                      New business (supported)
                    </label>
                    <label className="flex items-center gap-2 text-content-muted">
                      <input
                        type="radio"
                        checked={state.business_type === "existing"}
                        onChange={() => setState((s) => ({ ...s, business_type: "existing" }))}
                      />
                      Existing business (coming soon)
                    </label>
                  </div>
                </FieldRoot>
                <FieldRoot name="brand_story" required>
                  <FieldLabel>Brand story / context</FieldLabel>
                  <FieldDescription>Required. What should we know before generating canon/metrics?</FieldDescription>
                  <FieldControl
                    value={state.brand_story}
                    onChange={(e) => setState((s) => ({ ...s, brand_story: e.target.value }))}
                    render={(props) => (
                      <textarea
                        {...props}
                        rows={3}
                        className={cn(
                          "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted",
                          props.className
                        )}
                      />
                    )}
                  />
                  <FieldError />
                </FieldRoot>
              </>
            )}

            {currentStep.key === "markets" && (
              <>
                <FieldRoot name="primary_markets" required>
                  <FieldLabel>Primary markets</FieldLabel>
                  <FieldDescription>Comma-separated list of markets (e.g., US, UK, AU).</FieldDescription>
                  <Input
                    value={state.primary_markets}
                    onChange={(e) => setState((s) => ({ ...s, primary_markets: e.target.value }))}
                    placeholder="US, UK"
                  />
                  <FieldError />
                </FieldRoot>
                <FieldRoot name="primary_languages" required>
                  <FieldLabel>Primary languages</FieldLabel>
                  <Input
                    value={state.primary_languages}
                    onChange={(e) => setState((s) => ({ ...s, primary_languages: e.target.value }))}
                    placeholder="English, Spanish"
                  />
                  <FieldError />
                </FieldRoot>
              </>
            )}

            {currentStep.key === "offers" && (
              <>
                <FieldRoot name="offers" required>
                  <FieldLabel>Offers / products</FieldLabel>
                  <FieldDescription>Comma-separated list of offers or hero products.</FieldDescription>
                  <Input
                    value={state.offers}
                    onChange={(e) => setState((s) => ({ ...s, offers: e.target.value }))}
                    placeholder="Offer A, Offer B"
                  />
                  <FieldError />
                </FieldRoot>
                <FieldRoot name="goals">
                  <FieldLabel>Goals</FieldLabel>
                  <FieldDescription>Optional business goals (comma-separated).</FieldDescription>
                  <Input
                    value={state.goals}
                    onChange={(e) => setState((s) => ({ ...s, goals: e.target.value }))}
                    placeholder="Increase ROAS, New market launch"
                  />
                  <FieldError />
                </FieldRoot>
              </>
            )}

            {currentStep.key === "constraints" && (
              <>
                <FieldRoot name="constraints">
                  <FieldLabel>Constraints</FieldLabel>
                  <FieldDescription>Brand/legal constraints (comma-separated, optional).</FieldDescription>
                  <Input
                    value={state.constraints}
                    onChange={(e) => setState((s) => ({ ...s, constraints: e.target.value }))}
                    placeholder="No discounts, No medical claims"
                  />
                </FieldRoot>
                <FieldRoot name="competitor_domains">
                  <FieldLabel>Competitors</FieldLabel>
                  <FieldDescription>Competitor domains (comma-separated, optional).</FieldDescription>
                  <Input
                    value={state.competitor_domains}
                    onChange={(e) => setState((s) => ({ ...s, competitor_domains: e.target.value }))}
                    placeholder="competitor.com, rival.com"
                  />
                </FieldRoot>
              </>
            )}

            {currentStep.key === "funnel" && (
              <>
                <FieldRoot name="business_model">
                  <FieldLabel>Business model</FieldLabel>
                  <FieldDescription>Short description of the model (e.g., subscription DTC). Optional.</FieldDescription>
                  <Input
                    value={state.business_model}
                    onChange={(e) => setState((s) => ({ ...s, business_model: e.target.value }))}
                    placeholder="DTC subscription"
                  />
                </FieldRoot>
                <FieldRoot name="funnel_notes">
                  <FieldLabel>Funnel notes</FieldLabel>
                  <FieldDescription>Optional funnel notes or channel preferences.</FieldDescription>
                  <FieldControl
                    value={state.funnel_notes}
                    onChange={(e) => setState((s) => ({ ...s, funnel_notes: e.target.value }))}
                    render={(props) => (
                      <textarea
                        {...props}
                        rows={2}
                        className={cn(
                          "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted",
                          props.className
                        )}
                      />
                    )}
                  />
                </FieldRoot>
              </>
            )}

            {currentStep.key === "review" && (
              <div className="space-y-2 text-sm text-content">
                <div className="font-semibold text-content">Review details</div>
                <div className="rounded-lg border border-border bg-surface-2 p-3 shadow-inner">
                  <p><strong>Client name:</strong> {state.client_name || "Missing"}</p>
                  <p><strong>Industry:</strong> {state.client_industry || "Not set"}</p>
                  <p><strong>Business type:</strong> {state.business_type}</p>
                  <p><strong>Brand story:</strong> {state.brand_story || "Missing"}</p>
                  <p><strong>Markets:</strong> {state.primary_markets || "Missing"}</p>
                  <p><strong>Languages:</strong> {state.primary_languages || "Missing"}</p>
                  <p><strong>Offers:</strong> {state.offers || "Missing"}</p>
                  {state.goals && <p><strong>Goals:</strong> {state.goals}</p>}
                  {state.constraints && <p><strong>Constraints:</strong> {state.constraints}</p>}
                  {state.competitor_domains && <p><strong>Competitors:</strong> {state.competitor_domains}</p>}
                  {state.business_model && <p><strong>Business model:</strong> {state.business_model}</p>}
                  {state.funnel_notes && <p><strong>Funnel notes:</strong> {state.funnel_notes}</p>}
                </div>
              </div>
            )}
          </FormRoot>

            <div className="flex items-center justify-between pt-2">
              <Button variant="secondary" size="sm" onClick={goPrev} disabled={stepIndex === 0 || isSubmitting}>
                Back
              </Button>
              {stepIndex < steps.length - 1 ? (
                <Button size="sm" onClick={goNext} disabled={!canNext || isSubmitting}>
                  Next
                </Button>
              ) : (
                <Button size="sm" onClick={handleSubmit} disabled={isSubmitting}>
                  {isSubmitting ? "Starting…" : "Start onboarding"}
                </Button>
              )}
            </div>
            <DialogClose
              className={buttonClasses({ variant: "ghost", size: "sm", className: "text-content-muted" })}
              disabled={isSubmitting}
            >
              Cancel
            </DialogClose>
          </div>
        </DialogContent>
      </DialogRoot>
    );
}
