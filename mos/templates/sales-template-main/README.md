# PuppyPad PDP React Template

This project recreates the **PuppyPad PDP (product landing page)** layout in React.

## Quick start

```bash
npm install
npm run dev
```

Then open the local URL Vite prints.

## One-place copy + content

All text and assets are driven from:

`src/site/siteConfig.ts`

Change anything inside `siteConfig.page` and the rendered page updates.

## Theming

Base design tokens live in:

`src/theme/tokens.css`

You can also override any token at runtime in:

`siteConfig.theme.tokens` (in `src/site/siteConfig.ts`).

Example:

```ts
theme: {
  tokens: {
    '--color-brand': '#061a70',
    '--hero-bg': '#e9fbff',
  },
},
```

## How to get the fonts from the live page

If you want this template to match the live site *exactly*, you’ll need to load the
same fonts. Here are two reliable ways:

### Option A: Chrome DevTools (fast)

1. Open the live page in Chrome.
2. Right-click the **heading** text → **Inspect**.
3. In the **Computed** panel, search for **font-family**.
4. Note the font name(s) (e.g. `Merriweather, serif`).

If it’s a **Google Font**, you can add it to `index.html`:

1. Go to Google Fonts, search the font name.
2. Choose the weights used on the page.
3. Copy the `<link rel="preconnect">` + `<link href="https://fonts.googleapis.com...">` tags.
4. Paste them into this template’s `index.html` (inside `<head>`).

Then update `src/theme/tokens.css`:

```css
:root {
  --font-heading: 'Your Font Name', serif;
  --font-sans: 'Your Sans Font', ui-sans-serif, system-ui, ...;
}
```

### Option B: Network tab (for custom/self-hosted fonts)

1. Open DevTools → **Network**.
2. Filter by **Font**.
3. Reload the page.
4. You’ll see `.woff` / `.woff2` files.

To self-host:

1. Download those files.
2. Put them in `public/fonts/...`.
3. Create `src/styles/fonts.css` with `@font-face` rules.
4. Import `fonts.css` once (e.g. in `src/main.tsx`).

## Replacing placeholder images

This template ships with SVG placeholders in `public/assets/ph-*.svg`.

Swap the `src` fields in `src/site/siteConfig.ts` with your real image URLs or local files in `public/`.

## Build

```bash
npm run build
npm run preview
```
