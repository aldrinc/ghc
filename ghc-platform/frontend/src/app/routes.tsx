export type AppRoute = {
  path: string;
  label: string;
};

export const appRoutes: AppRoute[] = [
  { path: "/workspaces/overview", label: "Workspace Overview" },
  { path: "/workflows", label: "Workflows" },
  { path: "/campaigns", label: "Campaigns" },
  { path: "/research/documents", label: "Documents" },
  { path: "/research/competitors", label: "Competitors" },
  { path: "/research/ad-library", label: "Ad Library" },
  { path: "/research/funnels", label: "Funnels" },
  { path: "/explore/ads", label: "Explore Ads" },
  { path: "/explore/brands", label: "Explore Brands" },
  { path: "/strategy-sheet", label: "Strategy Sheet" },
  { path: "/experiments", label: "Experiments" },
  { path: "/creative-library", label: "Creative Library" },
];
