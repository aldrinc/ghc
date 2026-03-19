import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DialogRoot,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog";
import { Button, buttonClasses } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { FieldControl, FieldDescription, FieldError, FieldLabel, FieldRoot, FormRoot } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { useApiClient, type ApiError } from "@/api/client";
import { useCreateClient, useStartOnboarding } from "@/api/clients";
import {
  COMPLIANCE_RULESET_VERSION,
  type ClientComplianceProfile,
  type ComplianceBusinessModel,
} from "@/api/compliance";
import { toast } from "@/components/ui/toast";
import { useProductContext } from "@/contexts/ProductContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { cn } from "@/lib/utils";
import type { Client } from "@/types/common";

/* ------------------------------------------------------------------ */
/*  Types & constants                                                  */
/* ------------------------------------------------------------------ */

type WizardStep = {
  key: string;
  label: string;
  description?: string;
  requiredFields?: string[];
};

const steps: WizardStep[] = [
  {
    key: "brand",
    label: "Your Brand",
    description: "Tell us about your business",
    requiredFields: ["brand_story", "business_model"],
  },
  {
    key: "product",
    label: "Your Product",
    description: "What are you selling?",
  },
  {
    key: "audience",
    label: "Audience & Channels",
    description: "Who are you reaching and where?",
    requiredFields: ["funnel_position", "target_platforms", "target_regions"],
  },
  {
    key: "creative",
    label: "Creative Direction",
    description: "How should your brand sound?",
    requiredFields: ["brand_voice_notes", "existing_proof_assets"],
  },
  {
    key: "review",
    label: "Review & Launch",
    description: "Check your details and start",
  },
];

const complianceBusinessModelOptions: Array<{ label: string; value: ComplianceBusinessModel }> = [
  { label: "E-commerce", value: "ecommerce" },
  { label: "SaaS subscription", value: "saas_subscription" },
  { label: "Digital product", value: "digital_product" },
  { label: "Online service", value: "online_service" },
  { label: "Lead generation", value: "lead_generation" },
];

type ProductDraft = {
  product_name: string;
  product_description: string;
  price: string;
  product_type: string;
  product_category: string;
  competitor_urls: string;
};

const emptyProductDraft: ProductDraft = {
  product_name: "",
  product_description: "",
  price: "",
  product_type: "",
  product_category: "",
  competitor_urls: "",
};

type WizardState = {
  client_name: string;
  business_type: "new" | "existing";
  brand_story: string;
  product_customizable: boolean;
  business_model: ComplianceBusinessModel | "";
  funnel_position: string;
  target_platforms: string;
  target_regions: string;
  existing_proof_assets: string;
  brand_voice_notes: string;
  compliance_notes: string;
  products: ProductDraft[];
};

const baseState: WizardState = {
  client_name: "",
  business_type: "new",
  brand_story: "",
  product_customizable: false,
  business_model: "",
  funnel_position: "",
  target_platforms: "",
  target_regions: "",
  existing_proof_assets: "",
  brand_voice_notes: "",
  compliance_notes: "",
  products: [],
};

const initialState = (clientName?: string): WizardState => ({
  ...baseState,
  client_name: clientName || "",
});

const productTypeOptions = [
  { label: "Select product type", value: "" },
  { label: "Book", value: "book" },
  { label: "Digital", value: "digital" },
  { label: "Supplement", value: "supplement" },
  { label: "Software", value: "software" },
  { label: "Service", value: "service" },
  { label: "Course", value: "course" },
  { label: "Physical Product", value: "physical_product" },
  { label: "Other", value: "other" },
];

function parseListInput(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

/* ------------------------------------------------------------------ */
/*  Step indicator                                                     */
/* ------------------------------------------------------------------ */

type StepStatus = "completed" | "current" | "upcoming";

function StepDot({ status }: { status: StepStatus }) {
  if (status === "completed") {
    return (
      <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-success text-white">
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden>
          <path d="M2 5.5L4 7.5L8 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === "current") {
    return (
      <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent">
        <span className="h-1.5 w-1.5 rounded-full bg-surface" />
      </span>
    );
  }
  return (
    <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border bg-transparent" />
  );
}

function OnboardingStepIndicator({
  currentIndex,
  onStepClick,
  disabled,
}: {
  currentIndex: number;
  onStepClick: (index: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-y-2">
      {steps.map((step, idx) => {
        const status: StepStatus =
          idx < currentIndex ? "completed" : idx === currentIndex ? "current" : "upcoming";
        const canClick = idx < currentIndex && !disabled;

        return (
          <div key={step.key} className="flex items-center">
            {idx > 0 ? (
              <div
                className={cn(
                  "h-0.5 w-4",
                  idx <= currentIndex ? "bg-success" : "bg-border",
                )}
              />
            ) : null}
            <button
              type="button"
              onClick={() => canClick && onStepClick(idx)}
              disabled={!canClick}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition",
                canClick && "hover:ring-2 hover:ring-accent/20 cursor-pointer",
                status === "completed" && "text-content",
                status === "current" && "text-accent",
                status === "upcoming" && "text-content-muted opacity-50",
                !canClick && status !== "current" && status !== "upcoming" && "cursor-default",
              )}
            >
              <StepDot status={status} />
              <span className="hidden sm:inline">{step.label}</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Review section card                                                */
/* ------------------------------------------------------------------ */

function ReviewSection({
  title,
  onEdit,
  items,
}: {
  title: string;
  onEdit: () => void;
  items: Array<{ label: string; value: string; multiline?: boolean }>;
}) {
  const visibleItems = items.filter((item) => item.value && item.value !== "Not set");

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-content">{title}</div>
        <Button variant="ghost" size="xs" onClick={onEdit}>
          Edit
        </Button>
      </div>
      {visibleItems.length > 0 ? (
        <div className="mt-3 space-y-2">
          {visibleItems.map((item) => (
            <div key={item.label}>
              <div className="text-xs font-medium text-content-muted">{item.label}</div>
              <div className={cn("text-sm text-content", item.multiline && "whitespace-pre-line")}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-xs text-content-muted">No details added yet.</div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main wizard                                                        */
/* ------------------------------------------------------------------ */

type OnboardingWizardProps = {
  clientId?: string;
  clientName?: string;
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
  triggerLabel = "Start onboarding",
  onCompleted,
  variant = "modal",
}: OnboardingWizardProps) {
  const navigate = useNavigate();
  const { selectWorkspace } = useWorkspace();
  const { selectProduct } = useProductContext();
  const isPage = variant === "page";
  const [open, setOpen] = useState(isPage);
  const [stepIndex, setStepIndex] = useState(0);
  const [state, setState] = useState<WizardState>(() => initialState(clientName));
  const [activeClientId, setActiveClientId] = useState<string | null>(clientId ?? null);
  const [isProductEditorOpen, setIsProductEditorOpen] = useState(false);
  const [editingProductIndex, setEditingProductIndex] = useState<number | null>(null);
  const [productDraft, setProductDraft] = useState<ProductDraft>(emptyProductDraft);
  const [isSavingComplianceProfile, setIsSavingComplianceProfile] = useState(false);
  const { request } = useApiClient();
  const onboarding = useStartOnboarding();
  const createClient = useCreateClient();

  useEffect(() => {
    if (!open && !isPage) {
      setState(initialState(clientName));
      setStepIndex(0);
      setActiveClientId(clientId ?? null);
      setIsProductEditorOpen(false);
      setEditingProductIndex(null);
      setProductDraft(emptyProductDraft);
    }
  }, [open, clientId, clientName, isPage]);

  const currentStep = steps[stepIndex];
  const requiresClientName = !activeClientId;
  const isSubmitting =
    isSavingComplianceProfile ||
    onboarding.isPending ||
    createClient.isPending;

  /* ------ Validation per step ------ */

  const canNext = useMemo(() => {
    if (currentStep.key === "brand") {
      const hasName = !requiresClientName || Boolean(state.client_name.trim());
      const hasBrandStory = Boolean(state.brand_story.trim());
      const hasBusinessModel = Boolean(state.business_model.trim());
      return hasName && hasBrandStory && hasBusinessModel;
    }
    if (currentStep.key === "product") {
      if (state.products.length !== 1) return false;
      return (
        Boolean(state.products[0]?.product_name?.trim()) &&
        Boolean(state.products[0]?.product_description?.trim()) &&
        Boolean(state.products[0]?.price?.trim()) &&
        Boolean(state.products[0]?.product_type?.trim())
      );
    }
    if (currentStep.key === "audience") {
      if (!state.funnel_position.trim()) return false;
      if (!parseListInput(state.target_platforms).length) return false;
      if (!parseListInput(state.target_regions).length) return false;
      return true;
    }
    if (currentStep.key === "creative") {
      if (!state.brand_voice_notes.trim()) return false;
      if (!parseListInput(state.existing_proof_assets).length) return false;
      return true;
    }
    return true;
  }, [currentStep, requiresClientName, state]);

  /* ------ Navigation ------ */

  const goNext = () => {
    if (stepIndex < steps.length - 1) setStepIndex((i) => i + 1);
  };
  const goPrev = () => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  };

  const navigationBlocked = isSubmitting || (currentStep.key === "product" && isProductEditorOpen);

  const resetWizard = () => {
    setState(initialState(clientName));
    setStepIndex(0);
    setActiveClientId(clientId ?? null);
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
    setProductDraft(emptyProductDraft);
  };

  const completeOnboarding = ({
    clientId: completedClientId,
    clientName: completedClientName,
    productId,
    productName,
  }: {
    clientId: string;
    clientName?: string;
    productId: string;
    productName?: string;
  }) => {
    if (onCompleted) {
      onCompleted({
        clientId: completedClientId,
        clientName: completedClientName,
        productId,
        productName,
      });
      return;
    }
    selectWorkspace(completedClientId, { name: completedClientName });
    selectProduct(
      productId,
      {
        title: productName,
        client_id: completedClientId,
      },
      { clientId: completedClientId }
    );
    navigate("/workspaces/overview");
  };

  useEffect(() => {
    setIsProductEditorOpen(false);
    setEditingProductIndex(null);
  }, [stepIndex]);

  /* ------ Client creation ------ */

  const ensureClient = async (): Promise<string> => {
    if (activeClientId) return activeClientId;
    const created = (await createClient.mutateAsync({
      name: state.client_name.trim(),
      strategyV2Enabled: true,
    })) as Client;
    if (!created?.id) {
      throw new Error("Client creation failed");
    }
    setActiveClientId(created.id);
    return created.id;
  };

  /* ------ Submit ------ */

  const handleSubmit = async () => {
    const firstProduct = state.products[0];
    if (!state.brand_story.trim()) {
      toast.error("Please add your brand story before submitting.");
      return;
    }
    if (state.products.length !== 1 || !firstProduct?.product_name?.trim()) {
      toast.error("Please add a product with a name before submitting.");
      return;
    }
    if (!firstProduct?.product_description?.trim()) {
      toast.error("Please add a product description.");
      return;
    }
    if (!firstProduct?.price?.trim()) {
      toast.error("Please set a product price.");
      return;
    }
    if (!firstProduct?.product_type?.trim()) {
      toast.error("Please select a product type.");
      return;
    }
    if (requiresClientName && !state.client_name.trim()) {
      toast.error("Please enter a business name.");
      return;
    }
    const targetPlatforms = parseListInput(state.target_platforms);
    const targetRegions = parseListInput(state.target_regions);
    const existingProofAssets = parseListInput(state.existing_proof_assets);
    if (!state.business_model.trim()) {
      toast.error("Please select how you sell (business model).");
      return;
    }
    if (!state.funnel_position.trim()) {
      toast.error("Please describe who you're targeting.");
      return;
    }
    if (!targetPlatforms.length) {
      toast.error("Please add at least one advertising platform.");
      return;
    }
    if (!targetRegions.length) {
      toast.error("Please add at least one target region.");
      return;
    }
    if (!existingProofAssets.length) {
      toast.error("Please add at least one piece of social proof.");
      return;
    }
    if (!state.brand_voice_notes.trim()) {
      toast.error("Please describe your brand voice.");
      return;
    }
    const payload = {
      business_type: state.business_type,
      brand_story: state.brand_story.trim(),
      product_name: firstProduct.product_name.trim(),
      price: firstProduct.price.trim(),
      product_customizable: state.product_customizable,
      business_model: state.business_model.trim(),
      funnel_position: state.funnel_position.trim(),
      target_platforms: targetPlatforms,
      target_regions: targetRegions,
      existing_proof_assets: existingProofAssets,
      brand_voice_notes: state.brand_voice_notes.trim(),
      compliance_notes: state.compliance_notes.trim() || undefined,
      product_description: firstProduct.product_description.trim(),
      product_type: firstProduct.product_type.trim(),
      product_category: firstProduct.product_category.trim() || undefined,
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
      setIsSavingComplianceProfile(true);
      try {
        const legalBusinessName = state.client_name.trim() || clientName?.trim() || undefined;
        await request<ClientComplianceProfile>(`/clients/${ensuredClientId}/compliance/profile`, {
          method: "PUT",
          body: JSON.stringify({
            rulesetVersion: COMPLIANCE_RULESET_VERSION,
            businessModels: [state.business_model],
            legalBusinessName,
            metadata: {
              source: "onboarding_wizard",
              complianceNotes: state.compliance_notes.trim() || undefined,
            },
          }),
        });
      } catch (error) {
        const apiError = error as ApiError;
        const message = apiError?.message?.trim()
          ? apiError.message
          : "Failed to create required compliance profile before onboarding.";
        toast.error(message);
        return;
      } finally {
        setIsSavingComplianceProfile(false);
      }
      const response = await onboarding.mutateAsync({ clientId: ensuredClientId, payload });
      const productId = (response as any)?.product_id;
      if (!productId) {
        toast.error("Onboarding started but no product ID was returned.");
        return;
      }
      const completionPayload = {
        clientId: ensuredClientId,
        clientName: state.client_name.trim() || clientName,
        productId,
        productName: (response as any)?.product_name || firstProduct.product_name.trim(),
      };
      resetWizard();
      setOpen(false);
      completeOnboarding(completionPayload);
    } catch (err) {
      // errors are surfaced via mutation onError handlers
    }
  };

  /* ------ Product editor ------ */

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
    if (!productDraft.product_description.trim()) {
      toast.error("Product description is required.");
      return;
    }
    if (!productDraft.price.trim()) {
      toast.error("Product price is required.");
      return;
    }
    if (!productDraft.product_type.trim()) {
      toast.error("Product type is required.");
      return;
    }
    if (editingProductIndex === null && state.products.length >= 1) {
      toast.error("Only one product is supported right now.");
      return;
    }
    const nextDraft: ProductDraft = {
      ...productDraft,
      product_name: productDraft.product_name.trim(),
      product_description: productDraft.product_description.trim(),
      price: productDraft.price.trim(),
      product_type: productDraft.product_type.trim(),
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

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  const stepIndicator = (
    <OnboardingStepIndicator
      currentIndex={stepIndex}
      onStepClick={(idx) => setStepIndex(idx)}
      disabled={navigationBlocked}
    />
  );

  const stepDescription = currentStep.description ? (
    <div className="rounded-lg border border-border px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-content">{currentStep.label}</div>
          <div className="mt-1 text-xs text-content-muted">{currentStep.description}</div>
        </div>
      </div>
    </div>
  ) : null;

  /* ------ Form sections ------ */

  const form = (
    <FormRoot className="space-y-4" onSubmit={(e) => e.preventDefault()}>
      {/* ---- Step 1: Your Brand ---- */}
      {currentStep.key === "brand" && (
        <>
          <div className="rounded-lg border border-border bg-surface-2 p-4 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">Identity</div>
            <FieldRoot name="client_name">
              <FieldLabel>Business name</FieldLabel>
              <FieldDescription>This becomes your workspace name and is used as your legal business name for compliance.</FieldDescription>
              <Input
                value={state.client_name}
                onChange={(e) => setState((s) => ({ ...s, client_name: e.target.value }))}
                required
                placeholder="Acme Corp"
                disabled={Boolean(activeClientId)}
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="business_type">
              <FieldLabel>Business stage</FieldLabel>
              <FieldDescription>Are you launching something new or improving an existing business?</FieldDescription>
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
            <FieldRoot name="business_model">
              <FieldLabel>How do you sell?</FieldLabel>
              <FieldDescription>
                How your business makes money. This drives your compliance setup and shapes offer strategy.{" "}
                <span className="italic text-content-muted/60">(Business model)</span>
              </FieldDescription>
              <Select
                value={state.business_model}
                onValueChange={(value) =>
                  setState((s) => ({ ...s, business_model: value as ComplianceBusinessModel | "" }))
                }
                options={[
                  { label: "Select how you sell...", value: "" },
                  ...complianceBusinessModelOptions,
                ]}
                required
              />
              <FieldError />
            </FieldRoot>
          </div>

          <FieldRoot name="brand_story">
            <FieldLabel>Brand story</FieldLabel>
            <FieldDescription>
              Tell us about your brand in your own words — what you do, who you serve, and what makes you different. This shapes all the research and strategy we generate.
            </FieldDescription>
            <FieldControl
              value={state.brand_story}
              onChange={(e) => setState((s) => ({ ...s, brand_story: e.target.value }))}
              render={(props) => (
                <Textarea
                  {...props}
                  rows={4}
                  required
                  placeholder="We make natural sleep supplements for busy professionals who want to fall asleep faster without pills. Our founder developed the formula after years of insomnia..."
                />
              )}
            />
            <FieldError />
          </FieldRoot>
        </>
      )}

      {/* ---- Step 2: Your Product ---- */}
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
                        Price: {product.price || "Not set"}
                      </div>
                      <div className="mt-1 text-xs text-content-muted">
                        Type: {product.product_type || "Not set"}
                      </div>
                      {product.product_category ? (
                        <div className="mt-1 text-xs text-content-muted">
                          Category: {product.product_category}
                        </div>
                      ) : null}
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
                    These details shape your strategy, offer, and copy outputs.
                  </div>
                </div>
                <Badge tone="neutral" className="shrink-0">
                  Product {editingProductIndex === null ? state.products.length + 1 : editingProductIndex + 1}
                </Badge>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <FieldRoot name="product_name" className="md:col-span-2">
                  <FieldLabel>Product name</FieldLabel>
                  <FieldDescription>The name customers see. This becomes the default name for your offer and strategy.</FieldDescription>
                  <Input
                    value={productDraft.product_name}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_name: e.target.value }))}
                    placeholder="Herbal Sleep Drops"
                    required
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="product_type">
                  <FieldLabel>Product type</FieldLabel>
                  <FieldDescription>What kind of product is this? Affects how we generate images, copy, and store layouts.</FieldDescription>
                  <Select
                    value={productDraft.product_type}
                    onValueChange={(value) => setProductDraft((draft) => ({ ...draft, product_type: value }))}
                    options={productTypeOptions}
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="product_category">
                  <FieldLabel>Niche or category</FieldLabel>
                  <FieldDescription>Optional. A specific label like "sleep supplements" or "productivity SaaS" that focuses our research.</FieldDescription>
                  <Input
                    value={productDraft.product_category}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_category: e.target.value }))}
                    placeholder="Sleep supplements, productivity SaaS"
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="product_description" className="md:col-span-2">
                  <FieldLabel>Product description</FieldLabel>
                  <FieldDescription>A short summary of what this product is and does. Used throughout strategy and copy generation.</FieldDescription>
                  <FieldControl
                    value={productDraft.product_description}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, product_description: e.target.value }))}
                    render={(props) => (
                      <Textarea {...props} rows={3} placeholder="Sleep support tincture with calming herbs. Designed for busy professionals who want to fall asleep faster without pills." />
                    )}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="price">
                  <FieldLabel>Price</FieldLabel>
                  <FieldDescription>The price customers pay. Sets the starting point for your offer and pricing strategy.</FieldDescription>
                  <Input
                    value={productDraft.price}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, price: e.target.value }))}
                    placeholder="$49"
                    required
                    disabled={isSubmitting}
                  />
                  <FieldError />
                </FieldRoot>

                <FieldRoot name="competitor_urls" className="md:col-span-2">
                  <FieldLabel>Competitor websites</FieldLabel>
                  <FieldDescription>Optional. Paste competitor URLs (one per line). We use these as starting points for competitive research.</FieldDescription>
                  <FieldControl
                    value={productDraft.competitor_urls}
                    onChange={(e) => setProductDraft((draft) => ({ ...draft, competitor_urls: e.target.value }))}
                    render={(props) => (
                      <Textarea {...props} rows={3} placeholder={"https://competitor1.com\nhttps://competitor2.com"} />
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

      {/* ---- Step 3: Audience & Channels ---- */}
      {currentStep.key === "audience" && (
        <div className="space-y-4">
          <FieldRoot name="funnel_position">
            <FieldLabel>Who are you targeting?</FieldLabel>
            <FieldDescription>
              Are you reaching people who've never heard of you (cold traffic), or people who already know your brand (warm retargeting)?{" "}
              <span className="italic text-content-muted/60">(Funnel position)</span>
            </FieldDescription>
            <Input
              value={state.funnel_position}
              onChange={(e) => setState((s) => ({ ...s, funnel_position: e.target.value }))}
              placeholder="Cold traffic — reaching people who haven't heard of us yet"
              required
            />
            <FieldError />
          </FieldRoot>

          <div className="grid gap-4 md:grid-cols-2">
            <FieldRoot name="target_platforms">
              <FieldLabel>Where will you advertise?</FieldLabel>
              <FieldDescription>Which advertising platforms will you use? List each one on a new line or separate with commas.</FieldDescription>
              <FieldControl
                value={state.target_platforms}
                onChange={(e) => setState((s) => ({ ...s, target_platforms: e.target.value }))}
                render={(props) => <Textarea {...props} rows={3} placeholder={"Meta Ads\nTikTok Ads\nGoogle Ads"} required />}
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="target_regions">
              <FieldLabel>Where are your customers?</FieldLabel>
              <FieldDescription>Which countries or regions are you targeting? List each one on a new line or separate with commas.</FieldDescription>
              <FieldControl
                value={state.target_regions}
                onChange={(e) => setState((s) => ({ ...s, target_regions: e.target.value }))}
                render={(props) => <Textarea {...props} rows={3} placeholder={"United States\nCanada\nUnited Kingdom"} required />}
              />
              <FieldError />
            </FieldRoot>
          </div>
        </div>
      )}

      {/* ---- Step 4: Creative Direction ---- */}
      {currentStep.key === "creative" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-surface-2 p-4 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">Voice & proof</div>
            <FieldRoot name="brand_voice_notes">
              <FieldLabel>Brand voice</FieldLabel>
              <FieldDescription>How should your brand sound? Describe the tone and style for all headlines and copy we generate.</FieldDescription>
              <FieldControl
                value={state.brand_voice_notes}
                onChange={(e) => setState((s) => ({ ...s, brand_voice_notes: e.target.value }))}
                render={(props) => (
                  <Textarea
                    {...props}
                    rows={3}
                    placeholder="Conversational and friendly, like a knowledgeable friend giving advice. Direct response style but never pushy. Confident claims, always backed by evidence."
                    required
                  />
                )}
              />
              <FieldError />
            </FieldRoot>
            <FieldRoot name="existing_proof_assets">
              <FieldLabel>Social proof you already have</FieldLabel>
              <FieldDescription>
                Testimonials, case studies, before/after results, media mentions. We never invent proof — we build your offer around what you actually have.
              </FieldDescription>
              <FieldControl
                value={state.existing_proof_assets}
                onChange={(e) => setState((s) => ({ ...s, existing_proof_assets: e.target.value }))}
                render={(props) => (
                  <Textarea
                    {...props}
                    rows={3}
                    placeholder={"1,200+ five-star reviews on Amazon\nBefore/after customer photos\nFeatured in Men's Health magazine"}
                    required
                  />
                )}
              />
              <FieldError />
            </FieldRoot>
          </div>

          <div className="rounded-lg border border-border bg-surface-2 p-4 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">Constraints</div>
            <label className="flex items-start gap-3 text-sm text-content">
              <input
                type="checkbox"
                checked={state.product_customizable}
                onChange={() => setState((s) => ({ ...s, product_customizable: !s.product_customizable }))}
                className="mt-0.5"
              />
              <div>
                <div className="font-medium">Can we suggest changes to your product?</div>
                <div className="text-xs text-content-muted">
                  If yes, our strategy may recommend product modifications. If no, we only change how it's framed and offered.
                </div>
              </div>
            </label>
            <FieldRoot name="compliance_notes">
              <FieldLabel>Legal or compliance constraints</FieldLabel>
              <FieldDescription>Optional. Any specific legal restrictions we should follow when generating copy and claims.</FieldDescription>
              <FieldControl
                value={state.compliance_notes}
                onChange={(e) => setState((s) => ({ ...s, compliance_notes: e.target.value }))}
                render={(props) => (
                  <Textarea
                    {...props}
                    rows={2}
                    placeholder="No medical diagnosis claims. Must include FDA disclaimer for supplements. Avoid absolute guarantees."
                  />
                )}
              />
              <FieldError />
            </FieldRoot>
          </div>
        </div>
      )}

      {/* ---- Step 5: Review & Launch ---- */}
      {currentStep.key === "review" && (
        <div className="space-y-4">
          <ReviewSection
            title="Your Brand"
            onEdit={() => setStepIndex(0)}
            items={[
              { label: "Business name", value: state.client_name || clientName || "Not set" },
              { label: "Business stage", value: state.business_type === "new" ? "New business" : "Existing business" },
              {
                label: "How you sell",
                value: complianceBusinessModelOptions.find((o) => o.value === state.business_model)?.label || "Not set",
              },
              { label: "Brand story", value: state.brand_story || "Not set", multiline: true },
            ]}
          />

          <ReviewSection
            title="Your Product"
            onEdit={() => setStepIndex(1)}
            items={[
              { label: "Product name", value: state.products[0]?.product_name || "Not set" },
              { label: "Type", value: state.products[0]?.product_type || "Not set" },
              { label: "Price", value: state.products[0]?.price || "Not set" },
              { label: "Description", value: state.products[0]?.product_description || "Not set", multiline: true },
              ...(state.products[0]?.product_category
                ? [{ label: "Category", value: state.products[0].product_category }]
                : []),
              ...(state.products[0]?.competitor_urls
                ? [{ label: "Competitor websites", value: state.products[0].competitor_urls, multiline: true }]
                : []),
            ]}
          />

          <ReviewSection
            title="Audience & Channels"
            onEdit={() => setStepIndex(2)}
            items={[
              { label: "Targeting", value: state.funnel_position || "Not set" },
              { label: "Platforms", value: parseListInput(state.target_platforms).join(", ") || "Not set" },
              { label: "Regions", value: parseListInput(state.target_regions).join(", ") || "Not set" },
            ]}
          />

          <ReviewSection
            title="Creative Direction"
            onEdit={() => setStepIndex(3)}
            items={[
              { label: "Brand voice", value: state.brand_voice_notes || "Not set", multiline: true },
              { label: "Social proof", value: parseListInput(state.existing_proof_assets).join(", ") || "Not set" },
              { label: "Product changeable", value: state.product_customizable ? "Yes" : "No" },
              ...(state.compliance_notes
                ? [{ label: "Compliance constraints", value: state.compliance_notes, multiline: true }]
                : []),
            ]}
          />
        </div>
      )}
    </FormRoot>
  );

  /* ------ Layout ------ */

  const content = (
    <div className={isPage ? "flex h-full flex-col gap-4" : "flex flex-col gap-4"}>
      {!isPage ? (
        <>
          <DialogTitle>Set up your workspace</DialogTitle>
          <DialogDescription>We'll collect a few details and then handle research and strategy generation for you.</DialogDescription>
          {stepIndicator}
        </>
      ) : (
        <div className="space-y-3">
          <div className="text-sm font-semibold text-content">Onboarding flow</div>
          {stepIndicator}
          <p className="text-sm text-content-muted">We'll set up your workspace and start the first workflow automatically.</p>
        </div>
      )}

      {stepDescription}

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
          disabled={stepIndex === 0 || navigationBlocked}
        >
          Back
        </Button>
        {stepIndex < steps.length - 1 ? (
          <Button
            size="sm"
            onClick={goNext}
            disabled={!canNext || navigationBlocked}
          >
            Next
          </Button>
        ) : (
          <Button size="sm" onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? "Starting..." : "Launch onboarding"}
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
