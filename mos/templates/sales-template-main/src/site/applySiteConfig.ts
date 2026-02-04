import type { MetaConfig, SiteConfig, ThemeConfig } from './types'

function toCssVarName(key: string): string {
  const trimmed = key.trim()
  if (trimmed.startsWith('--')) return trimmed

  // If it's already kebab-case, just prefix.
  if (trimmed.includes('-')) return `--${trimmed}`

  // camelCase -> kebab-case, then prefix
  const kebab = trimmed.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
  return `--${kebab}`
}

export function applyThemeConfig(theme?: ThemeConfig) {
  if (!theme) return

  const root = document.documentElement

  if (theme.dataTheme) {
    root.setAttribute('data-theme', theme.dataTheme)
  }

  if (theme.tokens) {
    for (const [rawKey, rawValue] of Object.entries(theme.tokens)) {
      const cssVarName = toCssVarName(rawKey)
      root.style.setProperty(cssVarName, String(rawValue))
    }
  }
}

export function applyMetaConfig(meta: MetaConfig) {
  if (meta.lang) {
    document.documentElement.lang = meta.lang
  }

  document.title = meta.title

  if (meta.description) {
    let el = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    if (!el) {
      el = document.createElement('meta')
      el.setAttribute('name', 'description')
      document.head.appendChild(el)
    }
    el.setAttribute('content', meta.description)
  }
}

export function applySiteConfig(site: SiteConfig) {
  applyThemeConfig(site.theme)
  applyMetaConfig(site.meta)
}
