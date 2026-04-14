# Dedicated Medusa Per Workspace With Reusable Stripe Accounts Plan

## Decision

Phase 1 should assume:

1. every workspace gets its own Medusa environment
2. the selected Stripe account is a reusable profile
3. one Stripe account profile may be attached to many Medusa environments

That is the topology to design for.

In plain terms:

- Workspace A -> Medusa A -> Stripe Shared
- Workspace B -> Medusa B -> Stripe Shared
- Workspace C -> Medusa C -> Stripe Shared

And when a workspace needs its own Stripe account:

- Workspace D -> Medusa D -> Stripe D

Do not optimize phase 1 around a shared multi-workspace Medusa environment.

Do not keep direct Stripe checkout in MOS as the long-term path.

The correct architecture for your requirement is:

- one workspace
- one Medusa environment
- one selected Stripe account profile

Where the Stripe account profile can be reused across multiple workspaces.

## Requirement Matrix

| Requirement | Phase 1 status | Notes |
| --- | --- | --- |
| One Medusa environment per workspace | Required | This matches your intended operating model |
| Different workspaces can use different Stripe accounts | Required | Select a different Stripe profile at workspace creation |
| Different workspaces can reuse the same Stripe account | Required | Multiple Medusa environments may point at the same Stripe profile |
| MOS remains the place where the workspace selects its commerce wiring | Required | MOS chooses the Stripe profile and provisions the environment |
| Stripe remains owned by Medusa for checkout execution | Required | MOS should not remain the direct Stripe checkout owner |

## Topology Summary

This is the intended cardinality:

| Layer | Cardinality |
| --- | --- |
| Workspace -> Medusa environment | `1:1` |
| Medusa environment -> Stripe account profile | `many:1` allowed |
| Stripe account profile -> Medusa environment | `1:many` allowed |

That means:

- every workspace has its own store
- every store has its own Medusa environment
- many stores may still share the same Stripe merchant account

This is not:

- many workspaces sharing one Medusa environment

This is:

- many workspaces
- many Medusa environments
- one shared Stripe account when desired

## Revised Architecture

## 1. Keep workspace-scoped Medusa config

The current repo already stores Medusa config per workspace in `client_medusa_configs`.

That is aligned with your clarified requirement because each workspace will have its own Medusa environment.

Relevant code:

- `mos/backend/app/db/models.py`
- `mos/backend/app/services/medusa_connection.py`
- `mos/backend/app/routers/clients.py`

This means phase 1 does not need the environment-vs-binding split I outlined earlier.

For your chosen topology, the simpler model is better:

- keep `client_medusa_configs` as the workspace's Medusa environment record
- add Stripe-account selection to that model

## 2. Add StripeAccountProfile

Add a new reusable profile model for Stripe credentials.

Suggested fields:

| Field | Purpose |
| --- | --- |
| `id` | Internal identifier |
| `org_id` | Ownership boundary |
| `label` | Human-readable profile name |
| `stripe_account_id` | Stripe account identifier for review/debugging |
| `secret_key_ref` | Secret-manager reference for the Stripe secret key |
| `webhook_secret_ref` | Secret-manager reference for the shared webhook endpoint secret |
| `mode` | `shared` or `dedicated` |
| `status` | `active`, `disabled`, `error` |
| `created_at`, `updated_at` | Audit |

Important rule:

- do not store raw Stripe secrets in the MOS database
- store secret-manager references only

## 3. Link each workspace Medusa config to one StripeAccountProfile

Extend `client_medusa_configs` with:

| Field | Purpose |
| --- | --- |
| `stripe_account_profile_id` | Which Stripe account this workspace's Medusa environment should use |
| `default_payment_provider_id` | Which Medusa payment provider ID should be selected by default |
| `allowed_payment_provider_ids` | Explicit checkout allowlist for the workspace |
| `webhook_routing_mode` | `direct` or `shared_ingress` |

Why this is the right boundary:

- Medusa environment settings stay per workspace
- Stripe credentials become reusable across many workspaces
- MOS can say "workspace A and workspace B both use Stripe profile X"

## Why This Fits The Current Repo Better

## 1. The repo already thinks in per-workspace Medusa config

Current Medusa config is saved per workspace, not globally:

- `mos/backend/app/db/models.py`
- `mos/backend/app/services/medusa_connection.py`

That is already the right direction if the intended topology is one Medusa environment per workspace.

## 2. The repo already has Medusa checkout plumbing

The newer site checkout flow already uses Medusa for:

- payment provider listing
- payment session initialization
- cart completion

Relevant code:

- `mos/backend/app/routers/public_funnels.py`
- `mos/backend/app/services/medusa_store_runtime.py`
- `mos/frontend/src/components/commerce/CommerceBlocks.tsx`

That means the real missing work is not "how to use Medusa".

The missing work is:

- how to select the Stripe account when provisioning a workspace
- how to make one Stripe account safely back many Medusa environments

## 3. The current admin UI is still missing key setup

The current workspace Medusa form exposes:

- Base URL
- Admin API Key

but not the publishable key.

Relevant code:

- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`

That must be fixed regardless of which Stripe-account topology you choose.

## Stripe Reuse Is The Main New Problem

## What "reusing one Stripe account across many Medusa environments" actually means

If workspace A and workspace B both select the same Stripe profile, then:

- both Medusa environments will use the same Stripe secret key
- both Medusa environments will create payments in the same Stripe account
- Stripe webhook delivery becomes the primary architectural constraint

The credentials reuse is straightforward.

The webhook and event-routing model is the hard part.

## Why naive webhook wiring is not good enough

Medusa's Stripe docs show webhook handling per Medusa application, using a payment hook route shaped like:

- `{server_url}/hooks/payment/{provider_id}`

Source:

- [Stripe Module Provider](https://docs.medusajs.com/resources/commerce-modules/payment/payment-provider/stripe)
- [Payment Webhook Events](https://docs.medusajs.com/resources/commerce-modules/payment/webhook-events)

Stripe's docs also say:

- you can register webhook endpoints on a Stripe account
- one Stripe account supports up to 16 webhook endpoints

Source:

- [Add a webhook endpoint](https://docs.stripe.com/development/dashboard/webhooks)

That creates two concrete problems if one Stripe account is reused across many Medusa environments:

1. endpoint-count pressure
2. event-routing ambiguity

Even before scale, endpoint-per-environment is the wrong default for your model.

## Recommended webhook strategy

For any Stripe account profile reused by more than one Medusa environment:

- do not register one direct Stripe webhook endpoint per Medusa environment as the default architecture
- use one shared webhook ingress per Stripe account profile

That ingress should:

1. receive Stripe events for the shared account
2. verify the Stripe signature using that profile's webhook secret
3. resolve the owning Medusa environment
4. forward the event, or a normalized internal event, to the correct Medusa environment only

## What is required for routing

To route a Stripe event to the correct Medusa environment, the payment objects need a stable environment marker.

Recommended metadata to stamp into the Stripe-side payment object through Medusa customization:

| Metadata key | Purpose |
| --- | --- |
| `marketi_client_id` | Workspace identifier |
| `marketi_medusa_env_id` | Internal Medusa environment identifier |
| `marketi_funnel_id` | Attribution continuity |
| `marketi_publication_id` | Attribution continuity |

Without this metadata, one-account-many-environments is not operationally clean.

## Important implementation note

This probably requires a small Medusa customization or plugin, because the routing metadata must exist on the Stripe-side payment object before webhook delivery happens.

Do not assume the out-of-the-box configuration is enough for this part.

## Current Gaps In The Repo

## 1. No StripeAccountProfile abstraction

There is no current concept of:

- reusable Stripe credentials
- Stripe profile selection at workspace creation
- one Stripe profile backing many Medusa environments

This is the main missing data-model feature.

## 2. Direct Stripe is still present in MOS

The legacy direct Stripe path still exists in:

- `mos/backend/app/routers/public_funnels.py`
- `mos/backend/app/routers/stripe_webhooks.py`

That should not remain the primary checkout implementation once Medusa is the workspace commerce backend.

## 3. Payment-provider filtering is still too loose

The current checkout UI fetches payment providers from Medusa and renders what comes back.

Relevant code:

- `mos/frontend/src/components/commerce/CommerceBlocks.tsx`

Even with dedicated Medusa environments, the workspace should still pin:

- which provider IDs are allowed
- which provider ID is the default

That keeps checkout behavior deterministic.

## 4. Publishable-key setup is still incomplete in the UI

The Store API runtime requires the publishable key, but the current workspace UI does not expose it.

Relevant code:

- `mos/backend/app/services/medusa_store_runtime.py`
- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`

## Recommended Data Model

## Extend `client_medusa_configs`

Keep this table as the per-workspace Medusa environment record.

Add:

| Field | Purpose |
| --- | --- |
| `stripe_account_profile_id` | Selected Stripe account profile |
| `default_payment_provider_id` | Expected Medusa provider ID |
| `allowed_payment_provider_ids` | Expected provider allowlist |
| `webhook_routing_mode` | `direct` or `shared_ingress` |

This is enough for phase 1.

Do not add a more abstract shared-environment model unless the product requirement changes again.

## Add `stripe_account_profiles`

Create a reusable table for Stripe profiles.

Expected relationship:

- one Stripe profile
- many workspace Medusa configs

That directly expresses the requirement you clarified.

## Step-By-Step Plan

## Phase 0: Freeze The Topology

Document these as phase-1 rules:

1. every workspace gets a dedicated Medusa environment
2. each workspace chooses one Stripe account profile
3. many workspaces may reuse the same Stripe account profile
4. direct Stripe checkout in MOS is legacy only

This decision should replace the earlier shared-Medusa assumption.

## Phase 1: Add StripeAccountProfile Support

Implementation work:

1. add `stripe_account_profiles` table
2. add `stripe_account_profile_id` to `client_medusa_configs`
3. add `default_payment_provider_id`
4. add `allowed_payment_provider_ids`
5. add `webhook_routing_mode`

Implementation areas:

- `mos/backend/app/db/models.py`
- new Alembic migration after existing Medusa migrations
- `mos/backend/app/schemas/medusa_connection.py`
- `mos/backend/app/services/medusa_connection.py`
- `mos/backend/app/routers/clients.py`

## Phase 2: Update Workspace Creation And Admin UI

When creating or configuring a workspace, the operator must be able to choose:

1. Medusa base URL
2. Medusa admin API key
3. Medusa publishable key
4. Stripe account profile

If the workspace is provisioned automatically, the UI can show the selected profile and resulting Medusa environment rather than asking for raw values manually.

Implementation areas:

- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`
- `mos/frontend/src/api/products.ts`

## Phase 3: Provision Dedicated Medusa Environment Per Workspace

Provisioning flow:

1. create workspace
2. select Stripe account profile
3. provision dedicated Medusa environment
4. inject the selected Stripe profile's secret key into that Medusa environment
5. configure the Stripe payment provider in that environment
6. create or retrieve the Medusa publishable key
7. save workspace Medusa config in MOS

Important rule:

- the Medusa environment is dedicated
- only the Stripe profile is reused

## Phase 4: Decide Webhook Mode Per Stripe Profile

### Mode A: Direct webhook

Use only when a Stripe profile is attached to exactly one Medusa environment.

In this mode:

- Stripe sends events directly to that environment's Medusa payment hook
- Medusa verifies and processes them normally

### Mode B: Shared ingress

Use when a Stripe profile is attached to more than one Medusa environment.

In this mode:

- Stripe sends events to one shared ingress endpoint for that profile
- the ingress resolves the target Medusa environment
- the ingress routes the event only to that environment

Recommendation:

- make shared ingress the default for reusable profiles
- reserve direct webhook mode for dedicated one-to-one Stripe profiles

## Phase 5: Add Medusa Customization For Routing Metadata

Required work:

1. add a Marketi Medusa customization or plugin
2. stamp workspace/environment identifiers into payment metadata
3. ensure the shared ingress can resolve the owning environment deterministically

Do not move forward with one-profile-many-environments in production until this exists.

## Phase 6: Tighten Checkout Provider Selection

Even with one dedicated Medusa environment per workspace, checkout should not trust an unrestricted provider list.

Required behavior:

1. fetch region payment providers from Medusa
2. intersect them with the workspace allowlist
3. auto-select the configured default when appropriate
4. fail cleanly if the configured provider is missing

Implementation areas:

- `mos/backend/app/routers/public_funnels.py`
- `mos/backend/app/services/medusa_store_runtime.py`
- `mos/frontend/src/components/commerce/CommerceBlocks.tsx`
- `mos/frontend/src/types/commerce.ts`

## Phase 7: Move Order Completion To The Medusa Path

For Medusa-backed workspaces:

1. Stripe payment completes through Medusa
2. Medusa order/payment events reach the correct environment
3. MOS ingests the normalized order-complete event
4. MOS records attribution and conversions

This is the retirement path for:

- direct Stripe session creation in MOS
- direct Stripe webhook ownership in MOS

## Phase 8: Retire The Legacy Direct Stripe Path

After validation on:

- one workspace with a dedicated Stripe profile
- two or more workspaces sharing one Stripe profile

then retire the direct Stripe flow for Medusa-backed workspaces.

## Acceptance Criteria

The design is not complete until all of the following are true:

- every workspace has its own Medusa base URL
- workspace A and workspace B can point to the same `stripe_account_profile_id`
- workspace C can point to a different `stripe_account_profile_id`
- checkout in workspace A charges the shared Stripe account correctly
- checkout in workspace B also charges that same shared Stripe account correctly
- webhook processing routes each payment event to the correct Medusa environment
- the solution does not require one Stripe webhook endpoint per Medusa environment as the default reusable-profile path
- checkout UI shows only the configured provider IDs for that workspace
- MOS attribution survives the Medusa order path

## Review Notes

### Strong recommendation

For your clarified topology, keep `client_medusa_configs` as the workspace-level Medusa record.

The earlier environment/binding split is unnecessary for phase 1 if every workspace always gets a dedicated Medusa environment.

### Strong recommendation

The reusable object should be the Stripe account profile, not the Medusa environment.

That is the exact abstraction your requirement needs.

### Strong recommendation

Treat shared webhook ingress as a required design element for reusable Stripe profiles.

Without it, one-account-many-environments becomes operationally fragile and runs into Stripe endpoint-management issues quickly.

## Sources

Official Medusa sources used:

- [Stripe Module Provider](https://docs.medusajs.com/resources/commerce-modules/payment/payment-provider/stripe)
- [Payment Webhook Events](https://docs.medusajs.com/resources/commerce-modules/payment/webhook-events)

Official Stripe sources used:

- [Add a webhook endpoint](https://docs.stripe.com/development/dashboard/webhooks)
- [Receive Stripe events in your webhook endpoint](https://docs.stripe.com/webhooks/test)

Key repo touchpoints reviewed while writing this revision:

- `mos/backend/app/db/models.py`
- `mos/backend/app/services/medusa_connection.py`
- `mos/backend/app/services/medusa_store_runtime.py`
- `mos/backend/app/routers/public_funnels.py`
- `mos/backend/app/routers/stripe_webhooks.py`
- `mos/frontend/src/pages/workspaces/StoreTemplatesPage.tsx`
- `mos/frontend/src/components/commerce/CommerceBlocks.tsx`
