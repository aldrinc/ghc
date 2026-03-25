import { expect, test, type Page } from "@playwright/test";

const PRODUCT_SLUG = "honest-herbalist";
const FUNNEL_SLUG = "storefront";

function svgDataUrl(title: string, color: string) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="900" height="1100" viewBox="0 0 900 1100">
      <rect width="900" height="1100" fill="${color}" rx="48" />
      <rect x="88" y="88" width="724" height="924" rx="36" fill="rgba(255,255,255,0.78)" />
      <text x="450" y="420" text-anchor="middle" fill="#1f2937" font-size="56" font-family="Arial, sans-serif" font-weight="700">Honest Herbalist</text>
      <text x="450" y="520" text-anchor="middle" fill="#374151" font-size="38" font-family="Arial, sans-serif">${title}</text>
    </svg>
  `;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function buildProducts({ withCollectionData = true }: { withCollectionData?: boolean }) {
  return [
    {
      id: "prod-handbook",
      title: "The Honest Herbalist Handbook",
      handle: "the-honest-herbalist-handbook",
      description: "Reference handbook for herbal practitioners.",
      thumbnail: svgDataUrl("Handbook", "#d9f99d"),
      collection_id: withCollectionData ? "col-featured" : null,
      variants: [
        {
          id: "variant-handbook",
          title: "Standard",
          prices: [{ id: "price-handbook", currency_code: "usd", amount: 3900 }],
        },
      ],
      metadata: { format: "Printed handbook" },
    },
    {
      id: "prod-worksheet",
      title: '"What I’m Taking" Doctor-Visit Worksheet Pad',
      handle: "what-im-taking-doctor-visit-worksheet-pad",
      description: "Worksheet pad for supplement and medicine reviews.",
      thumbnail: svgDataUrl("Worksheet Pad", "#bfdbfe"),
      collection_id: withCollectionData ? "col-featured" : null,
      variants: [
        {
          id: "variant-worksheet",
          title: "Pad",
          prices: [{ id: "price-worksheet", currency_code: "usd", amount: 1800 }],
        },
      ],
      metadata: { format: "Physical pad" },
    },
    {
      id: "prod-prep",
      title: "Pre-Procedure Stop Supplements Pause List",
      handle: "preprocedure-stop-supplements-pause-list-2week-prep-guide",
      description: "Two-week prep guide for procedure planning.",
      thumbnail: svgDataUrl("Prep Guide", "#f5d0fe"),
      collection_id: withCollectionData ? "col-prep-guides" : null,
      variants: [
        {
          id: "variant-prep",
          title: "Guide",
          prices: [{ id: "price-prep", currency_code: "usd", amount: 1600 }],
        },
      ],
      metadata: { format: "Quick-check guide" },
    },
    {
      id: "prod-flags",
      title: "Avoid / Ask Clinician Interaction Flag Cards",
      handle: "avoid-ask-clinician-interaction-flag-cards-quick-check-deck",
      description: "Quick-check interaction flag cards.",
      thumbnail: svgDataUrl("Flag Cards", "#fde68a"),
      collection_id: withCollectionData ? "col-prep-guides" : null,
      variants: [
        {
          id: "variant-flags",
          title: "Deck",
          prices: [{ id: "price-flags", currency_code: "usd", amount: 2100 }],
        },
      ],
      metadata: { format: "Physical deck" },
    },
  ];
}

function buildSiteCommerce({
  slug,
  withCollectionData = true,
  cartHasItems = true,
}: {
  slug: "home" | "category" | "product";
  withCollectionData?: boolean;
  cartHasItems?: boolean;
}) {
  const products = buildProducts({ withCollectionData });
  return {
    siteFamily: "medusa-b2b-starter",
    commerceProvider: "medusa",
    storeName: "Honest Herbalist",
    regions: [
      {
        id: "reg-us",
        name: "United States",
        currency_code: "usd",
        countries: [{ iso_2: "us", display_name: "United States" }],
      },
    ],
    products,
    collections: withCollectionData
      ? [
          { id: "col-featured", title: "Featured", handle: "featured" },
          { id: "col-prep-guides", title: "Prep Guides", handle: "prep-guides" },
        ]
      : [{ id: "col-featured", title: "Featured", handle: "featured" }],
    categories: [
      { id: "cat-books", name: "Books", handle: "books" },
      { id: "cat-worksheets", name: "Worksheets", handle: "worksheets" },
    ],
    currentCategory: slug === "category" ? { id: "cat-books", name: "Books", handle: "books" } : null,
    currentProduct: slug === "product" ? products[0] : null,
    cart: cartHasItems
      ? {
          id: "cart-1",
          region_id: "reg-us",
          currency_code: "usd",
          subtotal: 5700,
          shipping_total: 900,
          tax_total: 0,
          total: 6600,
          items: [
            {
              id: "line-1",
              cart_id: "cart-1",
              title: products[0].title,
              variant_id: "variant-handbook",
              quantity: 1,
              unit_price: 3900,
              total: 3900,
              thumbnail: products[0].thumbnail,
              variant: { id: "variant-handbook", title: "Standard", prices: [] },
            },
          ],
        }
      : null,
  };
}

function buildPage(slug: "home" | "category" | "product" | "cart") {
  const pageMap = {
    "page-home": "home",
    "page-category": "category",
    "page-product": "product",
    "page-cart": "cart",
    "page-checkout": "checkout",
  };
  const pageTypeMap = {
    "page-home": "home",
    "page-category": "category",
    "page-product": "product_detail",
    "page-cart": "cart",
    "page-checkout": "checkout",
  };
  const sharedShell = [
    {
      type: "Section",
      props: {
        purpose: "header",
        layout: "full",
        containerWidth: "lg",
        variant: "default",
        padding: "none",
        content: [{ type: "StarterStoreHeader", props: { storeName: "Honest Herbalist", showSearch: true, showCart: true } }],
      },
    },
    {
      type: "Section",
      props: {
        purpose: "section",
        layout: "full",
        containerWidth: "lg",
        variant: "default",
        padding: "none",
        content: [
          {
            type: "StarterPromoBar",
            props: {
              message: "Practical tools for herbal practitioners and wellness professionals.",
              ctaLabel: "Browse catalog",
              linkType: "funnelPage",
              targetPageId: "page-category",
            },
          },
        ],
      },
    },
  ];

  const footer = {
    type: "Section",
    props: {
      purpose: "footer",
      layout: "full",
      containerWidth: "lg",
      variant: "default",
      padding: "none",
      content: [{ type: "StarterStoreFooter", props: { storeName: "Honest Herbalist", showCategories: true, showCollections: true } }],
    },
  };

  let content = [...sharedShell];
  if (slug === "home") {
    content = content.concat([
      {
        type: "Section",
        props: {
          purpose: "section",
          layout: "full",
          containerWidth: "lg",
          variant: "default",
          padding: "none",
          content: [
            {
              type: "StarterHomeHero",
              props: {
                eyebrow: "Honest Herbalist",
                title: "Practical tools for herbal practitioners",
                description: "Reference materials, worksheet pads, and quick-check resources grounded in the live catalog.",
                primaryCtaLabel: "Browse products",
                primaryLinkType: "funnelPage",
                primaryTargetPageId: "page-category",
                featuredProductHandles: [
                  "the-honest-herbalist-handbook",
                  "what-im-taking-doctor-visit-worksheet-pad",
                  "preprocedure-stop-supplements-pause-list-2week-prep-guide",
                ],
              },
            },
          ],
        },
      },
      {
        type: "Section",
        props: {
          purpose: "section",
          layout: "full",
          containerWidth: "lg",
          variant: "default",
          padding: "none",
          content: [{ type: "StarterCollectionRails", props: { maxCollections: 2, productsPerCollection: 2 } }],
        },
      },
      footer,
    ]);
  }

  if (slug === "category") {
    content = content.concat([
      {
        type: "Section",
        props: {
          layout: "contained",
          containerWidth: "lg",
          variant: "default",
          padding: "lg",
          content: [
            {
              type: "CommerceStoreTemplate",
              props: {
                content: [{ type: "CommerceProductGrid", props: { columns: 3 } }],
              },
            },
          ],
        },
      },
      footer,
    ]);
  }

  if (slug === "product") {
    content = content.concat([
      {
        type: "Section",
        props: {
          purpose: "section",
          layout: "contained",
          containerWidth: "lg",
          variant: "default",
          padding: "lg",
          content: [{ type: "CommerceProductDetail", props: {} }],
        },
      },
      footer,
    ]);
  }

  if (slug === "cart") {
    content = content.concat([
      {
        type: "Section",
        props: {
          purpose: "section",
          layout: "contained",
          containerWidth: "lg",
          variant: "default",
          padding: "lg",
          content: [{ type: "CommerceCart", props: {} }],
        },
      },
      footer,
    ]);
  }

  return {
    productSlug: PRODUCT_SLUG,
    funnelId: "funnel-1",
    publicationId: "publication-1",
    pageId: `page-${slug}`,
    slug,
    stage: "custom",
    puckData: {
      root: { props: { title: `Starter ${slug}`, description: `Starter ${slug} page` } },
      content,
      zones: {},
    },
    pageMap,
    pageStageMap: Object.fromEntries(Object.keys(pageMap).map((key) => [key, "custom"])),
    pageTypeMap,
    metadata: { title: `Starter ${slug}`, description: `Starter ${slug} page`, lang: "en", brandName: "Honest Herbalist" },
    tracking: null,
    nextPageId: slug === "home" ? "page-category" : slug === "category" ? "page-product" : null,
  };
}

async function mockStorefront(page: Page, options?: { withCollectionData?: boolean; cartHasItems?: boolean }) {
  const withCollectionData = options?.withCollectionData !== false;
  const cartHasItems = options?.cartHasItems !== false;

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/meta`, async (route) => {
    await route.fulfill({ json: { productSlug: PRODUCT_SLUG, funnelSlug: FUNNEL_SLUG, funnelId: "funnel-1", publicationId: "publication-1", entrySlug: "home", pages: [] } });
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/commerce`, async (route) => {
    await route.fulfill({ json: { productSlug: PRODUCT_SLUG, funnelSlug: FUNNEL_SLUG, funnelId: "funnel-1", product: { id: "legacy", title: "Legacy", variants: [], variants_count: 0 } } });
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/pages/*`, async (route) => {
    const slug = new URL(route.request().url()).pathname.split("/").pop();
    if (slug === "home" || slug === "category" || slug === "product" || slug === "cart") {
      await route.fulfill({ json: buildPage(slug) });
      return;
    }
    await route.abort();
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/site/commerce*`, async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const slug = pathname.endsWith("/cart")
      ? "cart"
      : url.searchParams.get("product_handle")
        ? "product"
        : url.searchParams.get("category")
          ? "category"
          : "home";
    await route.fulfill({ json: buildSiteCommerce({ slug: slug === "cart" ? "home" : slug, withCollectionData, cartHasItems }) });
  });

  await page.route("**/public/events", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
}

test.describe("starter storefront parity", () => {
  test.beforeEach(async ({ page }) => {
    await mockStorefront(page);
  });

  test("renders starter home shell and rails", async ({ page }) => {
    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/home`);

    await expect(page.getByTestId("starter-store-header")).toBeVisible();
    await expect(page.getByTestId("starter-promo-bar")).toBeVisible();
    await expect(page.getByTestId("starter-home-hero")).toBeVisible();
    await expect(page.getByTestId("starter-home-hero-media")).toBeVisible();
    await expect(page.getByTestId("starter-collection-rails")).toBeVisible();
    await expect(page.getByTestId("starter-store-footer")).toBeVisible();
    await expect(page).toHaveScreenshot("starter-home-desktop.png", { fullPage: true });
  });

  test("shows honest collection rail errors when live data is incomplete", async ({ page }) => {
    await mockStorefront(page, { withCollectionData: false });
    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/home`);

    await expect(page.getByText("Starter home requires at least one collection with attached products to render collection rails.")).toBeVisible();
  });

  test("renders category shell with promo and footer", async ({ page }) => {
    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/category?category=books`);

    await expect(page.getByTestId("starter-store-header")).toBeVisible();
    await expect(page.getByTestId("starter-promo-bar")).toBeVisible();
    await expect(page.getByTestId("category-container")).toBeVisible();
    await expect(page.getByText("Books").first()).toBeVisible();
    await expect(page.getByTestId("starter-store-footer")).toBeVisible();
  });

  test("supports catalog search without a full document reload", async ({ page }) => {
    const documentRequests: string[] = [];
    page.on("request", (request) => {
      if (request.resourceType() === "document") {
        documentRequests.push(request.url());
      }
    });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/category`);
    await page.waitForLoadState("networkidle");
    const requestCountAfterInitialLoad = documentRequests.length;

    const searchInput = page.getByRole("searchbox", { name: "Search products" });
    await searchInput.fill("worksheet");
    await searchInput.press("Enter");
    await page.waitForURL(/q=worksheet/);

    await expect(page.getByText('"What I’m Taking" Doctor-Visit Worksheet Pad')).toBeVisible();
    await expect(page.getByText("The Honest Herbalist Handbook")).toHaveCount(0);
    expect(documentRequests).toHaveLength(requestCountAfterInitialLoad);
  });

  test("renders product detail shell with starter header and footer", async ({ page }) => {
    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/product?product=the-honest-herbalist-handbook`);

    await expect(page.getByTestId("starter-store-header")).toBeVisible();
    await expect(page.getByTestId("starter-promo-bar")).toBeVisible();
    await expect(page.getByTestId("product-title")).toContainText("The Honest Herbalist Handbook");
    await expect(page.getByTestId("starter-store-footer")).toBeVisible();
    await expect(page).toHaveScreenshot("starter-pdp-desktop.png", { fullPage: true });
  });

  test("renders empty cart state without a dead checkout CTA", async ({ page }) => {
    await mockStorefront(page, { cartHasItems: false });

    const documentRequests: string[] = [];
    page.on("request", (request) => {
      if (request.resourceType() === "document") {
        documentRequests.push(request.url());
      }
    });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/cart`);
    await page.waitForLoadState("networkidle");
    const requestCountAfterInitialLoad = documentRequests.length;

    await expect(page.getByText("Your cart is empty")).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue Shopping" })).toBeVisible();
    await expect(page.getByRole("button", { name: /proceed to checkout/i })).toHaveCount(0);

    await page.getByRole("button", { name: "Continue Shopping" }).click();
    await page.waitForURL(/\/category$/);
    await expect(page.getByTestId("category-container")).toBeVisible();
    expect(documentRequests).toHaveLength(requestCountAfterInitialLoad);
  });
});

test.describe("starter storefront parity mobile", () => {
  test.use({ viewport: { width: 390, height: 1180 } });

  test.beforeEach(async ({ page }) => {
    await mockStorefront(page);
  });

  test("renders mobile starter home shell", async ({ page }) => {
    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/home`);

    await expect(page.getByTestId("starter-store-header")).toBeVisible();
    await page.getByLabel("Toggle navigation").click();
    await expect(page.getByRole("navigation", { name: "Mobile store navigation" })).toBeVisible();
    await expect(page).toHaveScreenshot("starter-home-mobile.png", { fullPage: true });
  });
});
