export type AppRoute = {
  path: string;
  label: string;
};

export const appRoutes: AppRoute[] = [
  { path: "/tasks", label: "Tasks / Approvals" },
  { path: "/clients", label: "Clients" },
  { path: "/campaigns", label: "Campaigns" },
  { path: "/library", label: "Library" },
  { path: "/workflows", label: "Workflows" },
];
