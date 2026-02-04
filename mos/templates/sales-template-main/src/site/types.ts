import type { PdpConfig } from '../pages/PdpPage/types'

/**
 * Key/value overrides for CSS variables.
 *
 * Keys can be either:
 * - CSS var names ("--color-brand")
 * - kebab-case without the leading dashes ("color-brand")
 * - camelCase ("colorBrand")
 *
 * Values should include units when needed (e.g. "18px", "62px", "50s").
 */
export type ThemeTokenValue = string | number

export type ThemeTokens = Record<string, ThemeTokenValue>

export type ThemeConfig = {
  /**
   * Sets <html data-theme="..."> which can be used to activate theme blocks in CSS.
   * Example: the tokens.css file includes a :root[data-theme='dark'] block.
   */
  dataTheme?: string

  /**
   * Runtime token overrides. Keys are CSS variables.
   *
   * Example:
   * tokens: {
   *   '--color-brand': '#111827',
   *   '--hero-bg': '#fff7ed'
   * }
   */
  tokens?: ThemeTokens
}

export type MetaConfig = {
  /** Browser tab title */
  title: string
  /** Optional meta description */
  description?: string
  /** HTML lang attribute */
  lang?: string
}

export type UiCopy = {
  common: {
    /** Template supports {rating} */
    starsAriaLabelTemplate: string
  }

  modal: {
    closeAriaLabel: string
    dialogAriaLabel: string
  }

  reviews: {
    sectionAriaLabel: string
    prevButtonAriaLabel: string
    nextButtonAriaLabel: string
    dotsAriaLabel: string
    /** Template supports {index} */
    goToReviewAriaLabelTemplate: string
  }

  reviewWall: {
    verifiedLabel: string
  }
}

export type SiteConfig = {
  meta: MetaConfig
  theme?: ThemeConfig
  copy: UiCopy
  /** Page content */
  page: PdpConfig
}
