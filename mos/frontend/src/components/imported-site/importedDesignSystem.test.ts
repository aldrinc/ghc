import { describe, expect, it } from "vitest";
import { buildImportedDesignSystemTokens } from "./importedDesignSystem";

describe("buildImportedDesignSystemTokens", () => {
  it("maps imported palette, fonts, and CTA radius into design-system tokens", () => {
    const tokens = buildImportedDesignSystemTokens({
      brandName: "The Honest Herbalist",
      theme: {
        palette: {
          primary: "rgb(38, 83, 146)",
          secondary: "rgb(0, 34, 102)",
          surface: "rgb(235, 242, 255)",
          background: "rgb(245, 248, 255)",
          text: "rgb(26, 26, 26)",
        },
        fonts: {
          heading: "Satoshi",
          body: "Satoshi",
        },
        cta: {
          borderRadius: "999px",
        },
      },
      headAssets: {
        stylesheetHrefs: [
          "https://api.fontshare.com/v2/css?f[]=satoshi@900,700,500,400&display=swap",
          "https://example.com/app.css",
        ],
      },
    });

    expect(tokens).toMatchObject({
      dataTheme: "light",
      brand: {
        name: "The Honest Herbalist",
      },
      fontUrls: [
        "https://api.fontshare.com/v2/css?f[]=satoshi@900,700,500,400&display=swap",
      ],
      cssVars: expect.objectContaining({
        "--font-heading": "Satoshi",
        "--font-sans": "Satoshi",
        "--color-brand": "rgb(0, 34, 102)",
        "--color-heading": "rgb(0, 34, 102)",
        "--color-cta": "rgb(38, 83, 146)",
        "--color-page-bg": "rgb(245, 248, 255)",
        "--color-page-bg-secondary": "rgb(235, 242, 255)",
        "--color-text": "rgb(26, 26, 26)",
        "--radius-full": "999px",
        "--pdp-radius-pill": "999px",
      }),
    });
  });
});
