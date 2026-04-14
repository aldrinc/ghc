import type { Data } from "@measured/puck";

export function isImportedTemplatePageData(data: Data | null | undefined): boolean {
  if (!data || typeof data !== "object") return false;
  const content = Array.isArray((data as { content?: unknown }).content)
    ? ((data as { content: unknown[] }).content as Array<Record<string, unknown>>)
    : [];
  const first = content[0];
  return !!first && typeof first === "object" && first.type === "ImportedPage";
}
