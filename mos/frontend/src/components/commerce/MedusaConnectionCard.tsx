import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CreditCard, ExternalLink, Loader2, Plus, Save } from "lucide-react";

import {
  useCreateMedusaVariant,
  useCreateStripeProfile,
  useMedusaConfig,
  useStripeProfiles,
  useTestMedusaConnection,
  useUpdateMedusaConfig,
  useUpdateStripeProfile,
} from "@/api/products";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

function readQueryError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string" && error.message) {
    return error.message;
  }
  return fallback;
}

function buildMedusaAdminUrl(baseUrl: string | null | undefined): string | null {
  if (!baseUrl) return null;
  return `${baseUrl.replace(/\/+$/, "")}/app`;
}

function MedusaStatusBadge({ status }: { status: string }) {
  if (status === "connected") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
        <CheckCircle2 className="h-3 w-3" />
        Connected
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
        <AlertTriangle className="h-3 w-3" />
        Error
      </span>
    );
  }
  if (status === "not_tested") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
        Not tested
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-neutral/10 px-2 py-0.5 text-xs font-medium text-content-muted">
      Not configured
    </span>
  );
}

export interface MedusaConnectionCardProps {
  clientId: string;
  productId?: string;
  onVariantCreated?: (variantId: string) => void;
}

export function MedusaConnectionCard({ clientId, productId, onVariantCreated }: MedusaConnectionCardProps) {
  const queryClient = useQueryClient();
  const [showConfigForm, setShowConfigForm] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [adminApiKey, setAdminApiKey] = useState("");
  const [publishableKey, setPublishableKey] = useState("");
  const [stripeAccountProfileId, setStripeAccountProfileId] = useState<string>("");
  const [defaultPaymentProviderId, setDefaultPaymentProviderId] = useState<string>("");
  const [allowedPaymentProviderIds, setAllowedPaymentProviderIds] = useState<string>("");
  const [webhookRoutingMode, setWebhookRoutingMode] = useState<"direct" | "shared_ingress">("shared_ingress");
  const [showCreateVariant, setShowCreateVariant] = useState(false);
  const [variantTitle, setVariantTitle] = useState("");
  const [variantPrice, setVariantPrice] = useState("");
  const [variantCurrency, setVariantCurrency] = useState("usd");
  const [variantInventoryQuantity, setVariantInventoryQuantity] = useState("");
  const [variantOptionValues, setVariantOptionValues] = useState("");
  const [variantFormError, setVariantFormError] = useState<string | null>(null);
  const [showStripeProfileForm, setShowStripeProfileForm] = useState(false);
  const [editingStripeProfile, setEditingStripeProfile] = useState<string | null>(null);
  const [stripeProfileLabel, setStripeProfileLabel] = useState("");
  const [stripeAccountId, setStripeAccountId] = useState("");
  const [stripeSecretKeyRef, setStripeSecretKeyRef] = useState("");
  const [stripeWebhookSecretRef, setStripeWebhookSecretRef] = useState("");
  const [stripeMode, setStripeMode] = useState<"shared" | "dedicated">("shared");

  const { data: config, isLoading: configLoading, refetch: refetchConfig } = useMedusaConfig(clientId);
  const {
    data: stripeProfiles = [],
    isLoading: profilesLoading,
    error: stripeProfilesError,
  } = useStripeProfiles();
  const updateConfig = useUpdateMedusaConfig(clientId);
  const testConnection = useTestMedusaConnection(clientId);
  const createVariant = useCreateMedusaVariant(productId || "");
  const createStripeProfile = useCreateStripeProfile();
  const updateStripeProfile = useUpdateStripeProfile(editingStripeProfile || "");

  const handleSaveConfig = async () => {
    if (!baseUrl.trim()) return;
    await updateConfig.mutateAsync({
      baseUrl: baseUrl.trim(),
      adminApiKey: adminApiKey.trim() || undefined,
      publishableKey: publishableKey.trim() || undefined,
      stripeAccountProfileId: stripeAccountProfileId || null,
      defaultPaymentProviderId: defaultPaymentProviderId || null,
      allowedPaymentProviderIds: allowedPaymentProviderIds
        .split(",")
        .map((id) => id.trim())
        .filter((id) => id.length > 0),
      webhookRoutingMode,
    });
    setBaseUrl("");
    setAdminApiKey("");
    setPublishableKey("");
    setShowConfigForm(false);
  };

  const handleTestConnection = async () => {
    await testConnection.mutateAsync();
    refetchConfig();
  };

  const handleCreateVariant = async () => {
    if (!productId || !variantTitle.trim() || !variantPrice || !variantCurrency) return;
    const price = Math.round(parseFloat(variantPrice) * 100);
    if (Number.isNaN(price) || price < 0) return;

    const result = await createVariant.mutateAsync({
      optionValues: variantOptionValues.trim() ? (JSON.parse(variantOptionValues) as Record<string, string>) : undefined,
      title: variantTitle.trim(),
      price,
      currency: variantCurrency.toUpperCase(),
      inventoryQuantity: variantInventoryQuantity ? parseInt(variantInventoryQuantity, 10) : undefined,
    });
    setVariantTitle("");
    setVariantPrice("");
    setVariantInventoryQuantity("");
    setVariantOptionValues("");
    setVariantFormError(null);
    setShowCreateVariant(false);
    onVariantCreated?.(result.variantId);
    queryClient.invalidateQueries({ queryKey: ["products", "detail", productId] });
  };

  const handleCreateVariantSafe = async () => {
    try {
      setVariantFormError(null);
      if (variantOptionValues.trim()) {
        const parsed = JSON.parse(variantOptionValues);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setVariantFormError('Option values must be a JSON object, for example {"Size":"Large"}.');
          return;
        }
      }
      await handleCreateVariant();
    } catch (error) {
      if (error instanceof SyntaxError) {
        setVariantFormError("Option values must be valid JSON.");
        return;
      }
      throw error;
    }
  };

  const handleSaveStripeProfile = async () => {
    if (!stripeProfileLabel.trim()) return;

    const payload = {
      label: stripeProfileLabel.trim(),
      stripeAccountId: stripeAccountId.trim() || undefined,
      secretKeyRef: stripeSecretKeyRef.trim() || undefined,
      webhookSecretRef: stripeWebhookSecretRef.trim() || undefined,
      mode: stripeMode,
    };

    if (editingStripeProfile) {
      await updateStripeProfile.mutateAsync(payload);
    } else {
      await createStripeProfile.mutateAsync(payload);
    }

    setStripeProfileLabel("");
    setStripeAccountId("");
    setStripeSecretKeyRef("");
    setStripeWebhookSecretRef("");
    setStripeMode("shared");
    setEditingStripeProfile(null);
    setShowStripeProfileForm(false);
  };

  const handleEditStripeProfile = (profile: {
    id: string;
    label: string;
    stripeAccountId: string | null;
    mode: "shared" | "dedicated";
  }) => {
    setEditingStripeProfile(profile.id);
    setStripeProfileLabel(profile.label);
    setStripeAccountId(profile.stripeAccountId || "");
    setStripeSecretKeyRef("");
    setStripeWebhookSecretRef("");
    setStripeMode(profile.mode);
    setShowStripeProfileForm(true);
  };

  const handleOpenConfigForm = () => {
    setBaseUrl(config?.baseUrl || "");
    setAdminApiKey("");
    setPublishableKey("");
    setStripeAccountProfileId(config?.stripeAccountProfileId || "");
    setDefaultPaymentProviderId(config?.defaultPaymentProviderId || "");
    setAllowedPaymentProviderIds((config?.allowedPaymentProviderIds || []).join(", "));
    setWebhookRoutingMode(config?.webhookRoutingMode || "shared_ingress");
    setShowConfigForm(true);
  };

  const isConnected = config?.connectionStatus === "connected";
  const adminUrl = buildMedusaAdminUrl(config?.baseUrl);

  if (configLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
        <div className="flex items-center gap-2 text-sm text-content-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading Medusa configuration...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Medusa Connection</div>
            <div className="mt-1 text-xs text-content-muted">
              {config?.baseUrl ? (
                <span className="flex items-center gap-1">
                  {config.baseUrl}
                  <a href={config.baseUrl} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </span>
              ) : (
                "Not configured"
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <MedusaStatusBadge status={config?.connectionStatus || "not_configured"} />
            {adminUrl ? (
              <Button asChild size="sm" variant="outline">
                <a href={adminUrl} target="_blank" rel="noopener noreferrer">
                  Open Admin
                  <ExternalLink className="h-3 w-3" />
                </a>
              </Button>
            ) : null}
            {config?.baseUrl ? (
              <Button size="sm" variant="outline" onClick={handleTestConnection} disabled={testConnection.isPending}>
                {testConnection.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Test"}
              </Button>
            ) : null}
          </div>
        </div>

        {config?.lastConnectionError ? (
          <div className="mt-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            {config.lastConnectionError}
          </div>
        ) : null}

        {!showConfigForm ? (
          <Button size="sm" variant="outline" className="mt-3" onClick={handleOpenConfigForm}>
            {config?.baseUrl ? "Edit Configuration" : "Configure Medusa"}
          </Button>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Base URL</label>
              <Input placeholder="https://my-store.medusa.example.com" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Admin API Key</label>
              <Input
                type="password"
                placeholder="Leave blank to keep existing"
                value={adminApiKey}
                onChange={(e) => setAdminApiKey(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Medusa Store Publishable API Key</label>
              <Input
                type="password"
                placeholder="Leave blank to keep existing"
                value={publishableKey}
                onChange={(e) => setPublishableKey(e.target.value)}
              />
              {config?.hasPublishableKey && !publishableKey ? (
                <div className="text-[11px] text-content-muted">A publishable key is already configured.</div>
              ) : null}
              {!publishableKey ? (
                <div className="text-[11px] text-content-muted">
                  This is the Medusa Store API key used by the storefront runtime. It is not a Stripe <code>pk_...</code> key.
                </div>
              ) : null}
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Stripe Account Profile</label>
              <Select
                value={stripeAccountProfileId}
                onValueChange={setStripeAccountProfileId}
                options={[
                  { label: "None", value: "" },
                  ...stripeProfiles.map((profile) => ({
                    label: `${profile.label} (${profile.mode})`,
                    value: profile.id,
                  })),
                ]}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Default Payment Provider ID</label>
              <Input
                placeholder="e.g., pp_stripe_stripe"
                value={defaultPaymentProviderId}
                onChange={(e) => setDefaultPaymentProviderId(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Allowed Payment Provider IDs (comma-separated)</label>
              <Input
                placeholder="e.g., pp_stripe_stripe, pp_manual_manual"
                value={allowedPaymentProviderIds}
                onChange={(e) => setAllowedPaymentProviderIds(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Webhook Routing Mode</label>
              <Select
                value={webhookRoutingMode}
                onValueChange={(value) => setWebhookRoutingMode(value as "direct" | "shared_ingress")}
                options={[
                  { label: "Shared ingress", value: "shared_ingress" },
                  { label: "Direct", value: "direct" },
                ]}
              />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveConfig} disabled={updateConfig.isPending || !baseUrl.trim()}>
                {updateConfig.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="mr-1 h-3 w-3" />}
                Save
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowConfigForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-content">Stripe Account Profiles</div>
            <div className="mt-1 text-xs text-content-muted">
              Manage Stripe account profiles for payment processing. For local dev, paste Stripe test keys directly.
            </div>
          </div>
          <CreditCard className="h-4 w-4 text-content-muted" />
        </div>

        {!showStripeProfileForm ? (
          <>
            <div className="mt-3 space-y-2">
              {profilesLoading ? (
                <div className="flex items-center gap-2 text-sm text-content-muted">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Loading profiles...
                </div>
              ) : stripeProfilesError ? (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
                  {readQueryError(stripeProfilesError, "Failed to load Stripe profiles.")}
                </div>
              ) : stripeProfiles.length === 0 ? (
                <div className="text-sm text-content-muted">No Stripe profiles configured.</div>
              ) : (
                stripeProfiles.map((profile) => (
                  <div
                    key={profile.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2"
                  >
                    <div>
                      <div className="text-sm font-medium text-content">{profile.label}</div>
                      <div className="text-xs text-content-muted">
                        {profile.stripeAccountId || "No connected account id"} • {profile.mode}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={profile.status === "active" ? "success" : "neutral"}>{profile.status}</Badge>
                      <Button size="sm" variant="outline" onClick={() => handleEditStripeProfile(profile)}>
                        Edit
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              className="mt-3"
              onClick={() => {
                setEditingStripeProfile(null);
                setStripeProfileLabel("");
                setStripeAccountId("");
                setStripeSecretKeyRef("");
                setStripeWebhookSecretRef("");
                setStripeMode("shared");
                setShowStripeProfileForm(true);
              }}
            >
              <Plus className="mr-1 h-3 w-3" />
              Add Profile
            </Button>
          </>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-content-muted">
              Local dev path: paste your <code>sk_test_...</code> key into Secret Key, leave Stripe Account ID blank
              unless you need a specific <code>acct_...</code>, and only add a webhook secret when testing direct
              webhook delivery.
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Label *</label>
              <Input placeholder="Test Account" value={stripeProfileLabel} onChange={(e) => setStripeProfileLabel(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Stripe Account ID</label>
              <Input
                placeholder="Optional. e.g. acct_xxxxxxxxxxxxxxxx"
                value={stripeAccountId}
                onChange={(e) => setStripeAccountId(e.target.value)}
              />
              <div className="text-[11px] text-content-muted">
                Leave blank for a standard test account. Only set this when you need a specific connected account.
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Secret Key {editingStripeProfile ? "" : "*"}</label>
              <Input
                placeholder={editingStripeProfile ? "Leave blank to keep existing" : "sk_test_... or stored secret reference"}
                value={stripeSecretKeyRef}
                onChange={(e) => setStripeSecretKeyRef(e.target.value)}
              />
              <div className="text-[11px] text-content-muted">
                Paste your Stripe test secret key directly for local dev.
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Webhook Secret</label>
              <Input
                placeholder={editingStripeProfile ? "Leave blank to keep existing" : "Optional. whsec_... or stored secret reference"}
                value={stripeWebhookSecretRef}
                onChange={(e) => setStripeWebhookSecretRef(e.target.value)}
              />
              <div className="text-[11px] text-content-muted">
                Only needed when you are testing Stripe webhook delivery.
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Mode</label>
              <Select
                value={stripeMode}
                onValueChange={(value) => setStripeMode(value as "shared" | "dedicated")}
                options={[
                  { label: "Shared", value: "shared" },
                  { label: "Dedicated", value: "dedicated" },
                ]}
              />
              <div className="text-[11px] text-content-muted">
                Keep this as <span className="font-medium">Shared</span> for a normal local test unless you specifically
                need a dedicated webhook topology.
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleSaveStripeProfile}
                disabled={
                  (editingStripeProfile ? updateStripeProfile.isPending : createStripeProfile.isPending) ||
                  !stripeProfileLabel.trim() ||
                  (!editingStripeProfile && !stripeSecretKeyRef.trim())
                }
              >
                {editingStripeProfile ? (
                  updateStripeProfile.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    "Update"
                  )
                ) : createStripeProfile.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Create"
                )}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setShowStripeProfileForm(false);
                  setEditingStripeProfile(null);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      {isConnected && productId ? (
        <div className="rounded-xl border border-border bg-surface-2 px-4 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-content">Create Medusa Variant</div>
              <div className="mt-1 text-xs text-content-muted">Create a new variant in Medusa for this product.</div>
            </div>
          </div>

          {!showCreateVariant ? (
            <Button size="sm" className="mt-3" onClick={() => setShowCreateVariant(true)}>
              Create Variant
            </Button>
          ) : (
            <div className="mt-3 space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-content">Title *</label>
                <Input placeholder="Variant title" value={variantTitle} onChange={(e) => setVariantTitle(e.target.value)} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Price ($) *</label>
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="19.99"
                    value={variantPrice}
                    onChange={(e) => setVariantPrice(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Currency *</label>
                  <Input placeholder="USD" value={variantCurrency} onChange={(e) => setVariantCurrency(e.target.value)} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Inventory</label>
                  <Input
                    type="number"
                    placeholder="Optional"
                    value={variantInventoryQuantity}
                    onChange={(e) => setVariantInventoryQuantity(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-content">Option values (JSON)</label>
                  <Input
                    placeholder='Optional, e.g. {"Format":"Print"}'
                    value={variantOptionValues}
                    onChange={(e) => setVariantOptionValues(e.target.value)}
                  />
                </div>
              </div>
              <div className="text-xs text-content-muted">
                Compare-at pricing is not supported by this Medusa flow yet. Leave it blank and manage it separately if needed.
              </div>
              {variantFormError ? (
                <div className="rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
                  {variantFormError}
                </div>
              ) : null}
              <div className="flex gap-2">
                <Button size="sm" onClick={handleCreateVariantSafe} disabled={createVariant.isPending || !variantTitle.trim() || !variantPrice}>
                  {createVariant.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Create"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowCreateVariant(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {!isConnected && productId ? (
        <div className="rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="font-medium">Medusa connection required</div>
              <div className="mt-1 text-xs">Configure and test your Medusa connection to create variants and use Store Templates.</div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
