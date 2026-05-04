import { describe, expect, it } from "vitest";

import { buildSwipeCompanyQuery } from "./swipes";

describe("buildSwipeCompanyQuery", () => {
  it("includes the workspace client id when provided", () => {
    expect(
      buildSwipeCompanyQuery({
        source: "gethookd",
        clientId: "client-123",
        reviewStatus: "pending",
      }),
    ).toBe("?client_id=client-123&source=gethookd&review_status=pending");
  });

  it("omits client_id when it is not provided", () => {
    expect(
      buildSwipeCompanyQuery({
        source: "gethookd",
      }),
    ).toBe("?source=gethookd");
  });
});
