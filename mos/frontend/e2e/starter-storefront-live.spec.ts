import { expect, test, type Page } from "@playwright/test";

const LIVE_ROUTE = process.env.STARTER_LIVE_ROUTE;

function resolveLiveUrl(baseURL: string | undefined): string {
  if (!LIVE_ROUTE) {
    throw new Error("STARTER_LIVE_ROUTE is required for the live starter storefront smoke test.");
  }
  if (LIVE_ROUTE.startsWith("http://") || LIVE_ROUTE.startsWith("https://")) {
    return LIVE_ROUTE;
  }
  const normalizedBase = (baseURL || "http://127.0.0.1:5275").replace(/\/$/, "");
  const normalizedRoute = LIVE_ROUTE.startsWith("/") ? LIVE_ROUTE : `/${LIVE_ROUTE}`;
  return `${normalizedBase}${normalizedRoute}`;
}

function trackDocumentRequests(page: Page): { urls: string[]; sinceLastCheck: () => number } {
  const urls: string[] = [];
  let cursor = 0;
  page.on("request", (request) => {
    if (request.resourceType() === "document") {
      urls.push(request.url());
    }
  });
  return {
    urls,
    sinceLastCheck: () => {
      const next = urls.length - cursor;
      cursor = urls.length;
      return next;
    },
  };
}

test.describe("starter storefront live smoke", () => {
  test.skip(!LIVE_ROUTE, "Set STARTER_LIVE_ROUTE to run live starter storefront smoke tests.");

  test("home renders without starter errors and hero CTA stays in-app", async ({ page, baseURL }) => {
    const documentRequests = trackDocumentRequests(page);
    const liveUrl = resolveLiveUrl(baseURL);

    await page.goto(liveUrl);
    await page.waitForLoadState("networkidle");
    documentRequests.sinceLastCheck();

    await expect(page.getByTestId("starter-store-header")).toBeVisible();
    await expect(page.getByTestId("starter-home-hero")).toBeVisible();
    await expect(page.getByTestId("starter-collection-rails")).toBeVisible();
    await expect(page.getByText("This storefront section is unavailable.")).toHaveCount(0);
    await expect(page.getByText(/could not resolve internal page target/i)).toHaveCount(0);
    await expect(page.getByTestId("starter-collection-rails").getByText("The Honest Herbalist Handbook")).toBeVisible();

    await page.getByRole("button", { name: /browse products/i }).click();
    await page.waitForURL(/\/category$/);
    await page.waitForLoadState("networkidle");

    expect(documentRequests.sinceLastCheck()).toBe(0);
    await expect(page.getByText("Loading page...")).toHaveCount(0);
  });

  test("category search filters results without a full document reload", async ({ page, baseURL }) => {
    const documentRequests = trackDocumentRequests(page);
    const liveUrl = resolveLiveUrl(baseURL).replace(/\/home$/, "/category");

    await page.goto(liveUrl);
    await page.waitForLoadState("networkidle");
    documentRequests.sinceLastCheck();

    const searchInput = page.getByRole("searchbox", { name: "Search products" });
    await expect(searchInput).toBeVisible();
    await searchInput.fill("worksheet");
    await searchInput.press("Enter");
    await page.waitForURL(/q=worksheet/);
    await page.waitForLoadState("networkidle");

    expect(documentRequests.sinceLastCheck()).toBe(0);
    await expect(page.getByText("Loading page...")).toHaveCount(0);
    await expect(page.getByText("Doctor-Visit Worksheet Pad")).toBeVisible();
    await expect(page.getByText("The Honest Herbalist Handbook")).toHaveCount(0);
    await expect(page.getByText(/No products matched/i)).toHaveCount(0);
  });

  test("cart empty state is usable and does not expose a dead checkout CTA", async ({ page, baseURL }) => {
    const documentRequests = trackDocumentRequests(page);
    const liveUrl = resolveLiveUrl(baseURL).replace(/\/home$/, "/cart");

    await page.goto(liveUrl);
    await page.waitForLoadState("networkidle");
    documentRequests.sinceLastCheck();

    await expect(page.getByText("Your cart is empty")).toBeVisible();
    await expect(page.getByRole("button", { name: /continue shopping/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /proceed to checkout/i })).toHaveCount(0);

    await page.getByRole("button", { name: /continue shopping/i }).click();
    await page.waitForURL(/\/category$/);
    await page.waitForLoadState("networkidle");

    expect(documentRequests.sinceLastCheck()).toBe(0);
    await expect(page.getByText("Loading page...")).toHaveCount(0);
  });
});
