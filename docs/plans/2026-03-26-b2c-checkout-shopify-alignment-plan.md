# B2C Checkout Shopify Alignment Plan

## Decision

Replace the current B2C starter checkout with a dedicated Shopify-style checkout experience.
Do not treat this as a CSS polish pass.

The current B2C checkout is only a thin wrapper around `completeCheckout()`:

- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx:1081`

The Mammotion target is a single-page progressive checkout with:

- express checkout methods at the top
- gated contact, delivery, shipping, and payment sections
- a sticky order summary
- provider-aware payment behavior
- legal/trust footer links

Route and template wiring already exist, so this is mostly a frontend + runtime rewrite, not a new funnel/template system:

- `mos/backend/app/templates/funnels/medusa-b2c-checkout.json:1`
- `mos/backend/app/services/site_blueprints.py:181`

## What I Reviewed

### Live target

Reviewed the live Mammotion checkout in the existing Brave session:

- `https://us.mammotion.com/checkouts/cn/hWNAGJHfpgGX4jzAMc41xGQz/en?_r=AQAB2px9nGXto3CzNSs2n26gH7o2gbnk7vgvy9laiI81DQ0`

Observed directly:

- centered brand header with minimal chrome
- express checkout row with `PayPal`, `G Pay`, and `Venmo`
- `Contact` section with `Sign in`
- `Delivery` section with country selector and full shipping form
- shipping methods disabled until address is entered
- payment section with multiple providers and expanded selected state
- right-side order summary with product row, discount/gift-card input, subtotal, shipping, and total
- legal footer links below the submit CTA

Inferred from the UI pattern and visible controls:

- express methods are eligibility-driven, not hard-coded
- shipping options refresh after address becomes valid
- payment methods refresh after shipping selection
- the bag icon likely controls mobile summary visibility
- address autocomplete is real behavior, not decorative UI

### Current implementation in repo

Current B2C checkout page:

- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx:1081`

Current B2C runtime surface:

- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:152`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:530`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:549`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:571`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:580`

Current Medusa data-layer support:

- `mos/frontend/src/lib/medusa/data.ts:230`
- `mos/frontend/src/lib/medusa/data.ts:289`
- `mos/frontend/src/lib/medusa/data.ts:372`
- `mos/frontend/src/lib/medusa/data.ts:385`
- `mos/frontend/src/lib/medusa/data.ts:407`
- `mos/frontend/src/lib/medusa/data.ts:420`
- `mos/frontend/src/lib/medusa/data.ts:442`

Existing richer checkout logic elsewhere in repo:

- `mos/frontend/src/components/commerce/CommerceBlocks.tsx:1767`

Current live starter coverage:

- `mos/frontend/e2e/starter-storefront-live.spec.ts:83`

## Current Baseline

Today the B2C starter checkout does this:

- renders the generic `PageShell`
- shows item count and total
- calls `completeCheckout()`
- navigates to order confirmation on success

Today it does not do this:

- collect contact details
- collect shipping address
- load or select shipping methods
- select payment providers
- manage billing address
- support discount code or gift card
- render express checkout methods
- render sticky summary behavior
- reflect Shopify-style section gating and inline validation

## Gap Matrix

| Area | Mammotion / Shopify-style target | Current B2C starter | Required change |
| --- | --- | --- | --- |
| Page structure | Single-page progressive checkout with summary aside | Generic page shell + total + button | Replace with dedicated checkout layout |
| Header | Minimal branded header | Standard page heading | Add checkout-specific top bar |
| Express checkout | Wallets shown above form | No express checkout UI | Add provider-driven express section |
| Contact | Email + sign-in entry point | No contact capture | Add email state, sign-in route, opt-in checkbox |
| Delivery | Full shipping form, country-aware | No delivery form | Add structured delivery form and validation |
| Address assist | Autocomplete affordance | None | Integrate real autocomplete or omit the affordance |
| Shipping methods | Disabled until address valid | Not shown | Load after valid address save/update |
| Payment methods | Inline provider selection with expanded selected state | None | Add provider list and selected-provider panel |
| Billing | Same-as-shipping toggle | None | Expose billing-address mutation and UI |
| Order summary | Sticky, line items, promo field, live totals | Basic total only | Build summary column and mobile summary behavior |
| Legal/trust | Security copy + policy links | None | Add footer links and trust copy |
| Validation | Inline, section-aware, progressive | Only generic submit error | Add field and section validation model |
| QA | Real checkout interactions | Empty-cart smoke only | Add checkout e2e coverage |

## Recommended Implementation Shape

### 1. Rebuild the page component

Primary file:

- `mos/frontend/src/components/commerce/b2c/pages/MedusaB2CAdditionalPages.tsx`

Recommended change:

- keep account pages where they are
- replace `MedusaB2CCheckoutPage` with a dedicated checkout composition
- do not reuse the generic `PageShell` for checkout

Suggested component split inside the same file first, then extract only if it becomes large:

- `CheckoutShell`
- `CheckoutExpressSection`
- `CheckoutContactSection`
- `CheckoutDeliverySection`
- `CheckoutShippingSection`
- `CheckoutPaymentSection`
- `CheckoutSummary`
- `CheckoutFooterLinks`

This keeps the first pass reviewable and avoids unnecessary file churn.

### 2. Use a single-page progressive state model

Do not reuse the B2B-style stepper UI from `CommerceCheckout`.
Use its sequencing logic as reference, but match the Mammotion interaction model instead.

Recommended local state:

- `email`
- `emailOptIn`
- `isAuthenticated`
- `shippingAddress`
- `saveInfoForNextTime`
- `shippingOptions`
- `shippingOptionsLoading`
- `selectedShippingOptionId`
- `paymentProviders`
- `paymentProvidersLoading`
- `selectedPaymentProviderId`
- `billingSameAsShipping`
- `billingAddress`
- `discountCode`
- `submitting`
- `fieldErrors`
- `sectionErrors`

Behavior rules:

- contact section should save email before checkout completion
- shipping methods should stay disabled until shipping address is valid enough to rate
- payment methods should stay disabled until shipping method is selected
- summary totals should update after shipping selection and promo application
- CTA should remain at the bottom of the payment section, not at the top of the page

### 3. Extend the B2C runtime where it is missing

Current B2C runtime already exposes:

- `updateCartEmail`
- `updateCartShippingAddress`
- `getShippingOptions`
- `selectShippingMethod`
- `getPaymentProviders`
- `initPaymentSession`
- `completeCheckout`

References:

- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:158`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:530`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:549`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:571`
- `mos/frontend/src/components/commerce/b2c/B2CRuntimeProvider.tsx:580`

What to add:

- `updateCartBillingAddress`
- a cleaner checkout-focused way to refresh checkout state after mutations
- promo-code / gift-card actions if the backend actually supports them
- explicit country/region handling when country changes mid-checkout

Important note:

The lower Medusa data layer already supports `billingAddress` in:

- `mos/frontend/src/lib/medusa/data.ts:289`

So exposing billing address in B2C runtime is a low-complexity gap.

### 4. Handle country and region correctly

The checkout target visibly exposes `Country/Region`.
That cannot be decorative.

Current cart creation seeds region/country here:

- `mos/frontend/src/lib/medusa/data.ts:230`

Implication:

- if country changes and the active cart region no longer matches, we need deterministic cart refresh behavior
- do not fake multi-country behavior in the UI if the current Medusa setup cannot support it cleanly

## Payment Reality Check

This is the biggest functional constraint.

Current payment support in the B2C path is:

- list providers: `mos/frontend/src/lib/medusa/data.ts:407`
- initialize session: `mos/frontend/src/lib/medusa/data.ts:420`
- complete cart: `mos/frontend/src/lib/medusa/data.ts:442`

That is enough for:

- provider selection UI
- redirect-based payment flows
- completing carts that rely on provider-side session state

That is not enough by itself for:

- true Shopify-style inline credit-card capture
- secure card-field tokenization in the page
- brand-accurate wallet capability detection

Decision rule:

- do not ship fake card fields
- do not hard-code PayPal / G Pay / Venmo / Klarna buttons unless they are actually enabled for the site
- if inline card capture is required, integrate the real provider SDK for the active Medusa payment provider

## Existing Reuse Opportunity

`CommerceCheckout` already contains useful sequencing logic:

- hydration from cart
- address validation
- shipping-method load
- payment-provider load
- redirect handling
- summary rendering

Reference:

- `mos/frontend/src/components/commerce/CommerceBlocks.tsx:1767`

Use it as logic reference only.
Do not copy its UI directly because:

- it is a stepper, not a one-page checkout
- it is styled for a different starter feel
- it documents a live shipping-address problem that must be verified before reuse

Important warning in existing code:

- `mos/frontend/src/components/commerce/CommerceBlocks.tsx:1873`

That comment explicitly says shipping address updates were causing a 500 on the live Medusa server in that implementation path.
Before building the new delivery section around server-side address saves, verify the current B2C runtime path is stable against the live Medusa backend.

## What We Should Not Do

- Do not skin the current one-button checkout and call it done.
- Do not add fake express wallets.
- Do not add a fake address-search icon without real autocomplete behind it.
- Do not render a discount / gift-card box unless apply/remove logic exists.
- Do not add inline card-number fields unless the real payment provider supports secure client-side collection.

## Recommended Delivery Order

1. Rebuild the checkout shell and sticky summary layout.
2. Add contact + delivery form state and hydrate from cart/customer data.
3. Wire shipping-option loading and selection.
4. Wire payment-provider loading and provider selection.
5. Add billing-address handling.
6. Add promo / gift-card support only if backed by real Medusa support.
7. Add provider-specific express checkout and inline payment integrations if supported.
8. Add legal links, trust text, and final polish.
9. Add e2e coverage and regression checks.

## Testing and QA

Current live test coverage does not validate checkout behavior:

- `mos/frontend/e2e/starter-storefront-live.spec.ts:83`

Add live or mocked e2e coverage for:

- empty cart route protection
- contact email persistence
- address validation
- shipping section disabled until address is valid
- shipping options load after address
- payment section disabled until shipping is selected
- payment provider selection
- summary total changes after shipping selection
- redirect-based provider behavior
- order completion success path
- inline error rendering for API failures

Manual QA checklist for parity review:

- desktop split layout matches expected information hierarchy
- mobile summary entry point is usable and obvious
- form sections unlock in the correct order
- field validation is visible and localized
- legal links remain accessible near the submit CTA
- no unsupported provider or promo affordance appears in the UI

## Acceptance Criteria

The rewrite is review-ready when:

- checkout visually reads like a Shopify-style single-page checkout
- it uses real runtime data for shipping, payment, and totals
- shipping and payment are gated by real checkout state
- unsupported capabilities are omitted rather than faked
- order summary stays legible and sticky on desktop
- mobile summary behavior is clear
- empty-cart and API-error states are clean
- checkout has e2e coverage beyond empty-cart smoke

## Bottom Line

This is a medium frontend rewrite plus a small runtime/API expansion.
It is not a new funnel type.
It is not a backend-heavy rearchitecture.

The critical implementation constraint is payment-provider realism:

- layout parity is straightforward
- interaction parity is straightforward
- full inline payment parity depends on the actual Medusa payment provider capabilities
