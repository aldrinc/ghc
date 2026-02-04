# PuppyPad Listicle React Template

This is a React + TypeScript + Vite template that recreates the structure of:
- https://campaigns.puppypad.co/listicle

## Run locally

```bash
npm install
npm run dev
```

## Customizing content (single object)

Edit:
- `src/site/siteConfig.ts`

That file is the single source of truth for:
- All visible copy (headers, subheaders, listicle items, reviews, CTAs)
- UI copy / aria labels (so nothing is hard-coded inside JSX)
- Optional runtime theme overrides (CSS variables)
- Basic meta (title / description / lang)

### Review carousel (under the listicle)
The review section is driven by:
- `siteConfig.page.reviews.slides[]` (text, author, optional rating, and up to 3 images)

### Bold text in pitch bullets
Pitch bullets support simple **bold** markup using `**double asterisks**`.
Example:
`"**Replaces Over 1,000 Disposable Pads** - Just wash & reuse"`

## Theming (fonts, colors, spacing)

Baseline theme tokens live in:
- `src/theme/tokens.css`

If you want theme changes to come from an object (for easy AI-driven site generation), use:
- `siteConfig.theme.tokens` inside `src/site/siteConfig.ts`

Example:
```ts
theme: {
  tokens: {
    '--color-brand': '#111827',
    '--hero-bg': '#fff7ed',
    '--marquee-speed': '35s'
  }
}
```

Tip: You can still override tokens without touching the template styles by importing an override file *after* `tokens.css` in `src/main.tsx`.

