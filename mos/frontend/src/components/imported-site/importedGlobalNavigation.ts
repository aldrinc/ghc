type SlotRecord = Record<string, unknown>;

export const IMPORTED_FOOTER_GENERATED_LINKS = [
  { label: "Privacy Policy Button", originalText: "Privacy Policy", text: "Privacy Policy", href: "policies/privacy-policy" },
  { label: "Terms Of Service Button", originalText: "Terms of Service", text: "Terms of Service", href: "policies/terms-of-service" },
  { label: "Shipping Policy Button", originalText: "Shipping Policy", text: "Shipping Policy", href: "policies/shipping-policy" },
  { label: "Refund Policy Button", originalText: "Refund Policy", text: "Refund Policy", href: "policies/refund-policy" },
] as const satisfies ReadonlyArray<SlotRecord>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizeComparableText(value: unknown): string {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function getButtonSlots(sectionProps: Record<string, unknown>): SlotRecord[] {
  const current = Array.isArray(sectionProps.buttonSlots)
    ? (deepClone(sectionProps.buttonSlots) as SlotRecord[])
    : [];
  sectionProps.buttonSlots = current;
  return current;
}

function upsertButtonSlot(buttonSlots: SlotRecord[], slot: SlotRecord): void {
  const targetOriginalText = normalizeComparableText(slot.originalText);
  const targetLabel = normalizeComparableText(slot.label);
  const existingIndex = buttonSlots.findIndex((entry) => {
    return (
      normalizeComparableText(entry.originalText) === targetOriginalText ||
      normalizeComparableText(entry.label) === targetLabel
    );
  });

  if (existingIndex >= 0) {
    buttonSlots[existingIndex] = {
      ...buttonSlots[existingIndex],
      ...slot,
    };
    return;
  }

  buttonSlots.push(slot);
}

function isGlobalHeader(sectionProps: Record<string, unknown>): boolean {
  return (
    normalizeComparableText(sectionProps.componentName) === "globalheader" ||
    normalizeComparableText(sectionProps.sectionLabel) === "global header"
  );
}

function isGlobalFooter(sectionProps: Record<string, unknown>): boolean {
  return (
    normalizeComparableText(sectionProps.componentName) === "globalfooter" ||
    normalizeComparableText(sectionProps.sectionLabel) === "global footer"
  );
}

export function augmentImportedSourceSectionProps(props: Record<string, unknown>): Record<string, unknown> {
  if (!isRecord(props)) {
    return props;
  }

  const next = deepClone(props);
  const buttonSlots = getButtonSlots(next);

  if (isGlobalHeader(next)) {
    if (typeof next.sectionTargetId !== "string" || !next.sectionTargetId.trim()) {
      next.sectionTargetId = "global-header";
    }
    upsertButtonSlot(buttonSlots, {
      label: "Logo link",
      originalText: "OMNI",
      text: "The Honest Herbalist",
      href: "/",
    });
    upsertButtonSlot(buttonSlots, {
      label: "Shop Now button",
      originalText: "SHOP NOW",
      text: "Get Safe Dosing & Drug Interactions",
      href: "#product-purchase-section",
    });
    upsertButtonSlot(buttonSlots, {
      label: "Account Icon Button",
      originalText: "Account",
      text: "Account",
      href: "account",
    });
    upsertButtonSlot(buttonSlots, {
      label: "Cart Icon Button",
      originalText: "Cart",
      text: "Cart",
      href: "cart",
    });
    return next;
  }

  if (isGlobalFooter(next)) {
    if (typeof next.sectionTargetId !== "string" || !next.sectionTargetId.trim()) {
      next.sectionTargetId = "global-footer";
    }
    upsertButtonSlot(buttonSlots, {
      label: "Footer Logo link",
      originalText: "OMNI",
      text: "The Honest Herbalist",
      href: "/",
    });
    upsertButtonSlot(buttonSlots, {
      label: "Contact Us Button",
      originalText: "Contact Us",
      text: "Contact Support",
      href: "policies/contact-support",
    });
    for (const link of IMPORTED_FOOTER_GENERATED_LINKS) {
      upsertButtonSlot(buttonSlots, link);
    }
    upsertButtonSlot(buttonSlots, {
      label: "Shop Now Button",
      originalText: "Shop Now",
      text: "Start Reading",
      href: "#product-purchase-section",
    });
    upsertButtonSlot(buttonSlots, {
      label: "Account Login Button",
      originalText: "Account Login",
      text: "Log In",
      href: "account",
    });
    return next;
  }

  return next;
}
