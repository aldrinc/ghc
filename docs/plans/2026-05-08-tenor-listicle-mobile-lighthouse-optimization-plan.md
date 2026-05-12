# Tenor Listicle Mobile Lighthouse Optimization Plan

## Decision

Prioritize a mobile-only performance cleanup for the deployed Tenor `10-reasons-glp` listicle. The RMBC analytics hotfix is live and validated, but Lighthouse mobile performance is below the 85 target.

## Current Result

URL tested: `https://shoptenorco.com/8b89a76d/daily-drive-essentials/10-reasons-glp/?codex_validation=lighthouse_20260508T024016Z`

| Profile | Performance | Accessibility | Best Practices | SEO |
| --- | ---: | ---: | ---: | ---: |
| Mobile | 70 | 91 | 100 | 66 |
| Desktop | 99 | 91 | 96 | 66 |

Mobile vitals:

| Metric | Result |
| --- | ---: |
| First Contentful Paint | 3.4s |
| Largest Contentful Paint | 5.6s |
| Speed Index | 4.8s |
| Total Blocking Time | 0ms |
| Cumulative Layout Shift | 0 |

## Diagnosis

The mobile LCP element is the hero headline text, not an image. Lighthouse attributes the largest delay to element render delay, which points at render-blocking CSS/font work rather than JavaScript execution.

Primary findings:

- Reduce unused CSS: estimated 88 KiB savings on mobile.
- Minify CSS: estimated 14 KiB savings.
- LCP headline render delay: about 2.1s.
- JavaScript is not the bottleneck: TBT is 0ms.
- Images are already reasonably optimized for the current page.
- SEO is 66 because the page is blocked from indexing. Treat that as a business decision for paid-funnel pages, not a performance blocker.

## Implementation Plan

1. Split critical above-the-fold CSS into an inline critical block for the listicle hero, author row, offer bar, and first visible content.
2. Defer non-critical Replo/bundle CSS so it does not block first paint on mobile.
3. Remove or scope unused CSS from `bundle-7ee05610b5.css` for this standalone artifact.
4. Minify the remaining page CSS after pruning.
5. Reduce font blocking for the LCP headline:
   - keep `display=swap`;
   - preconnect to Google Fonts origins;
   - remove duplicate font-family requests that are not needed above the fold;
   - consider self-hosting the exact headline/body font subsets used on this page.
6. Keep current image optimization intact; do not rework images unless a later Lighthouse run identifies them as the LCP source.
7. Re-run Lighthouse mobile and desktop after each change and only deploy if:
   - mobile performance is at least 85;
   - desktop performance remains at least 95;
   - RMBC live analytics validation still passes;
   - no broken images or page errors are introduced.

## Deployment Guardrails

- Patch only `10-reasons-glp/index.html` and route-local assets.
- Take a backup before every deploy.
- Compare sibling route hashes before and after deploy; only the target listicle route may change.
- Do not touch the sales page.
