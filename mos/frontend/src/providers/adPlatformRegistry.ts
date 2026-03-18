import type { AdPlatformAdapter, AdPlatformId } from "@/types/adPlatform";
import { MetaAdapter } from "./meta/MetaAdapter";

const registry = new Map<AdPlatformId, AdPlatformAdapter>();

// Register built-in adapters
registry.set(MetaAdapter.id, MetaAdapter);

export function registerAdapter(adapter: AdPlatformAdapter) {
  registry.set(adapter.id, adapter);
}

export function getAdapter(id: AdPlatformId): AdPlatformAdapter | undefined {
  return registry.get(id);
}

export function getRegisteredPlatforms(): AdPlatformId[] {
  return Array.from(registry.keys());
}

export function getAllAdapters(): AdPlatformAdapter[] {
  return Array.from(registry.values());
}
