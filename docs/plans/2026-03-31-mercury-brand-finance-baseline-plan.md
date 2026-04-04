# Mercury Brand Finance Baseline Plan

## Decision

Use Mercury as the workspace-level treasury and reporting layer, not as the checkout provider.

The default topology should be:

- one workspace in Marketi = one brand operating unit
- one workspace = one finance baseline in Marketi
- one finance baseline = one dedicated Mercury account set for that brand
- many brand account sets may live inside one Mercury organization when they share the same legal entity
- create a separate Mercury organization only when the brand also needs separate legal/entity isolation

Do not model Mercury as another Medusa payment provider.
Do not overload `client_medusa_configs` with Mercury fields.

Mercury belongs beside Medusa and Stripe:

- Medusa + Stripe handle checkout, orders, payment sessions, payouts
- Mercury handles cash landing, account isolation, spend controls, reserves, and accounting/reconciliation surfaces

## Why This Is The Right Boundary

The current repo already uses the right pattern for commerce:

- workspace-scoped Medusa config in [`mos/backend/app/db/models.py`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py)
- reusable Stripe account profiles in [`mos/backend/app/db/models.py`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py)
- strict workspace/profile validation in [`mos/backend/app/routers/clients.py`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/clients.py)
- an explicit long-term plan for automatic commerce provisioning in [`docs/medusa-shopify-replacement-full-plan.md`](/Users/aldrinclement/Documents/programming/marketi/docs/medusa-shopify-replacement-full-plan.md)

Mercury should mirror that structure:

- shared org/legal-entity profile
- workspace attachment
- explicit account bindings
- explicit readiness states
- no hidden fallback behavior

This keeps checkout concerns and treasury concerns cleanly separated.

## Recommended Topology

| Layer | Default boundary | Notes |
| --- | --- | --- |
| Workspace / brand in Marketi | `1:1` | Existing operating unit in the repo |
| Medusa environment | `1:1` with workspace | Already aligned with the current Medusa plan |
| Stripe account profile | `many:1` allowed | Already implemented for shared or dedicated checkout merchants |
| Mercury organization profile | `many:1` allowed when brands share a legal entity | Separate org only for real legal/accounting isolation |
| Mercury brand account set | `1:1` with workspace | This is the key isolation boundary for reporting and cash control |

## Critical payout constraint

Brand-level Mercury isolation is only operationally clean when payout routing can also stay brand-specific.

That means at least one of these must be true:

- the workspace uses a dedicated Stripe merchant/profile
- the payout provider supports brand-level settlement routing
- Marketi introduces a more complex payout-routing layer such as Stripe Connect-style destination routing

If many workspaces share one Stripe merchant profile and all payouts settle into one bank destination, then Mercury account isolation becomes downstream bookkeeping only, not true operational isolation.

So the practical rule is:

- if you want true per-brand Mercury cash isolation, prefer dedicated Stripe profiles for those brands
- if you reuse shared Stripe profiles, treat Mercury isolation as partial until payout routing is solved explicitly

### Default for ecommerce launches

For most new brands launched under one parent company:

- keep one Mercury organization per legal entity
- create one Mercury account set per brand
- route payouts from Stripe/Shopify/Amazon into the brand's Mercury operating account
- keep brand-level spend, reserves, and reporting isolated by account bindings

### When to create a separate Mercury organization

Create a separate Mercury organization only when at least one of these is true:

- the brand has its own LLC/EIN
- the brand needs separate owners/admins in Mercury
- the brand needs separate bank statements for diligence or tax
- the brand will have material cash volume or risk that should not commingle
- the brand may be sold or financed independently

## Recommended Mercury Account Template Per Brand

Mercury's ecommerce guidance explicitly supports multiple checking/savings accounts, separate cards by checking account, and auto-transfer rules for taxes/profit/operating cash. Source: [Guide for Ecommerce](https://support.mercury.com/hc/en-us/articles/43283723809684-Guide-for-Ecommerce), [Setting up auto transfer rules](https://support.mercury.com/hc/en-us/articles/28768212621332-Setting-up-auto-transfer-rules).

Use this default account set:

| Account | Type | Purpose |
| --- | --- | --- |
| `Brand Operating` | Checking | Primary payout destination from Stripe and other channels |
| `Brand Ad Spend` | Checking | Funds Meta/TikTok/Google cards only |
| `Brand Tax Reserve` | Savings | Automatic tax set-aside |
| `Brand Returns Reserve` | Savings | Chargebacks, refunds, and operational buffer |
| `Brand Profit / HoldCo Sweep` | Savings or Treasury | Optional sweep for profit or excess cash |

Optional later:

- `Brand Inventory / COGS`
- `Brand Payroll / Contractors`
- `Brand Agency Clearing`

### Default Mercury controls

- create merchant-locked or vendor-specific cards from `Brand Ad Spend`
- maintain a target balance in `Brand Ad Spend`
- distribute a percentage of incoming funds from `Brand Operating` into `Tax Reserve`, `Returns Reserve`, and `Profit`
- invite accountant/bookkeeper users with read-only or accounting permissions

These are all first-class Mercury ecommerce patterns. Sources:

- [Guide for Ecommerce](https://support.mercury.com/hc/en-us/articles/43283723809684-Guide-for-Ecommerce)
- [Setting up auto transfer rules](https://support.mercury.com/hc/en-us/articles/28768212621332-Setting-up-auto-transfer-rules)
- [Connect your payment and accounting software](https://support.mercury.com/hc/en-us/articles/43480693275028-Connect-your-payment-and-accounting-software)

## Automation Boundary

## What Marketi can automate cleanly

- create org-level Mercury integration profile records
- bind a workspace to a Mercury organization profile
- register and verify Mercury webhook endpoints
- sync Mercury accounts, transactions, statements, and events into Marketi
- reconcile Stripe payouts and fees against Mercury cash deposits
- create default internal reporting views and daily rollups
- create explicit operator tasks when a required Mercury step is still manual

Mercury's public API documentation includes:

- accounts
- transactions
- statements
- events
- internal transfers
- webhooks

Sources:

- [Mercury API reference](https://docs.mercury.com/reference/listinvoices) because its navigation shows the available public resource families
- [Using the Mercury Sandbox for Testing](https://docs.mercury.com/docs/using-mercury-sandbox)

## What should be treated as manual unless Mercury grants a deeper integration

- Mercury organization creation / KYB / approval
- initial Mercury account opening in the dashboard
- cross-organization account linking
- any customer-facing OAuth integration

Important Mercury constraints:

- Mercury OAuth2 for integrations requires prior approval from Mercury. Source: [Integrations with OAuth2](https://docs.mercury.com/docs/integrations-with-oauth2)
- write-capable API tokens require IP allowlisting; unused tokens can be deleted and over-privileged tokens can be downgraded after 45 days. Source: [API Token Security Policies](https://docs.mercury.com/docs/api-token-security-policies)
- linking transfers across Mercury organizations are in closed beta and auto-transfers to linked accounts are not available. Source: [Linking and transferring between Mercury accounts across organizations](https://support.mercury.com/hc/en-us/articles/47272287713428-Linking-and-transferring-between-Mercury-accounts-across-organizations)

Inference from the published API reference: Mercury does not expose a public create-account endpoint today, so Marketi should assume account creation is a dashboard/operator step unless Mercury documents otherwise.

## How This Maps Onto Current Marketi Systems

## 1. Do not extend `client_medusa_configs` for Mercury

[`ClientMedusaConfig`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py) is already the workspace's commerce-backend record.

That table should stay focused on:

- Medusa URL and keys
- allowed payment providers
- webhook routing for checkout providers

Mercury is not a checkout provider and should not become one.

## 2. Copy the Stripe profile pattern

The Stripe pattern already exists:

- org-level reusable profile in [`StripeAccountProfile`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py)
- workspace attachment through [`ClientMedusaConfig`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/db/models.py)
- validation rules in [`mos/backend/app/routers/clients.py`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/routers/clients.py)

Mercury should use the same idea, but in a finance layer.

## 3. Add a separate finance provisioning workflow

Today the active onboarding runtime is still thin:

- the wizard creates workspace/product/onboarding payload
- [`ClientOnboardingWorkflow`](/Users/aldrinclement/Documents/programming/marketi/mos/backend/app/temporal/workflows/client_onboarding.py) immediately starts Strategy V2
- the current happy path does not yet run the older design-system/canon activities directly

Source: [`docs/onboarding-field-usage-map.md`](/Users/aldrinclement/Documents/programming/marketi/docs/onboarding-field-usage-map.md)

So the clean near-term approach is:

- start a separate `WorkspaceFinanceProvisioningWorkflow` from the same onboarding trigger
- keep it async and non-blocking for strategy generation
- surface readiness on the workspace

Longer term, once the Medusa provisioning plan lands, finance provisioning can run immediately after `provision_workspace_commerce_activity`, but it should still remain its own workflow/activity.

## Proposed Data Model

## Org-level reusable profile

Add `mercury_org_profiles`:

| Field | Purpose |
| --- | --- |
| `id` | Internal id |
| `org_id` | Marketi org boundary |
| `label` | Human-readable profile name |
| `legal_entity_name` | Matches Mercury legal entity |
| `mercury_organization_external_id` | Mercury org identifier if exposed |
| `api_token_ref` | Secret-manager reference |
| `webhook_secret_ref` | Secret-manager reference |
| `accounting_provider` | `quickbooks | xero | netsuite | none` |
| `status` | `active | pending_manual_setup | error | disabled` |
| `created_at`, `updated_at` | Audit |

## Workspace-level treasury binding

Add `client_treasury_configs`:

| Field | Purpose |
| --- | --- |
| `id` | Internal id |
| `org_id`, `client_id` | Workspace binding |
| `mercury_org_profile_id` | Which Mercury org/legal entity this workspace uses |
| `operating_account_id` | Primary payout landing account |
| `ad_spend_account_id` | Card funding account |
| `tax_reserve_account_id` | Reserve account |
| `returns_reserve_account_id` | Reserve account |
| `profit_account_id` | Optional sweep account |
| `finance_status` | `not_configured | waiting_on_mercury | accounts_bound | reporting_ready | error` |
| `last_sync_at` | Last successful sync |
| `last_sync_error` | Explicit failure message |

## Reporting and sync tables

Add:

- `client_treasury_sync_runs`
- `client_treasury_transactions`
- `client_payout_reconciliations`

Minimum fields for normalized transaction rows:

- `org_id`, `client_id`
- `provider = mercury`
- `external_transaction_id`
- `external_account_id`
- `direction`
- `amount`
- `currency`
- `transaction_date`
- `status`
- `normalized_type`
- `counterparty_name`
- `raw_metadata_json`
- `trace_id`
- `request_id`

## Reporting Model

Keep business reporting out of logs and traces, consistent with [`docs/mos-telemetry-spec.md`](/Users/aldrinclement/Documents/programming/marketi/docs/mos-telemetry-spec.md), but attach `trace_id` and `request_id` to source-of-record finance events for audit.

The baseline reporting model should have three layers:

### 1. Revenue and demand

Source systems:

- `FunnelOrder`
- normalized order-completion events
- Stripe payout data

Use for:

- gross sales
- refunds
- chargebacks
- processor fees
- net cash expected

### 2. Cash and bank movement

Source systems:

- Mercury accounts
- Mercury transactions
- Mercury statements
- Mercury events/webhooks

Use for:

- cash received
- bank-side timing
- transfers between reserve and operating accounts
- ad spend cash out

### 3. Reconciliation

Build one normalized brand ledger in Marketi that answers:

- expected payout vs received deposit
- payout fees vs bank net
- reserve movements
- unreconciled deposits
- brand cash position by account

## Accounting Strategy

Mercury already supports:

- QuickBooks Online, Xero, and NetSuite integrations
- syncing baseline bank-feed details multiple times a day
- GL codes, notes, receipts, and counterparty enrichment

Sources:

- [Managing accounting integrations](https://support.mercury.com/hc/en-us/articles/46240197437844-Managing-accounting-integrations)
- [Connect your payment and accounting software](https://support.mercury.com/hc/en-us/articles/43480693275028-Connect-your-payment-and-accounting-software)

For brands sharing one Mercury organization:

- use dedicated Mercury accounts per brand
- map each Mercury account to the matching ledger account in the accounting system
- if QuickBooks or NetSuite is the ERP, use Mercury classes for brand or channel segmentation where useful

Important limitation:

- Mercury classes do not apply to internal transfers. Source: [Using classes in Mercury](https://support.mercury.com/hc/en-us/articles/43275244012820-Using-classes-in-Mercury)

That means account structure still needs to carry the primary isolation burden.

## Provisioning Workflow

## Phase 1 workflow

1. User creates workspace/brand in Marketi.
2. Marketi attaches:
   - Medusa config
   - Stripe account profile
   - Mercury org profile
3. Marketi starts `WorkspaceFinanceProvisioningWorkflow`.
4. Workflow checks whether required Mercury account ids already exist.
5. If account ids are missing:
   - set status to `waiting_on_mercury`
   - create an explicit operator task with exact account names to create
   - stop cleanly with a visible status
6. If account ids exist:
   - bind account ids to workspace
   - register Mercury webhook endpoint
   - run initial accounts/transactions/events sync
   - create default reporting rows and readiness status
7. Nightly reconciliation job matches:
   - Stripe payout records
   - Mercury deposit transactions
   - MOS order totals

## No hidden fallback rule

If a required Mercury account binding is missing, the workflow should error or enter `waiting_on_mercury` with a precise operator action.

Do not silently dump the workspace into a shared generic operating account.

## Rollout

## Phase 1

- add Mercury profile + workspace binding tables
- add read-only Mercury sync
- add workspace finance readiness states
- add operator task generation for manual Mercury setup

## Phase 2

- add webhook ingestion
- add payout reconciliation against Stripe
- add daily brand cash dashboard
- add default account-template UI

## Phase 3

- add write-scoped automation behind static egress IPs
- enable internal transfer automation for reserve sweeps
- add accounting export or sync status into workspace finance view

## Bottom Line

The efficient baseline is not "one Mercury organization per site."

The efficient baseline is:

- one Marketi workspace per brand
- one dedicated Mercury account set per workspace
- one shared Mercury organization profile per legal entity when possible
- one separate Mercury organization only when legal isolation is actually required

That gives you:

- clean brand isolation
- better review speed
- easier reconciliation
- less KYB/admin overhead
- a workflow that can be automated honestly with today's public Mercury surface
