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

function buildB2CPage(slug: "cart" | "checkout" | "order/confirmed") {
  const pageMap = {
    "page-cart": "cart",
    "page-checkout": "checkout",
    "page-order-confirmed": "order/confirmed",
  };
  const pageTypeMap = {
    "page-cart": "cart",
    "page-checkout": "checkout",
    "page-order-confirmed": "order_confirmed",
  };

  const content = [
    {
      type: "Section",
      props: {
        purpose: "section",
        layout: "full",
        containerWidth: "xl",
        variant: "default",
        padding: "none",
        content: [
          {
            type: slug === "cart" ? "MedusaB2CCartPage" : slug === "checkout" ? "MedusaB2CCheckoutPage" : "MedusaB2COrderConfirmedPage",
            props: {},
          },
        ],
      },
    },
  ];

  return {
    productSlug: PRODUCT_SLUG,
    funnelId: "funnel-1",
    publicationId: "publication-1",
    pageId: slug === "cart" ? "page-cart" : slug === "checkout" ? "page-checkout" : "page-order-confirmed",
    slug,
    stage: "custom",
    puckData: {
      root: { props: { title: `B2C ${slug}`, description: `B2C ${slug} page` } },
      content,
      zones: {},
    },
    pageMap,
    pageStageMap: Object.fromEntries(Object.keys(pageMap).map((key) => [key, "custom"])),
    pageTypeMap,
    metadata: { title: `B2C ${slug}`, description: `B2C ${slug} page`, lang: "en", brandName: "Honest Herbalist" },
    tracking: null,
    nextPageId: slug === "cart" ? "page-checkout" : null,
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

async function mockB2CCheckout(
  page: Page,
  options?: { cartHasItems?: boolean; paymentRedirect?: boolean; shippingOptionFailure?: boolean },
) {
  const cartHasItems = options?.cartHasItems !== false;
  const paymentRedirect = options?.paymentRedirect === true;
  const shippingOptionFailure = options?.shippingOptionFailure === true;
  const backendUrl = "https://medusa.test";
  const recalculateCartTotal = <TCart extends { subtotal?: number; shipping_total?: number; tax_total?: number; discount_total?: number; total?: number }>(nextCart: TCart) => ({
    ...nextCart,
    total: (nextCart.subtotal || 0) + (nextCart.shipping_total || 0) + (nextCart.tax_total || 0) - (nextCart.discount_total || 0),
  });

  let cart = recalculateCartTotal({
    id: "cart-b2c-1",
    region_id: "reg-us",
    currency_code: "usd",
    email: "",
    shipping_address: undefined,
    billing_address: undefined,
    shipping_methods: [] as Array<{ id: string; shipping_option_id: string; price: number }>,
    subtotal: cartHasItems ? 3900 : 0,
    shipping_total: 0,
    discount_total: 0,
    tax_total: 0,
    promotions: [] as Array<{ id: string; code: string }>,
    items: cartHasItems
      ? [
          {
            id: "line-1",
            cart_id: "cart-b2c-1",
            title: "The Honest Herbalist Handbook",
            variant_id: "variant-handbook",
            quantity: 1,
            unit_price: 3900,
            total: 3900,
            variant: { id: "variant-handbook", title: "Standard", prices: [] },
          },
        ]
      : [],
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/meta`, async (route) => {
    await route.fulfill({
      json: {
        productSlug: PRODUCT_SLUG,
        funnelSlug: FUNNEL_SLUG,
        funnelId: "funnel-1",
        publicationId: "publication-1",
        entrySlug: "checkout",
        pages: [],
        medusaRuntimeConfig: {
          backendUrl,
          publishableKey: "pk_test_123",
          defaultCountryCode: "us",
        },
      },
    });
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/commerce`, async (route) => {
    await route.fulfill({ json: { productSlug: PRODUCT_SLUG, funnelSlug: FUNNEL_SLUG, funnelId: "funnel-1", product: { id: "legacy", title: "Legacy", variants: [], variants_count: 0 } } });
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/pages/**`, async (route) => {
    const url = new URL(route.request().url());
    const requestedSlug = decodeURIComponent(url.pathname.split(`/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/pages/`)[1] || "");
    if (requestedSlug === "cart" || requestedSlug === "checkout" || requestedSlug === "order/confirmed") {
      await route.fulfill({ json: buildB2CPage(requestedSlug as "cart" | "checkout" | "order/confirmed") });
      return;
    }
    await route.abort();
  });

  await page.route(`**/public/funnels/${PRODUCT_SLUG}/${FUNNEL_SLUG}/site/commerce*`, async (route) => {
    await route.fulfill({
      json: {
        siteFamily: "medusa-b2c-starter",
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
        products: [],
        collections: [],
        categories: [],
        currentCategory: null,
        currentProduct: null,
        cart,
      },
    });
  });

  await page.route(`${backendUrl}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (method === "GET" && path.endsWith("/store/regions")) {
      await route.fulfill({
        json: {
          regions: [
            {
              id: "reg-us",
              name: "United States",
              currency_code: "usd",
              countries: [{ iso_2: "us", display_name: "United States" }],
            },
          ],
        },
      });
      return;
    }

    if (method === "GET" && path.includes("/store/collections")) {
      await route.fulfill({ json: { collections: [] } });
      return;
    }

    if (method === "GET" && (path.includes("/store/product-categories") || path.includes("/store/categories") || path.includes("/store/category"))) {
      await route.fulfill({ json: { product_categories: [] } });
      return;
    }

    if (method === "POST" && /\/store\/carts\/?$/.test(path)) {
      await route.fulfill({ json: { cart } });
      return;
    }

    if (method === "GET" && path.includes(`/store/carts/${cart.id}`)) {
      await route.fulfill({ json: { cart } });
      return;
    }

    if (method === "POST" && path.includes(`/store/carts/${cart.id}`) && path.includes("shipping-method")) {
      const payload = request.postDataJSON() as { option_id?: string };
      cart = recalculateCartTotal({
        ...cart,
        shipping_methods: [{ id: "sm-1", shipping_option_id: payload.option_id || "ship-standard", price: 900 }],
        shipping_total: 900,
      });
      await route.fulfill({ json: { cart } });
      return;
    }

    if (method === "POST" && path.includes(`/store/carts/${cart.id}`) && path.includes("complete")) {
      await route.fulfill({ json: { type: "order", order: { id: "order-b2c-1" } } });
      return;
    }

    if ((method === "POST" || method === "DELETE") && path.includes(`/store/carts/${cart.id}/promotions`)) {
      const payload = request.postDataJSON() as { promo_codes?: string[] };
      const [code] = payload.promo_codes || [];
      if (!code) {
        await route.fulfill({ status: 400, json: { message: "Enter a discount code." } });
        return;
      }

      if (method === "POST") {
        if (code !== "HERBAL10") {
          await route.fulfill({ status: 400, json: { message: "Discount code is invalid." } });
          return;
        }
        cart = recalculateCartTotal({
          ...cart,
          discount_total: 500,
          promotions: [{ id: "promo-herbal10", code }],
        });
      } else {
        cart = recalculateCartTotal({
          ...cart,
          discount_total: 0,
          promotions: cart.promotions.filter((promotion) => promotion.code !== code),
        });
      }

      await route.fulfill({ json: { cart } });
      return;
    }

    if (method === "POST" && path.includes(`/store/carts/${cart.id}`)) {
      const payload = request.postDataJSON() as {
        email?: string;
        shipping_address?: typeof cart.shipping_address;
        billing_address?: typeof cart.billing_address;
      };
      cart = recalculateCartTotal({
        ...cart,
        email: payload.email ?? cart.email,
        shipping_address: payload.shipping_address ?? cart.shipping_address,
        billing_address: payload.billing_address ?? cart.billing_address,
      });
      await route.fulfill({ json: { cart } });
      return;
    }

    if (method === "GET" && path.includes("shipping-options")) {
      if (shippingOptionFailure) {
        await route.fulfill({ status: 500, json: { message: "Shipping service unavailable" } });
        return;
      }
      await route.fulfill({
        json: {
          shipping_options: [
            { id: "ship-standard", name: "Standard Shipping", amount: 900, currency_code: "usd", region_id: "reg-us", price_type: "flat" },
          ],
        },
      });
      return;
    }

    if (method === "GET" && path.includes("payment") && path.includes("provider")) {
      await route.fulfill({
        json: {
          payment_providers: [{ id: "paypal" }, { id: "manual_test" }],
        },
      });
      return;
    }

    if (method === "POST" && path.includes("payment")) {
      const payload = request.postDataJSON() as { provider_id?: string };
      const shouldRedirect = payload.provider_id === "paypal" || paymentRedirect;
      await route.fulfill({
        json: {
          payment_collection: {
            id: "paycol-1",
            status: "authorized",
            amount: cart.total,
            currency_code: "usd",
            payment_sessions: [
              {
                id: "session-1",
                provider_id: payload.provider_id || "manual_test",
                status: "pending",
                amount: cart.total,
                data: shouldRedirect ? { redirect_url: "https://payments.test/checkout" } : {},
              },
            ],
          },
        },
      });
      return;
    }

    await route.abort();
  });

  await page.route("https://payments.test/**", async (route) => {
    await route.fulfill({
      contentType: "text/html",
      body: "<html><body><h1>Redirected to provider</h1></body></html>",
    });
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

test.describe("b2c checkout parity", () => {
  test("protects the checkout route when the cart is empty", async ({ page }) => {
    await mockB2CCheckout(page, { cartHasItems: false });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("b2c-checkout-empty-state")).toBeVisible();
    await expect(page.getByRole("button", { name: "Back to cart" })).toBeVisible();

    await page.getByRole("button", { name: "Back to cart" }).click();
    await page.waitForURL(new RegExp(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/cart$`));
  });

  test("unlocks shipping and payment progressively and completes checkout", async ({ page }) => {
    await mockB2CCheckout(page);

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("b2c-checkout-contact")).toBeVisible();
    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("$39.00");
    await expect(page.getByTestId("b2c-checkout-shipping")).toContainText("Save a valid delivery address to load shipping options.");

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();

    await expect(page.getByTestId("b2c-shipping-options")).toBeVisible();
    await page.getByText("Standard Shipping").click();

    await expect(page.getByTestId("b2c-payment-providers")).toBeVisible();
    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("$48.00");
    await page.getByText("Manual Test").click();
    await page.getByTestId("b2c-complete-checkout").click();

    await page.waitForURL(new RegExp(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/order/order-b2c-1/confirmed$`));
  });

  test("applies and removes a discount code from the live order summary", async ({ page }) => {
    await mockB2CCheckout(page);

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    const summary = page.getByTestId("b2c-checkout-summary");
    const promo = page.getByTestId("b2c-checkout-promo");

    await expect(summary).toContainText("$39.00");

    await promo.getByPlaceholder("Enter code").fill("HERBAL10");
    await promo.getByRole("button", { name: "Apply" }).click();

    await expect(summary).toContainText("Discounts");
    await expect(summary).toContainText("-$5.00");
    await expect(summary).toContainText("$34.00");

    await promo.getByRole("button", { name: "Remove" }).click();

    await expect(summary).not.toContainText("Discounts");
    await expect(summary).toContainText("$39.00");
  });

  test("re-locks shipping totals and payment after delivery details change", async ({ page }) => {
    await mockB2CCheckout(page);

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();
    await page.getByText("Standard Shipping").click();

    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("$48.00");
    await expect(page.getByTestId("b2c-payment-providers")).toBeVisible();

    await deliverySection.getByLabel("Address").fill("456 Updated Avenue");
    await page.getByTestId("b2c-save-delivery").click();

    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("Calculated next");
    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("$39.00");
    await expect(page.getByTestId("b2c-checkout-payment")).toContainText("Choose a shipping method before selecting a payment option.");
  });

  test("disables checkout completion when delivery fields are edited after shipping selection", async ({ page }) => {
    await mockB2CCheckout(page);

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();
    await page.getByText("Standard Shipping").click();
    await page.getByText("Manual Test").click();

    await expect(page.getByTestId("b2c-complete-checkout")).toBeEnabled();

    await deliverySection.getByLabel("Address").fill("789 Unsaved Update");

    await expect(page.getByTestId("b2c-complete-checkout")).toBeDisabled();
    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("Calculated next");
    await expect(page.getByTestId("b2c-checkout-summary")).toContainText("$39.00");
  });

  test("express checkout auto-selects a single shipping option and redirects through the wallet provider", async ({ page }) => {
    await mockB2CCheckout(page, { paymentRedirect: true });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("b2c-checkout-express")).toBeVisible();
    await expect(page.getByTestId("b2c-express-provider-paypal")).toBeDisabled();

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();

    await expect(page.getByTestId("b2c-express-provider-paypal")).toBeEnabled();
    await page.getByTestId("b2c-express-provider-paypal").click();

    await page.waitForURL("https://payments.test/checkout");
    await expect(page.getByText("Redirected to provider")).toBeVisible();
  });

  test("renders inline shipping API failures", async ({ page }) => {
    await mockB2CCheckout(page, { shippingOptionFailure: true });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();

    await expect(page.getByTestId("b2c-checkout-shipping")).toContainText("Shipping service unavailable");
  });

  test("redirect-capable providers send the buyer to the provider flow", async ({ page }) => {
    await mockB2CCheckout(page, { paymentRedirect: true });

    await page.goto(`/f/${PRODUCT_SLUG}/${FUNNEL_SLUG}/us/checkout`);
    await page.waitForLoadState("networkidle");

    const deliverySection = page.getByTestId("b2c-checkout-delivery");
    await page.getByLabel("Email address").fill("buyer@example.com");
    await deliverySection.getByLabel("First name").fill("Taylor");
    await deliverySection.getByLabel("Last name").fill("Smith");
    await deliverySection.getByLabel("Address").fill("123 Market Street");
    await deliverySection.getByLabel("City").fill("Austin");
    await deliverySection.getByLabel("ZIP / Postal code").fill("78701");
    await page.getByTestId("b2c-save-delivery").click();
    await page.getByText("Standard Shipping").click();
    await page.getByTestId("b2c-payment-providers").getByText("PayPal", { exact: true }).click();
    await page.getByTestId("b2c-complete-checkout").click();

    await page.waitForURL("https://payments.test/checkout");
    await expect(page.getByText("Redirected to provider")).toBeVisible();
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
