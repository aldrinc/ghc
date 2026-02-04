/**
 * Backwards-compatible export.
 *
 * The template now uses src/site/siteConfig.ts as the single source of truth
 * for content + UI copy + optional theme overrides.
 */
import { siteConfig } from '../../site/siteConfig'

export const defaultListicleConfig = siteConfig.page
