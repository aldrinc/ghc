# Medusa B2C React + Vite Port Parity Checklist

## Decision

- Pin upstream `medusajs/nextjs-starter-medusa` to commit `56c4a6fa2a0432430007ffa912a34573b665cf19`.
- Treat that commit as the only parity reference for this port.

## App routes under `src/app`

- [ ] `src/app/layout.tsx` root shell parity
- [ ] `src/app/[countryCode]/(main)/layout.tsx` main storefront shell parity
- [ ] `src/app/[countryCode]/(checkout)/layout.tsx` checkout shell parity
- [ ] `src/app/[countryCode]/(main)/page.tsx` home route parity
- [ ] `src/app/[countryCode]/(main)/store/page.tsx` store route parity
- [ ] `src/app/[countryCode]/(main)/collections/[handle]/page.tsx` collection route parity
- [ ] `src/app/[countryCode]/(main)/categories/[...category]/page.tsx` nested category route parity
- [ ] `src/app/[countryCode]/(main)/products/[handle]/page.tsx` product detail route parity
- [ ] `src/app/[countryCode]/(main)/cart/page.tsx` cart route parity
- [ ] `src/app/[countryCode]/(checkout)/checkout/page.tsx` checkout route parity
- [ ] `src/app/[countryCode]/(main)/account/@login/page.tsx` login shell parity
- [ ] `src/app/[countryCode]/(main)/account/@dashboard/page.tsx` account overview parity
- [ ] `src/app/[countryCode]/(main)/account/@dashboard/profile/page.tsx` profile parity
- [ ] `src/app/[countryCode]/(main)/account/@dashboard/addresses/page.tsx` address book parity
- [ ] `src/app/[countryCode]/(main)/account/@dashboard/orders/page.tsx` orders list parity
- [ ] `src/app/[countryCode]/(main)/account/@dashboard/orders/details/[id]/page.tsx` order detail parity
- [ ] `src/app/[countryCode]/(main)/order/[id]/confirmed/page.tsx` order confirmation parity
- [ ] `src/app/[countryCode]/(main)/order/[id]/transfer/[token]/page.tsx` transfer landing parity
- [ ] `src/app/[countryCode]/(main)/order/[id]/transfer/[token]/accept/page.tsx` transfer accept parity
- [ ] `src/app/[countryCode]/(main)/order/[id]/transfer/[token]/decline/page.tsx` transfer decline parity
- [ ] loading and not-found behaviors reviewed for cart, account, order confirmed, main, and checkout subtrees

## Templates under `src/modules`

- [ ] `home`
- [ ] `layout`
- [ ] `store`
- [ ] `collections`
- [ ] `categories`
- [ ] `products`
- [ ] `cart`
- [ ] `checkout`
- [ ] `account`
- [ ] `order`
- [ ] shared `common`
- [ ] shared `shipping`
- [ ] shared `skeletons`

## Data surfaces under `src/lib/data`

- [ ] `products.ts`
- [ ] `collections.ts`
- [ ] `categories.ts`
- [ ] `regions.ts`
- [ ] `locales.ts`
- [ ] `locale-actions.ts`
- [ ] `cart.ts`
- [ ] `fulfillment.ts`
- [ ] `payment.ts`
- [ ] `customer.ts`
- [ ] `orders.ts`
- [ ] `variants.ts`
- [ ] `cookies.ts`

## Cross-cutting parity references

- [ ] `src/middleware.ts` country detection, redirect, and query preservation behavior mapped to React + Vite runtime logic
- [ ] `src/lib/config.ts` Medusa SDK bootstrap mapped to shared browser runtime bootstrap
- [ ] `src/lib/data/cookies.ts` auth token, cart id, and cache id behavior mapped to one client-side persistence abstraction

## Marketi acceptance checks

- [ ] `medusa-b2c-starter` registered as a first-class site family
- [ ] nested public route model supports `/f/:productSlug/:funnelSlug/*sitePath`
- [ ] storefront commerce goes directly to Medusa, not MOS proxy endpoints
- [ ] account, address, order, and transfer flows are implemented or cleanly error when unsupported by Medusa/store config
- [ ] import and synthesis surfaces recognize B2C page roles without reviving legacy `Section` props
- [ ] no legacy `layout`, `containerWidth`, or `padding` keys survive in Medusa import output
