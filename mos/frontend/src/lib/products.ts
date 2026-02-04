import type { Product } from "@/types/products";

const STORAGE_KEY = "mos_active_product";

type StoredProduct = Pick<Product, "id" | "name" | "client_id"> & {
  category?: string | null;
};

type StoredState = Record<string, StoredProduct>;

const parseState = (raw: string | null): StoredState => {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as StoredState;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
};

export const loadActiveProduct = (workspaceId?: string | null): StoredProduct | null => {
  if (typeof window === "undefined" || !workspaceId) return null;
  const state = parseState(localStorage.getItem(STORAGE_KEY));
  return state[workspaceId] ?? null;
};

export const saveActiveProduct = (workspaceId: string, product: StoredProduct) => {
  if (typeof window === "undefined") return;
  try {
    const state = parseState(localStorage.getItem(STORAGE_KEY));
    state[workspaceId] = product;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore write errors
  }
};

export const clearActiveProduct = (workspaceId?: string | null) => {
  if (typeof window === "undefined") return;
  try {
    if (!workspaceId) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    const state = parseState(localStorage.getItem(STORAGE_KEY));
    delete state[workspaceId];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore write errors
  }
};
