import { useQuery } from "@tanstack/react-query";
import { useSiteMedusaConfig } from "@/api/sites";
import { isMedusaB2CRuntimeSite } from "@/components/commerce/b2c/runtimeSite";

type MedusaCollectionSummary = {
  handle?: string | null;
};

type MedusaCategorySummary = {
  handle?: string | null;
  parent_category_id?: string | null;
};

type MedusaCollectionsResponse = {
  collections?: MedusaCollectionSummary[];
};

type MedusaCategoriesResponse = {
  product_categories?: MedusaCategorySummary[];
};

export type SitePreviewDefaults = {
  collectionHandle: string | null;
  categoryHandle: string | null;
};

function firstNonEmptyHandle(items: Array<{ handle?: string | null }>): string | null {
  for (const item of items) {
    const handle = typeof item.handle === "string" ? item.handle.trim() : "";
    if (handle) {
      return handle;
    }
  }

  return null;
}

export function resolveSitePreviewDefaults(
  collections: MedusaCollectionSummary[],
  categories: MedusaCategorySummary[],
): SitePreviewDefaults {
  const rootCategories = categories.filter((category) => !category.parent_category_id);

  return {
    collectionHandle: firstNonEmptyHandle(collections),
    categoryHandle: firstNonEmptyHandle(rootCategories) || firstNonEmptyHandle(categories),
  };
}

async function readErrorMessage(response: Response, label: string): Promise<string> {
  try {
    const raw = await response.clone().json();
    const candidate =
      typeof (raw as { message?: unknown })?.message === "string"
        ? (raw as { message: string }).message
        : typeof (raw as { detail?: unknown })?.detail === "string"
          ? (raw as { detail: string }).detail
          : "";
    if (candidate) {
      return candidate;
    }
  } catch {
    // Fall through to text parsing.
  }

  try {
    const text = (await response.text()).trim();
    if (text) {
      return text;
    }
  } catch {
    // Fall through to status text.
  }

  return `${label} request failed with status ${response.status}.`;
}

async function fetchStoreJson<T>(
  baseUrl: string,
  publishableKey: string,
  path: string,
  label: string,
): Promise<T> {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "x-publishable-api-key": publishableKey,
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, label));
  }

  return response.json() as Promise<T>;
}

async function fetchSitePreviewDefaults(baseUrl: string, publishableKey: string): Promise<SitePreviewDefaults> {
  const [collectionsPayload, categoriesPayload] = await Promise.all([
    fetchStoreJson<MedusaCollectionsResponse>(
      baseUrl,
      publishableKey,
      "/store/collections?limit=100",
      "Medusa collections",
    ),
    fetchStoreJson<MedusaCategoriesResponse>(
      baseUrl,
      publishableKey,
      "/store/product-categories?limit=100",
      "Medusa categories",
    ),
  ]);

  return resolveSitePreviewDefaults(
    Array.isArray(collectionsPayload.collections) ? collectionsPayload.collections : [],
    Array.isArray(categoriesPayload.product_categories) ? categoriesPayload.product_categories : [],
  );
}

export function useSitePreviewDefaults(
  siteId: string | null | undefined,
  siteFamily: string | null | undefined,
  commerceProvider: string | null | undefined,
) {
  const { data: medusaConfig } = useSiteMedusaConfig(siteId);
  const runtimeConfig = medusaConfig?.medusaConfig;

  return useQuery({
    queryKey: [
      "sites",
      siteId,
      "preview-defaults",
      runtimeConfig?.baseUrl ?? null,
      runtimeConfig?.publishableKey ?? null,
    ],
    queryFn: () => fetchSitePreviewDefaults(runtimeConfig!.baseUrl!, runtimeConfig!.publishableKey!),
    enabled:
      isMedusaB2CRuntimeSite({ siteFamily, commerceProvider }) &&
      !!siteId &&
      runtimeConfig?.available === true &&
      !!runtimeConfig.baseUrl &&
      !!runtimeConfig.publishableKey,
    staleTime: 60_000,
  });
}
