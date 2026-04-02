import { describe, expect, it } from "vitest";
import { augmentImportedSourceSectionProps, IMPORTED_FOOTER_GENERATED_LINKS } from "./importedGlobalNavigation";

describe("augmentImportedSourceSectionProps", () => {
  it("adds account and cart routes to imported global headers", () => {
    const result = augmentImportedSourceSectionProps({
      componentName: "GlobalHeader",
      buttonSlots: [
        {
          label: "Shop Now button",
          originalText: "SHOP NOW",
          text: "Get Safe Dosing & Drug Interactions",
          href: "#product-purchase-section",
        },
      ],
    });

    expect(result.buttonSlots).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          originalText: "OMNI",
          href: "/",
        }),
        expect.objectContaining({
          originalText: "Account",
          href: "account",
        }),
        expect.objectContaining({
          originalText: "Cart",
          href: "cart",
        }),
      ]),
    );
  });

  it("rewrites imported global footer routes to storefront destinations", () => {
    const result = augmentImportedSourceSectionProps({
      componentName: "GlobalFooter",
      buttonSlots: [
        {
          label: "Account Login Button",
          originalText: "Account Login",
          text: "Account Login",
          href: "#login",
        },
      ],
    });

    expect(result.buttonSlots).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          originalText: "OMNI",
          href: "/",
        }),
        expect.objectContaining({
          originalText: "Contact Us",
          href: "policies/contact-support",
        }),
        expect.objectContaining({
          originalText: "Shop Now",
          href: "#product-purchase-section",
        }),
        expect.objectContaining({
          originalText: "Account Login",
          text: "Log In",
          href: "account",
        }),
        ...IMPORTED_FOOTER_GENERATED_LINKS.map((entry) => expect.objectContaining(entry)),
      ]),
    );
  });
});
