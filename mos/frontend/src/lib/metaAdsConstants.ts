import type { SelectOption } from "@/components/ui/select";

// ---------------------------------------------------------------------------
// Campaign Objective (ODAX)
// ---------------------------------------------------------------------------

export const META_CAMPAIGN_OBJECTIVES: SelectOption[] = [
  { label: "Sales (conversions)", value: "OUTCOME_SALES" },
  { label: "Traffic", value: "OUTCOME_TRAFFIC" },
  { label: "Leads", value: "OUTCOME_LEADS" },
  { label: "Engagement", value: "OUTCOME_ENGAGEMENT" },
  { label: "Awareness", value: "OUTCOME_AWARENESS" },
  { label: "App promotion", value: "OUTCOME_APP_PROMOTION" },
];

// ---------------------------------------------------------------------------
// Buying Type
// ---------------------------------------------------------------------------

export const META_BUYING_TYPES: SelectOption[] = [
  { label: "Auction (default)", value: "AUCTION" },
  { label: "Reserved (reach & frequency)", value: "RESERVED" },
];

// ---------------------------------------------------------------------------
// Optimization Goal
// ---------------------------------------------------------------------------

export const META_OPTIMIZATION_GOALS: SelectOption[] = [
  // Common
  { label: "Offsite conversions", value: "OFFSITE_CONVERSIONS" },
  { label: "Link clicks", value: "LINK_CLICKS" },
  { label: "Landing page views", value: "LANDING_PAGE_VIEWS" },
  { label: "Reach", value: "REACH" },
  { label: "Value", value: "VALUE" },
  { label: "Lead generation", value: "LEAD_GENERATION" },
  { label: "Impressions", value: "IMPRESSIONS" },
  { label: "ThruPlay (video)", value: "THRUPLAY" },
  { label: "App installs", value: "APP_INSTALLS" },
  // Divider
  { label: "\u2500\u2500\u2500 Less common \u2500\u2500\u2500", value: "__divider__", disabled: true },
  { label: "Post engagement", value: "POST_ENGAGEMENT" },
  { label: "Conversations", value: "CONVERSATIONS" },
  { label: "Page likes", value: "PAGE_LIKES" },
  { label: "Ad recall lift", value: "AD_RECALL_LIFT" },
  { label: "Event responses", value: "EVENT_RESPONSES" },
  { label: "Quality lead", value: "QUALITY_LEAD" },
  { label: "Quality call", value: "QUALITY_CALL" },
  { label: "Profile visit", value: "PROFILE_VISIT" },
];

// ---------------------------------------------------------------------------
// Billing Event
// ---------------------------------------------------------------------------

export const META_BILLING_EVENTS: SelectOption[] = [
  { label: "Impressions (CPM, default)", value: "IMPRESSIONS" },
  { label: "Link clicks (CPC)", value: "LINK_CLICKS" },
  { label: "ThruPlay (video)", value: "THRUPLAY" },
  { label: "App installs", value: "APP_INSTALLS" },
  { label: "Post engagement", value: "POST_ENGAGEMENT" },
  { label: "Page likes", value: "PAGE_LIKES" },
];

// ---------------------------------------------------------------------------
// Website Conversion Events
// ---------------------------------------------------------------------------

export const META_CUSTOM_EVENT_TYPES: SelectOption[] = [
  { label: "Purchase", value: "PURCHASE" },
  { label: "Lead", value: "LEAD" },
  { label: "Complete registration", value: "COMPLETE_REGISTRATION" },
  { label: "Initiate checkout", value: "INITIATE_CHECKOUT" },
  { label: "Add to cart", value: "ADD_TO_CART" },
  { label: "View content", value: "VIEW_CONTENT" },
  { label: "Subscribe", value: "SUBSCRIBE" },
];

// ---------------------------------------------------------------------------
// Special Ad Categories
// ---------------------------------------------------------------------------

export const META_SPECIAL_AD_CATEGORIES = [
  { label: "Credit", value: "CREDIT" },
  { label: "Employment", value: "EMPLOYMENT" },
  { label: "Housing", value: "HOUSING" },
  { label: "Issues / Elections / Politics", value: "ISSUES_ELECTIONS_POLITICS" },
  { label: "Online gambling & gaming", value: "ONLINE_GAMBLING_AND_GAMING" },
] as const;

// ---------------------------------------------------------------------------
// Country Targeting Tiers
// ---------------------------------------------------------------------------

export const META_COUNTRY_TIER_1 = [
  "US", "GB", "CA", "AU", "NZ", "DE", "FR", "IT", "ES", "NL",
  "SE", "NO", "DK", "FI", "CH", "AT", "BE", "IE", "LU",
] as const;

export const META_COUNTRY_TIER_2 = [
  "BR", "MX", "AR", "CL", "CO", "PL", "CZ", "RO", "HU", "PT",
  "GR", "IL", "JP", "KR", "SG", "HK", "AE", "SA", "ZA", "TR", "TH", "ID",
] as const;

export const META_COUNTRY_TIER_3 = [
  "IN", "PH", "VN", "BD", "PK", "NG", "EG", "KE", "MA", "PE",
] as const;

// ---------------------------------------------------------------------------
// Targeting JSON helpers
// ---------------------------------------------------------------------------

export function parseCountriesFromTargetingJson(json: string): string[] {
  try {
    const parsed = JSON.parse(json);
    const countries = parsed?.geo_locations?.countries;
    return Array.isArray(countries) ? countries : [];
  } catch {
    return [];
  }
}

export function mergeCountriesIntoTargetingJson(
  existingJson: string,
  addCountries: readonly string[],
): string {
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(existingJson);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      parsed = {};
    }
  } catch {
    // keep empty
  }
  const geo = (parsed.geo_locations as Record<string, unknown>) ?? {};
  const existing = Array.isArray(geo.countries) ? (geo.countries as string[]) : [];
  const merged = [...new Set([...existing, ...addCountries])];
  return JSON.stringify(
    { ...parsed, geo_locations: { ...geo, countries: merged } },
    null,
    2,
  );
}

export function clearCountriesFromTargetingJson(existingJson: string): string {
  let parsed: Record<string, unknown> = {};
  try {
    parsed = JSON.parse(existingJson);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return JSON.stringify({ geo_locations: { countries: [] } }, null, 2);
    }
  } catch {
    return JSON.stringify({ geo_locations: { countries: [] } }, null, 2);
  }
  const geo = (parsed.geo_locations as Record<string, unknown>) ?? {};
  return JSON.stringify(
    { ...parsed, geo_locations: { ...geo, countries: [] } },
    null,
    2,
  );
}
