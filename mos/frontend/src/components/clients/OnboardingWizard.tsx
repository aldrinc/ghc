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
import { Textarea } from "@/components/ui/textarea";
import { FieldControl, FieldDescription, FieldError, FieldLabel, FieldRoot, FormRoot } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { useCreateClient, useStartOnboarding } from "@/api/clients";
import { toast } from "@/components/ui/toast";
import type { Client } from "@/types/common";

type WizardStep = {
  key: string;
  label: string;
  description?: string;
  requiredFields?: string[];
};

const steps: WizardStep[] = [
  { key: "basics", label: "Basics", description: "Business type and brand story", requiredFields: ["brand_story"] },
  {
    key: "product",
    label: "Product",
    description: "Add what we should scope research and strategy to.",
  },
  { key: "funnel", label: "Funnel", description: "Funnel notes" },
  { key: "review", label: "Review", description: "Confirm and submit" },
];

type ProductDraft = {
  product_name: string;
  product_description: string;
  product_category: string;
  primary_benefits: string;
  feature_bullets: string;
  guarantee_text: string;
  disclaimers: string;
  goals: string;
  competitor_urls: string;
};

const emptyProductDraft: ProductDraft = {
  product_name: "",
  product_description: "",
  product_category: "",
  primary_benefits: "",
  feature_bullets: "",
  guarantee_text: "",
  disclaimers: "",
  goals: "",
  competitor_urls: "",
};

type WizardState = {
  client_name: string;
  client_industry: string;
  business_type: "new" | "existing";
  brand_story: string;
  funnel_notes: string;
  products: ProductDraft[];
};

const baseState: WizardState = {
  client_name: "",
  client_industry: "",
  business_type: "new",
  brand_story: "",
  funnel_notes: "",
  products: [],
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
  const [isProductEditorOpen, setIsProductEditorOpen] = useState(false);
  const [editingProductIndex, setEditingProductIndex] = useState<number | null>(null);
  const [productDraft, setProductDraft] = useState<ProductDraft>(emptyProductDraft);
  const onboarding = useStartOnboarding();
  const createClient = useCreateClient();

  useEffect(() => {
    if (!open && !isPage) {
      setState(initialState(clientName, clientIndustry));
      setStepIndex(0);
      setActiveClientId(clientId ?? null);
      setIsProductEditorOpen(false);
      setEditingProductIndex(null);
      setProductDraft(emptyProductDraft);
    }
  }, [open, clientId, clientName, clientIndustry, isPage]);

  const currentStep = steps[stepIndex];
  const progress = Math.round(((stepIndex + 1) / steps.length) * 100);
  const requiresClientName = !activeClientId;
  const isSubmitting = onboarding.isPending || createClient.isPending;

  const canNext = useMemo(() => {
    if (currentStep.key === "basics") {
      const hasBrandStory = Boolean(state.brand_story.trim());
      const needsName = requiresClientName;
      const hasName = !needsName || Boolean(state.client_name.trim());
      return hasBrandStory && hasName;
    }
    if (currentStep.key === "product") {
      if (state.products.length !== 1) return false;
      return Boolean(state.products[0]?.product_name?.trim());
    }
    return true;
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
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
    setProductDraft(emptyProductDraft);
  };

  useEffect(() => {
    // Keep the wizard surface stable: close inline editors when leaving a step.
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
  }, [stepIndex]);

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
    const firstProduct = state.products[0];
    if (!state.brand_story.trim()) {
      toast.error("Brand story is required.");
      return;
    }
    if (state.products.length !== 1 || !firstProduct?.product_name?.trim()) {
      toast.error("Add exactly one product (product name is required).");
      return;
    }
    if (requiresClientName && !state.client_name.trim()) {
      toast.error("Client name is required.");
      return;
    }
    const payload = {
      business_type: state.business_type,
      brand_story: state.brand_story.trim(),
      product_name: firstProduct.product_name.trim(),
      product_description: firstProduct.product_description.trim() || undefined,
      product_category: firstProduct.product_category.trim() || undefined,
      primary_benefits: firstProduct.primary_benefits.trim()
        ? firstProduct.primary_benefits.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
      feature_bullets: firstProduct.feature_bullets.trim()
        ? firstProduct.feature_bullets.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
      guarantee_text: firstProduct.guarantee_text.trim() || undefined,
      disclaimers: firstProduct.disclaimers.trim()
        ? firstProduct.disclaimers.split(",").map((item) => item.trim()).filter(Boolean)
        : undefined,
      funnel_notes: state.funnel_notes || undefined,
      goals: firstProduct.goals ? firstProduct.goals.split(",").map((g) => g.trim()).filter(Boolean) : undefined,
      competitor_urls: undefined as string[] | undefined,
    };
    const competitorList = firstProduct.competitor_urls
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
        productName: (response as any)?.product_name || firstProduct.product_name.trim(),
      });
    } catch (err) {
      // errors are surfaced via mutation onError handlers
    }
  };

  const openAddProduct = () => {
    if (state.products.length >= 1) {
      toast.error("Only one product is supported right now.");
      return;
    }
    setProductDraft(emptyProductDraft);
    setEditingProductIndex(null);
    setIsProductEditorOpen(true);
  };

  const openEditProduct = (index: number) => {
    const existing = state.products[index];
    if (!existing) {
      toast.error("Product not found.");
      return;
    }
    setProductDraft(existing);
    setEditingProductIndex(index);
    setIsProductEditorOpen(true);
  };

  const closeProductEditor = () => {
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
    setProductDraft(emptyProductDraft);
  };

  const saveProduct = () => {
    if (!productDraft.product_name.trim()) {
      toast.error("Product name is required.");
      return;
    }
    if (editingProductIndex === null && state.products.length >= 1) {
      toast.error("Only one product is supported right now.");
      return;
    }
    const nextDraft: ProductDraft = {
      ...productDraft,
      product_name: productDraft.product_name.trim(),
    };
    setState((s) => {
      const nextProducts = [...s.products];
      if (editingProductIndex === null) {
        nextProducts.push(nextDraft);
      } else if (editingProductIndex >= 0 && editingProductIndex < nextProducts.length) {
        nextProducts[editingProductIndex] = nextDraft;
      } else {
        throw new Error("Cannot save product: invalid product index.");
      }
      return { ...s, products: nextProducts };
    });
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
  };

  const removeProduct = (index: number) => {
    setState((s) => ({ ...s, products: s.products.filter((_product, idx) => idx !== index) }));
    if (editingProductIndex === index) {
      closeProductEditor();
    } else if (editingProductIndex !== null && editingProductIndex > index) {
      setEditingProductIndex(editingProductIndex - 1);
    }
  };

  const stepHeader = (
    <div className="rounded-lg border border-border px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-content">{currentStep.label}</div>
          {currentStep.description ? (
            <div className="mt-1 text-xs text-content-muted">{currentStep.description}</div>
          ) : null}
        </div>
        <Badge tone="neutral" className="shrink-0">
          Step {stepIndex + 1} of {steps.length}
        </Badge>
      </div>
    </div>
  );

  const form = (
    <FormRoot className="space-y-4" onSubmit={(e) => e.preventDefault()}>
      {currentStep.key === "basics" && (
        <>
          <FieldRoot name="client_name">
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
          <FieldRoot name="brand_story">
            <FieldLabel>Brand story / context</FieldLabel>
            <FieldDescription>Required. What should we know before generating canon/metrics?</FieldDescription>
            <FieldControl
              value={state.brand_story}
              onChange={(e) => setState((s) => ({ ...s, brand_story: e.target.value }))}
              render={(props) => <Textarea {...props} rows={3} required />}
            />
            <FieldError />
          </FieldRoot>
        </>
      )}

      {currentStep.key === "product" && (
        <div className="space-y-4">
          {!state.products.length && !isProductEditorOpen ? (
            <div className="flex items-center justify-start">
              <Button variant="secondary" size="sm" onClick={openAddProduct} disabled={isSubmitting}>
                Add product
              </Button>
            </div>
          ) : null}

          {state.products.length ? (
            <div className="space-y-3">
              {state.products.map((product, idx) => (
                <div key={`${product.product_name}-${idx}`} className="rounded-lg border border-border p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-content">{product.product_name}</div>
                      <div className="mt-1 text-xs text-content-muted">
                        {product.product_category ? product.product_category : "Category not set"}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button variant="secondary" size="xs" onClick={() => openEditProduct(idx)} disabled={isSubmitting}>
                        Edit
                      </Button>
                      <Button variant="ghost" size="xs" onClick={() => removeProduct(idx)} disabled={isSubmitting}>
                        Remove
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {isProductEditorOpen ? (
            <div className="rounded-lg border border-border p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-content">
                    {editingProductIndex === null ? "Add product" : "Edit product"}
                  </div>
                  <div className="mt-1 text-xs text-content-muted">
                    Product details help generate canon, strategy, and angles.
                  </div>
                </div>
                <Badge tone="neutral" className="shrink-0">
                  Product {editingProductIndex === null ? state.products.length + 1 : editingProductIndex + 1}
                </Badge>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <FieldRoot name="product_name" className="md:col-span-2">
                  <FieldLabel>Product name</FieldLabel>
                  <FieldDescription>Required.</FieldDescription>
                  <Input
                    value={productDraft.product_name}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_name: e.target.value }))}
                    placeholder="Herbal Sleep Drops"
                    required
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="product_category">
                  <FieldLabel>Category</FieldLabel>
                  <FieldDescription>Optional product category or niche.</FieldDescription>
                  <Input
                    value={productDraft.product_category}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_category: e.target.value }))}
                    placeholder="Supplements, SaaS, Courses"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="goals">
                  <FieldLabel>Goals</FieldLabel>
                  <FieldDescription>Optional business goals (comma-separated).</FieldDescription>
                  <Input
                    value={productDraft.goals}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, goals: e.target.value }))}
                    placeholder="Increase ROAS, New market launch"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="product_description" className="md:col-span-2">
                  <FieldLabel>Description</FieldLabel>
                  <FieldDescription>Optional short description of the product.</FieldDescription>
                  <FieldControl
                    value={productDraft.product_description}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_description: e.target.value }))}
                    render={(props) => (
                      <Textarea {...props} rows={3} placeholder="Sleep support tincture with calming herbs." />
                    )}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="primary_benefits">
                  <FieldLabel>Primary benefits</FieldLabel>
                  <FieldDescription>Optional comma-separated list.</FieldDescription>
                  <Input
                    value={productDraft.primary_benefits}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, primary_benefits: e.target.value }))}
                    placeholder="Fall asleep faster, Wake refreshed"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="feature_bullets">
                  <FieldLabel>Feature bullets</FieldLabel>
                  <FieldDescription>Optional comma-separated list.</FieldDescription>
                  <Input
                    value={productDraft.feature_bullets}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, feature_bullets: e.target.value }))}
                    placeholder="Organic herbs, Fast-acting drops"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="guarantee_text" className="md:col-span-2">
                  <FieldLabel>Guarantee text</FieldLabel>
                  <FieldDescription>Optional guarantee statement.</FieldDescription>
                  <Input
                    value={productDraft.guarantee_text}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, guarantee_text: e.target.value }))}
                    placeholder="30-day money back guarantee"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="disclaimers" className="md:col-span-2">
                  <FieldLabel>Disclaimers</FieldLabel>
                  <FieldDescription>Optional comma-separated list.</FieldDescription>
                  <Input
                    value={productDraft.disclaimers}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, disclaimers: e.target.value }))}
                    placeholder="Not medical advice, Results may vary"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="competitor_urls" className="md:col-span-2">
                  <FieldLabel>Competitor URLs</FieldLabel>
                  <FieldDescription>Optional. One URL per line. We’ll use these as seed competitors.</FieldDescription>
                  <FieldControl
                    value={productDraft.competitor_urls}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, competitor_urls: e.target.value }))}
                    render={(props) => (
                      <Textarea {...props} rows={4} placeholder="https://competitor1.com\nhttps://competitor2.com" />
                    )}
                  />
                  <FieldError />
                </FieldRoot>
              </div>

              <div className="mt-4 flex items-center justify-end gap-2 border-t border-divider pt-4">
                <Button variant="secondary" size="sm" onClick={closeProductEditor} disabled={isSubmitting}>
                  Cancel
                </Button>
                <Button size="sm" onClick={saveProduct} disabled={isSubmitting}>
                  Save product
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}

      {currentStep.key === "funnel" && (
        <FieldRoot name="funnel_notes">
          <FieldLabel>Funnel notes</FieldLabel>
          <FieldDescription>Optional funnel notes or channel preferences.</FieldDescription>
          <FieldControl
            value={state.funnel_notes}
            onChange={(e) => setState((s) => ({ ...s, funnel_notes: e.target.value }))}
            render={(props) => <Textarea {...props} rows={2} />}
          />
        </FieldRoot>
      )}

      {currentStep.key === "review" && (
        <div className="space-y-2 text-sm text-content">
          <div className="font-semibold text-content">Review details</div>
          <div className="rounded-lg border border-border bg-surface-2 p-3 shadow-inner">
            <p>
              <strong>Workspace name:</strong> {state.client_name || "Missing"}
            </p>
            <p>
              <strong>Industry:</strong> {state.client_industry || "Not set"}
            </p>
            <p>
              <strong>Business type:</strong> {state.business_type}
            </p>
            <p>
              <strong>Brand story:</strong> {state.brand_story || "Missing"}
            </p>
            <p>
              <strong>Products:</strong> {state.products.length ? state.products.length : "Missing"}
            </p>
            {state.products[0]?.product_name ? (
              <>
                <p>
                  <strong>Product name:</strong> {state.products[0].product_name}
                </p>
                {state.products[0].product_description ? (
                  <p>
                    <strong>Description:</strong> {state.products[0].product_description}
                  </p>
                ) : null}
                {state.products[0].product_category ? (
                  <p>
                    <strong>Category:</strong> {state.products[0].product_category}
                  </p>
                ) : null}
                {state.products[0].primary_benefits ? (
                  <p>
                    <strong>Primary benefits:</strong> {state.products[0].primary_benefits}
                  </p>
                ) : null}
                {state.products[0].feature_bullets ? (
                  <p>
                    <strong>Feature bullets:</strong> {state.products[0].feature_bullets}
                  </p>
                ) : null}
                {state.products[0].guarantee_text ? (
                  <p>
                    <strong>Guarantee:</strong> {state.products[0].guarantee_text}
                  </p>
                ) : null}
                {state.products[0].disclaimers ? (
                  <p>
                    <strong>Disclaimers:</strong> {state.products[0].disclaimers}
                  </p>
                ) : null}
                {state.products[0].goals ? (
                  <p>
                    <strong>Goals:</strong> {state.products[0].goals}
                  </p>
                ) : null}
                {state.products[0].competitor_urls ? (
                  <p className="whitespace-pre-line">
                    <strong>Competitor URLs:</strong> {state.products[0].competitor_urls}
                  </p>
                ) : null}
              </>
            ) : null}
            {state.funnel_notes ? (
              <p>
                <strong>Funnel notes:</strong> {state.funnel_notes}
              </p>
            ) : null}
          </div>
        </div>
      )}
    </FormRoot>
  );

  const content = (
    <div className={isPage ? "flex h-full flex-col gap-4" : "flex flex-col gap-4"}>
      {!isPage ? (
        <>
          <DialogTitle>Workspace onboarding</DialogTitle>
          <DialogDescription>Create the workspace and capture onboarding details in one flow.</DialogDescription>
          <Progress value={progress} />
        </>
      ) : (
        <div className="space-y-3">
          <div className="text-sm font-semibold text-content">Onboarding flow</div>
          <Progress value={progress} />
          <p className="text-sm text-content-muted">We’ll set up the workspace and start the first workflow automatically.</p>
        </div>
      )}

      {stepHeader}

      {isPage ? (
        <div className="min-h-0 flex-1 overflow-y-auto pr-1">{form}</div>
      ) : (
        <div className="max-h-[60vh] overflow-y-auto pr-1">{form}</div>
      )}

      <div className="flex items-center justify-between border-t border-divider pt-4">
        <Button
          variant="secondary"
          size="sm"
          onClick={goPrev}
          disabled={stepIndex === 0 || isSubmitting || (currentStep.key === "product" && isProductEditorOpen)}
        >
          Back
        </Button>
        {stepIndex < steps.length - 1 ? (
          <Button
            size="sm"
            onClick={goNext}
            disabled={!canNext || isSubmitting || (currentStep.key === "product" && isProductEditorOpen)}
          >
            Next
          </Button>
        ) : (
          <Button size="sm" onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? "Starting…" : "Start onboarding"}
          </Button>
        )}
      </div>

      {!isPage ? (
        <DialogClose
          className={buttonClasses({ variant: "ghost", size: "sm", className: "text-content-muted" })}
          disabled={isSubmitting}
        >
          Cancel
        </DialogClose>
      ) : null}
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
