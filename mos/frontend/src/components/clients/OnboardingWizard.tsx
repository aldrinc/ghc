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
  { key: "product", label: "Product", description: "Core product details", requiredFields: ["product_name"] },
  { key: "funnel", label: "Funnel", description: "Funnel notes" },
  { key: "review", label: "Review", description: "Confirm and submit" },
];

type WizardState = {
  client_name: string;
  client_industry: string;
  business_type: "new" | "existing";
  brand_story: string;
  product_name: string;
  product_description: string;
  product_category: string;
  primary_benefits: string;
  feature_bullets: string;
  guarantee_text: string;
  disclaimers: string;
  goals: string;
  funnel_notes: string;
  competitor_urls: string;
};

const baseState: WizardState = {
  client_name: "",
  client_industry: "",
  business_type: "new",
  brand_story: "",
  product_name: "",
  product_description: "",
  product_category: "",
  primary_benefits: "",
  feature_bullets: "",
  guarantee_text: "",
  disclaimers: "",
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
  onCompleted?: (payload: {
    clientId: string;
    clientName?: string;
    productId: string;
    productName?: string;
  }) => void;
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
    const requiredFields = ["brand_story", "product_name"];
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
      product_name: state.product_name.trim(),
      product_description: state.product_description.trim() || undefined,
      product_category: state.product_category.trim() || undefined,
      primary_benefits: state.primary_benefits.trim()
        ? state.primary_benefits.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
      feature_bullets: state.feature_bullets.trim()
        ? state.feature_bullets.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
      guarantee_text: state.guarantee_text.trim() || undefined,
      disclaimers: state.disclaimers.trim()
        ? state.disclaimers.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
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
      const response = await onboarding.mutateAsync({ clientId: ensuredClientId, payload });
      const productId = (response as any)?.product_id;
      if (!productId) {
        toast.error("Onboarding started but no product ID was returned.");
        return;
      }
      resetWizard();
      setOpen(false);
      onCompleted?.({
        clientId: ensuredClientId,
        clientName: state.client_name.trim() || clientName,
        productId,
        productName: (response as any)?.product_name || state.product_name.trim(),
      });
    } catch (err) {
      // errors are surfaced via mutation onError handlers
    }
  };

  const content = (
    <div className="space-y-4">
      {!isPage ? (
        <>
          <DialogTitle>Workspace onboarding</DialogTitle>
          <DialogDescription>Create the workspace and capture onboarding details in one flow.</DialogDescription>
          <Progress value={progress} />
        </>
      ) : (
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="text-sm font-semibold text-content">Onboarding flow</div>
            <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
              Step-by-step
            </span>
          </div>
          <Progress value={progress} />
          <p className="text-sm text-content-muted">
            We’ll set up the workspace and start the first workflow automatically.
          </p>
        </div>
      )}
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

        {currentStep.key === "product" && (
          <>
            <FieldRoot name="product_name" required>
              <FieldLabel>Product name</FieldLabel>
              <FieldDescription>Required. The core product for this onboarding run.</FieldDescription>
              <Input
                value={state.product_name}
                onChange={(e) => setState((s) => ({ ...s, product_name: e.target.value }))}
                placeholder="Herbal Sleep Drops"
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="product_description">
              <FieldLabel>Description</FieldLabel>
              <FieldDescription>Optional short description of the product.</FieldDescription>
              <Input
                value={state.product_description}
                onChange={(e) => setState((s) => ({ ...s, product_description: e.target.value }))}
                placeholder="Sleep support tincture with calming herbs."
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="product_category">
              <FieldLabel>Category</FieldLabel>
              <FieldDescription>Optional product category or niche.</FieldDescription>
              <Input
                value={state.product_category}
                onChange={(e) => setState((s) => ({ ...s, product_category: e.target.value }))}
                placeholder="Supplements, SaaS, Courses"
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="primary_benefits">
              <FieldLabel>Primary benefits</FieldLabel>
              <FieldDescription>Optional comma-separated list.</FieldDescription>
              <Input
                value={state.primary_benefits}
                onChange={(e) => setState((s) => ({ ...s, primary_benefits: e.target.value }))}
                placeholder="Fall asleep faster, Wake refreshed"
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="feature_bullets">
              <FieldLabel>Feature bullets</FieldLabel>
              <FieldDescription>Optional comma-separated list.</FieldDescription>
              <Input
                value={state.feature_bullets}
                onChange={(e) => setState((s) => ({ ...s, feature_bullets: e.target.value }))}
                placeholder="Organic herbs, Fast-acting drops"
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="guarantee_text">
              <FieldLabel>Guarantee text</FieldLabel>
              <FieldDescription>Optional guarantee statement.</FieldDescription>
              <Input
                value={state.guarantee_text}
                onChange={(e) => setState((s) => ({ ...s, guarantee_text: e.target.value }))}
                placeholder="30-day money back guarantee"
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="disclaimers">
              <FieldLabel>Disclaimers</FieldLabel>
              <FieldDescription>Optional comma-separated list.</FieldDescription>
              <Input
                value={state.disclaimers}
                onChange={(e) => setState((s) => ({ ...s, disclaimers: e.target.value }))}
                placeholder="Not medical advice, Results may vary"
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
              <p><strong>Product name:</strong> {state.product_name || "Missing"}</p>
              {state.product_description && <p><strong>Description:</strong> {state.product_description}</p>}
              {state.product_category && <p><strong>Category:</strong> {state.product_category}</p>}
              {state.primary_benefits && <p><strong>Primary benefits:</strong> {state.primary_benefits}</p>}
              {state.feature_bullets && <p><strong>Feature bullets:</strong> {state.feature_bullets}</p>}
              {state.guarantee_text && <p><strong>Guarantee:</strong> {state.guarantee_text}</p>}
              {state.disclaimers && <p><strong>Disclaimers:</strong> {state.disclaimers}</p>}
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
