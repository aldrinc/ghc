/**
 * Very small template helper for configurable UI copy.
 *
 * Supports placeholders like `{index}` and `{rating}`.
 */
export function formatTemplate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_match, key) => {
    const value = values[key]
    // If a placeholder wasn't supplied, keep it in the output so it's obvious.
    return value === undefined || value === null ? `{${key}}` : String(value)
  })
}
