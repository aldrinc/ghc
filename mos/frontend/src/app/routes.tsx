export type AppRoute = {
  path: string;
  label: string;
};

export const appRoutes: AppRoute[] = [
  { path: "/workspaces/overview", label: "Workspace Overview" },
  { path: "/workspaces/brand", label: "Brand Settings" },
  { path: "/workspaces/sites", label: "Sites" },
  { path: "/workspaces/sites/templates", label: "Site Templates" },
  { path: "/workspaces/sites/imports", label: "Site Imports" },
  { path: "/workspaces/sites/:siteId/funnels", label: "Site Funnels" },
  { path: "/workspaces/products", label: "Products" },
  { path: "/strategy", label: "Strategy" },
  { path: "/campaigns", label: "Campaigns" },
  { path: "/commerce", label: "Commerce" },
  { path: "/research/documents", label: "Documents" },
  { path: "/research", label: "Research" },
  { path: "/research/funnels", label: "Funnels" },
  { path: "/creative-library", label: "Creative Library" },
  { path: "/claude-chat", label: "Assistant Chat" },
];
