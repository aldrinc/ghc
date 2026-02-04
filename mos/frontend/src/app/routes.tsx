export type AppRoute = {
  path: string;
  label: string;
};

export const appRoutes: AppRoute[] = [
  { path: "/workspaces/overview", label: "Workspace Overview" },
  { path: "/workspaces/brand", label: "Brand Settings" },
  { path: "/workspaces/products", label: "Products" },
  { path: "/workflows", label: "Workflows" },
  { path: "/campaigns", label: "Campaigns" },
  { path: "/research/documents", label: "Documents" },
  { path: "/research", label: "Research" },
  { path: "/research/funnels", label: "Funnels" },
  { path: "/creative-library", label: "Creative Library" },
  { path: "/claude-chat", label: "Claude Chat" },
];
