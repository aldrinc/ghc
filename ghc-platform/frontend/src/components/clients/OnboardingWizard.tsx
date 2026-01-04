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
  { key: "offers", label: "Offers", description: "Offers/products and goals", requiredFields: ["offers"] },
  { key: "funnel", label: "Funnel", description: "Funnel notes" },
  { key: "review", label: "Review", description: "Confirm and submit" },
];

type WizardState = {
  client_name: string;
  client_industry: string;
  business_type: "new" | "existing";
  brand_story: string;
  offers: string;
  goals: string;
  funnel_notes: string;
  competitor_urls: string;
};

const baseState: WizardState = {
  client_name: "",
  client_industry: "",
  business_type: "new",
  brand_story: "",
  offers: "",
  goals: "",
  funnel_notes: "",
  competitor_urls: "",
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
  onCompleted?: (clientId: string, clientName?: string) => void;
  variant?: "modal" | "page";
};

export function OnboardingWizard({
  clientId,
  clientName,
  clientIndustry,
  triggerLabel = "Start onboarding",
  onCompleted,
  variant = "modal",
}: OnboardingWizardProps) {
  const isPage = variant === "page";
  const [open, setOpen] = useState(isPage);
  const [stepIndex, setStepIndex] = useState(0);
  const [state, setState] = useState<WizardState>(() => initialState(clientName, clientIndustry));
  const [activeClientId, setActiveClientId] = useState<string | null>(clientId ?? null);
  const onboarding = useStartOnboarding();
  const createClient = useCreateClient();

  useEffect(() => {
    if (!open && !isPage) {
      setState(initialState(clientName, clientIndustry));
      setStepIndex(0);
      setActiveClientId(clientId ?? null);
    }
  }, [open, clientId, clientName, clientIndustry, isPage]);

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
    const requiredFields = ["brand_story", "offers"];
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
      funnel_notes: state.funnel_notes || undefined,
      goals: state.goals ? state.goals.split(",").map((g) => g.trim()).filter(Boolean) : undefined,
      competitor_urls: undefined as string[] | undefined,
    };
    const competitorList = state.competitor_urls
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (competitorList.length) {
      const invalid = competitorList.filter((url) => {
        try {
          const parsed = new URL(url);
          return parsed.protocol !== "http:" && parsed.protocol !== "https:";
        } catch {
          return true;
        }
      });
      if (invalid.length) {
        toast.error("Competitor URLs must be valid http/https links.");
        return;
      }
      payload.competitor_urls = competitorList;
    }
    try {
      const ensuredClientId = await ensureClient();
      await onboarding.mutateAsync({ clientId: ensuredClientId, payload });
      resetWizard();
      setOpen(false);
      onCompleted?.(ensuredClientId, state.client_name.trim() || clientName);
    } catch (err) {
      // errors are surfaced via mutation onError handlers
    }
  };

  const content = (
    <div className="space-y-4">
      {!isPage && (
        <>
          <DialogTitle>Workspace onboarding</DialogTitle>
          <DialogDescription>Create the workspace and capture onboarding details in one flow.</DialogDescription>
        </>
      )}
      {isPage && (
        <div>
          <div className="text-lg font-semibold text-content">Workspace onboarding</div>
          <div className="text-sm text-content-muted">Capture client details and launch the onboarding workflow.</div>
        </div>
      )}
      <Progress value={progress} />
      <div>
        <div className="text-sm font-semibold text-content">{currentStep.label}</div>
        {currentStep.description ? <div className="text-xs text-content-muted">{currentStep.description}</div> : null}
      </div>

      <FormRoot className="space-y-3">
        {currentStep.key === "basics" && (
          <>
            <FieldRoot name="client_name" required>
              <FieldLabel>Workspace name</FieldLabel>
              <FieldDescription>Creates the workspace (client) before starting onboarding.</FieldDescription>
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
            <FieldRoot name="competitor_urls">
              <FieldLabel>Competitor URLs</FieldLabel>
              <FieldDescription>Optional. One URL per line. We’ll use these as seed competitors.</FieldDescription>
              <FieldControl
                value={state.competitor_urls}
                onChange={(e) => setState((s) => ({ ...s, competitor_urls: e.target.value }))}
                render={(props) => (
                  <textarea
                    {...props}
                    rows={3}
                    className={cn(
                      "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-content shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 focus-visible:ring-offset-2 focus-visible:ring-offset-surface placeholder:text-content-muted",
                      props.className
                    )}
                    placeholder="https://competitor1.com\nhttps://competitor2.com"
                  />
                )}
              />
              <FieldError />
            </FieldRoot>
          </>
        )}

        {currentStep.key === "funnel" && (
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
        )}

        {currentStep.key === "review" && (
          <div className="space-y-2 text-sm text-content">
            <div className="font-semibold text-content">Review details</div>
            <div className="rounded-lg border border-border bg-surface-2 p-3 shadow-inner">
              <p><strong>Workspace name:</strong> {state.client_name || "Missing"}</p>
              <p><strong>Industry:</strong> {state.client_industry || "Not set"}</p>
              <p><strong>Business type:</strong> {state.business_type}</p>
              <p><strong>Brand story:</strong> {state.brand_story || "Missing"}</p>
              <p><strong>Offers:</strong> {state.offers || "Missing"}</p>
              {state.goals && <p><strong>Goals:</strong> {state.goals}</p>}
              {state.funnel_notes && <p><strong>Funnel notes:</strong> {state.funnel_notes}</p>}
              {state.competitor_urls && (
                <p className="whitespace-pre-line">
                  <strong>Competitor URLs:</strong> {state.competitor_urls}
                </p>
              )}
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
      {!isPage && (
        <DialogClose
          className={buttonClasses({ variant: "ghost", size: "sm", className: "text-content-muted" })}
          disabled={isSubmitting}
        >
          Cancel
        </DialogClose>
      )}
    </div>
  );

  if (isPage) {
    return content;
  }

  return (
    <DialogRoot open={open} onOpenChange={setOpen}>
      <DialogTrigger className={buttonClasses({ size: "sm" })}>{triggerLabel}</DialogTrigger>
      <DialogContent>{content}</DialogContent>
    </DialogRoot>
  );
}
