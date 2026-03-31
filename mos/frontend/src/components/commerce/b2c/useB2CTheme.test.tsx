import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";

import { useB2CCTATheme } from "./useB2CTheme";

function CTARadiusProbe() {
  const { style } = useB2CCTATheme();

  return <div data-testid="cta-probe" style={style} />;
}

describe("useB2CCTATheme", () => {
  it("prefers the pill radius token for CTA styling", () => {
    render(
      <DesignSystemProvider
        tokens={{
          cssVars: {
            "--color-cta": "rgb(38, 83, 146)",
            "--color-cta-text": "#ffffff",
            "--radius-md": "14px",
            "--radius-full": "999px",
          },
        }}
      >
        <CTARadiusProbe />
      </DesignSystemProvider>
    );

    expect(screen.getByTestId("cta-probe")).toHaveStyle({
      borderRadius: "999px",
      backgroundColor: "rgb(38, 83, 146)",
    });
  });
});
