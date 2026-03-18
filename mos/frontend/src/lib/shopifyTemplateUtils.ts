import type {
  ClientShopifyThemeTemplateImageSlot,
  ClientShopifyThemeTemplateTextSlot,
  ClientShopifyThemeTemplateGenerateImagesResponse,
} from "@/api/clients";

export const DEFAULT_SHOPIFY_THEME_NAME = "futrgroup2-0theme";

export function parseStringMap(raw: string, label: string): { value?: Record<string, string>; error?: string } {
  if (!raw.trim()) return { value: {} };
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { error: `${label} must be a JSON object.` };
    }
    const normalized: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof key !== "string" || !key.trim()) {
        return { error: `${label} keys must be non-empty strings.` };
      }
      if (typeof value !== "string" || !value.trim()) {
        return { error: `${label} values must be non-empty strings.` };
      }
      normalized[key.trim()] = value.trim();
    }
    return { value: normalized };
  } catch {
    return { error: `${label} must be valid JSON.` };
  }
}

export function buildImageSlotPathOrder(slots: ClientShopifyThemeTemplateImageSlot[]): string[] {
  const orderedPaths: string[] = [];
  const seenPaths = new Set<string>();
  for (const slot of slots) {
    const path = typeof slot.path === "string" ? slot.path.trim() : "";
    if (!path || seenPaths.has(path)) continue;
    seenPaths.add(path);
    orderedPaths.push(path);
  }
  return orderedPaths;
}

export function orderStringMapByPreferredPaths(
  source: Record<string, string>,
  preferredPaths: string[],
): Record<string, string> {
  const ordered: Record<string, string> = {};
  const seenPaths = new Set<string>();

  for (const rawPath of preferredPaths) {
    const path = rawPath.trim();
    if (!path || seenPaths.has(path)) continue;
    if (!Object.prototype.hasOwnProperty.call(source, path)) continue;
    const rawValue = source[path];
    const value = typeof rawValue === "string" ? rawValue.trim() : "";
    if (!value) continue;
    ordered[path] = value;
    seenPaths.add(path);
  }

  for (const [rawPath, rawValue] of Object.entries(source)) {
    const path = rawPath.trim();
    const value = typeof rawValue === "string" ? rawValue.trim() : "";
    if (!path || !value || seenPaths.has(path)) continue;
    ordered[path] = value;
    seenPaths.add(path);
  }

  return ordered;
}

export function areStringMapsEqual(
  left: Record<string, string>,
  right: Record<string, string>,
): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  for (const key of leftKeys) {
    if (!Object.prototype.hasOwnProperty.call(right, key)) return false;
    if (left[key] !== right[key]) return false;
  }
  return true;
}

export function parseSlotPathList(raw: string): { value?: string[]; error?: string } {
  if (!raw.trim()) return { value: [] };
  const normalized: string[] = [];
  const seen = new Set<string>();
  const duplicatePaths: string[] = [];
  const segments = raw
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  for (const segment of segments) {
    if (seen.has(segment)) {
      duplicatePaths.push(segment);
      continue;
    }
    seen.add(segment);
    normalized.push(segment);
  }
  if (duplicatePaths.length) {
    return {
      error: `Duplicate slot path(s) in generation scope: ${duplicatePaths.join(", ")}`,
    };
  }
  return { value: normalized };
}

export function collectTemplateGenerationNonFatalErrors(
  response: ClientShopifyThemeTemplateGenerateImagesResponse,
): string[] {
  return [response.imageGenerationError?.trim(), response.copyGenerationError?.trim()].filter(
    (message): message is string => Boolean(message),
  );
}

export function humanizeSlotToken(raw: string): string {
  const normalized = raw
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_./-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "Image Slot";
  return normalized
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

export function deriveImageSlotBaseLabel(slot: ClientShopifyThemeTemplateImageSlot): string {
  const haystack = `${slot.role} ${slot.key} ${slot.path}`.toLowerCase();
  if (haystack.includes("feature")) return "Feature";
  if (haystack.includes("hero") && (haystack.includes("icon") || haystack.includes("badge"))) {
    return "Hero Icon";
  }
  if (haystack.includes("hero")) return "Hero Image";
  if (haystack.includes("gallery")) return "Gallery Image";
  if (haystack.includes("review") || haystack.includes("testimonial")) return "Review";

  if (slot.role.trim()) return humanizeSlotToken(slot.role);
  if (slot.key.trim()) return humanizeSlotToken(slot.key);

  const pathLeaf = slot.path.split(".").pop() || slot.path;
  return humanizeSlotToken(pathLeaf);
}

export function buildImageSlotReadableLabelMap(
  slots: ClientShopifyThemeTemplateImageSlot[],
): Map<string, string> {
  const baseByPath = slots.map((slot) => ({
    path: slot.path,
    baseLabel: deriveImageSlotBaseLabel(slot),
  }));
  const totalsByBase = new Map<string, number>();
  for (const entry of baseByPath) {
    totalsByBase.set(entry.baseLabel, (totalsByBase.get(entry.baseLabel) || 0) + 1);
  }
  const seenByBase = new Map<string, number>();
  const labelsByPath = new Map<string, string>();
  for (const entry of baseByPath) {
    const total = totalsByBase.get(entry.baseLabel) || 0;
    if (total <= 1) {
      labelsByPath.set(entry.path, entry.baseLabel);
      continue;
    }
    const nextIndex = (seenByBase.get(entry.baseLabel) || 0) + 1;
    seenByBase.set(entry.baseLabel, nextIndex);
    labelsByPath.set(entry.path, `${entry.baseLabel} ${nextIndex}`);
  }
  return labelsByPath;
}

export function deriveTextSlotBaseLabel(slot: ClientShopifyThemeTemplateTextSlot): string {
  const haystack = `${slot.key} ${slot.path}`.toLowerCase();
  if (haystack.includes("headline") || haystack.includes("heading") || haystack.includes("title")) {
    return "Headline";
  }
  if (haystack.includes("subheading") || haystack.includes("subtitle")) {
    return "Subheadline";
  }
  if (haystack.includes("feature")) return "Feature Copy";
  if (haystack.includes("body") || haystack.includes("description")) return "Body Copy";
  if (haystack.includes("cta") || haystack.includes("button")) return "CTA Label";
  if (haystack.includes("review") || haystack.includes("testimonial")) return "Review Copy";
  if (slot.key.trim()) return humanizeSlotToken(slot.key);
  const pathLeaf = slot.path.split(".").pop() || slot.path;
  return humanizeSlotToken(pathLeaf);
}

export function buildTextSlotReadableLabelMap(
  slots: ClientShopifyThemeTemplateTextSlot[],
): Map<string, string> {
  const baseByPath = slots.map((slot) => ({
    path: slot.path,
    baseLabel: deriveTextSlotBaseLabel(slot),
  }));
  const totalsByBase = new Map<string, number>();
  for (const entry of baseByPath) {
    totalsByBase.set(entry.baseLabel, (totalsByBase.get(entry.baseLabel) || 0) + 1);
  }
  const seenByBase = new Map<string, number>();
  const labelsByPath = new Map<string, string>();
  for (const entry of baseByPath) {
    const total = totalsByBase.get(entry.baseLabel) || 0;
    if (total <= 1) {
      labelsByPath.set(entry.path, entry.baseLabel);
      continue;
    }
    const nextIndex = (seenByBase.get(entry.baseLabel) || 0) + 1;
    seenByBase.set(entry.baseLabel, nextIndex);
    labelsByPath.set(entry.path, `${entry.baseLabel} ${nextIndex}`);
  }
  return labelsByPath;
}
