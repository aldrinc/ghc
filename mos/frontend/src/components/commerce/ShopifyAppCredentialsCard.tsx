import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type ShopifyAppCredentialsCardProps = {
  workspaceId: string;
  shopifyAppApiKeyDraft: string;
  setShopifyAppApiKeyDraft: (value: string) => void;
  shopifyAppApiSecretDraft: string;
  setShopifyAppApiSecretDraft: (value: string) => void;
  hasConfiguredShopifyAppCredentials: boolean;
  isLoadingShopifyAppCredentials: boolean;
  shopifyAppCredentialsUpdatedAtLabel: string;
  isShopifyAppCredentialsMutating: boolean;
  hasShopifyConnectionTarget: boolean;
  onSave: () => void;
};

export function ShopifyAppCredentialsCard({
  workspaceId,
  shopifyAppApiKeyDraft,
  setShopifyAppApiKeyDraft,
  shopifyAppApiSecretDraft,
  setShopifyAppApiSecretDraft,
  hasConfiguredShopifyAppCredentials,
  isLoadingShopifyAppCredentials,
  shopifyAppCredentialsUpdatedAtLabel,
  isShopifyAppCredentialsMutating,
  hasShopifyConnectionTarget,
  onSave,
}: ShopifyAppCredentialsCardProps) {
  return (
    <div className="ds-card ds-card--md space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-content">App credentials</div>
          <div className="text-xs text-content-muted">
            Save one Shopify app API key + secret pair per workspace before connecting a store.
          </div>
        </div>
        <Badge tone={hasConfiguredShopifyAppCredentials ? "success" : "neutral"}>
          {isLoadingShopifyAppCredentials
            ? "Loading…"
            : hasConfiguredShopifyAppCredentials
              ? "Configured"
              : "Missing"}
        </Badge>
      </div>

      {shopifyAppCredentialsUpdatedAtLabel ? (
        <div className="text-xs text-content-muted">Updated: {shopifyAppCredentialsUpdatedAtLabel}</div>
      ) : null}

      <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <Input
          placeholder="Shopify app API key"
          value={shopifyAppApiKeyDraft}
          onChange={(event) => setShopifyAppApiKeyDraft(event.target.value)}
          disabled={isShopifyAppCredentialsMutating}
        />
        <Input
          type="password"
          placeholder="Shopify app API secret"
          value={shopifyAppApiSecretDraft}
          onChange={(event) => setShopifyAppApiSecretDraft(event.target.value)}
          disabled={isShopifyAppCredentialsMutating}
        />
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void onSave()}
          disabled={
            !workspaceId ||
            !shopifyAppApiKeyDraft.trim() ||
            !shopifyAppApiSecretDraft.trim() ||
            isShopifyAppCredentialsMutating
          }
        >
          {isShopifyAppCredentialsMutating ? "Saving…" : "Save credentials"}
        </Button>
      </div>

      <div className="text-xs text-content-muted">
        {hasShopifyConnectionTarget
          ? "To switch to a different Shopify app, disconnect the current store first, then reconnect."
          : "The store connection card below will unlock after credentials are saved."}
      </div>
    </div>
  );
}
