export type AppRoute = {
  path: string;
  label: string;
};

export const appRoutes: AppRoute[] = [
  { path: "/workspaces/sites/imports/:importId", label: "Site Import" },
  { path: "/workspaces/sites/imports", label: "Site Imports" },
  { path: "/workspaces/sites/templates/:templateId", label: "Site Template" },
  { path: "/workspaces/sites/templates", label: "Site Templates" },
  { path: "/workspaces/sites/:siteId/pages/:pageId", label: "Site Page Editor" },
  { path: "/workspaces/sites/:siteId/funnels/:funnelId", label: "Site Funnel" },
  { path: "/workspaces/sites/:siteId/funnels", label: "Site Funnels" },
  { path: "/workspaces/sites/:siteId", label: "Site Detail" },
  { path: "/workspaces/foundation-status", label: "Foundation Setup" },
  { path: "/workspaces/foundation-ready", label: "Foundation Complete" },
  { path: "/workspaces/overview", label: "Workspace Overview" },
  { path: "/workspaces/brand", label: "Brand Settings" },
  { path: "/workspaces/execution/analytics", label: "Analytics" },
  { path: "/workspaces/execution/postiz", label: "Postiz" },
  { path: "/workspaces/execution/social-agents", label: "Social Agents" },
  { path: "/workspaces/sites", label: "Sites" },
  { path: "/workspaces/products", label: "Products" },
  { path: "/strategy", label: "Strategy" },
  { path: "/campaigns", label: "Campaigns" },
  { path: "/commerce", label: "Commerce" },
  { path: "/research/documents", label: "Documents" },
  { path: "/research", label: "Research" },
  { path: "/research/funnels", label: "Funnels" },
  { path: "/creative-library", label: "Creative Library" },
  { path: "/claude-chat", label: "Assistant Chat" },
  { path: "/dev/components", label: "Component Review" },
];
