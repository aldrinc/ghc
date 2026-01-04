import type { Workspace } from "@/types/workspaces";

const STORAGE_KEY = "ghc_active_workspace";
const LEGACY_KEY = "ghc_active_idea";

const parseWorkspace = (raw: string | null): Workspace | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Workspace & { niche?: string };
    return {
      id: parsed.id,
      name: parsed.name,
      industry: parsed.industry ?? parsed.niche,
      lastActive: parsed.lastActive,
      status: parsed.status,
    };
  } catch {
    return null;
  }
};

export const loadActiveWorkspace = (): Workspace | null => {
  if (typeof window === "undefined") return null;
  const current = parseWorkspace(localStorage.getItem(STORAGE_KEY));
  if (current) return current;
  return parseWorkspace(localStorage.getItem(LEGACY_KEY));
};

export const saveActiveWorkspace = (workspace: Workspace) => {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
  } catch {
    // ignore write errors
  }
};

export const clearActiveWorkspace = () => {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore write errors
  }
};
