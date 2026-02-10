# mOS Platform Frontend – UI-First Map with API Notes

Primary goal: understand the UI surface area for refactor. Each UI block lists its behavior and then the backend calls it drives.

Style rules: see `docs/ui-style-guide.md` (semantic tokens, dark mode approach, and CI enforcement).
Next standardization work: see `docs/prd-ui-standardization-phase2.md`.

## Global Shell
- **Layout**: `Sidebar` (links to `/tasks`, `/clients`, `/campaigns`, `/library`, `/workflows`), `Header` (derived title + Clerk `UserButton`), `AppShell` wraps all authenticated routes.
- **Auth**: `/sign-in` renders Clerk `<SignIn>`; everything else behind `RequireAuth` (Clerk session check).
- **API client**: `useApiClient` injects Clerk JWT and JSON headers to `VITE_API_BASE_URL` (default `http://localhost:8008`).

## Page-by-Page UI → API

### Tasks page (`/tasks`)
- **UI**: “Needs attention” list of workflows in `running` or `failed` status; `Review` button per item; `View all workflows` CTA.
- **API**: GET `/workflows` (filter client-side for attention items). No mutations; navigation only.

### Clients page (`/clients`)
- **UI**: Page header with “New client” button opening Onboarding Wizard modal; list of clients with per-row `Actions` menu (`Open detail`, `Copy ID`).
- **API**:
  - GET `/clients` to populate list.
  - Onboarding Wizard submit: (a) if no existing client id, POST `/clients` `{ name, industry? }`; (b) POST `/clients/{clientId}/onboarding` with wizard payload; invalidates `workflows`.

### Onboarding Wizard modal (launched from Clients page or Client detail)
- **UI**: 4-step dialog: Basics, Product, Funnel, Review. Required fields: client name (if creating), brand story, product name. Back/Next navigation, Cancel closes and resets, Review is read-only summary. “Start onboarding” submits.
- **API**:
  - POST `/clients` when creating a new client inline.
  - POST `/clients/{clientId}/onboarding` with product fields (name, category, description, benefits, features, guarantee, disclaimers). Server creates the product automatically.

### Client detail (`/clients/:clientId`)
- **UI**: Tabs — Overview (ids/industry), Onboarding (wizard prefilled with name/industry), Workflows (table of runs for this client, read-only).
- **API**:
  - GET `/clients/{clientId}` for header data.
  - GET `/workflows` then client-side filter by `client_id` for the Workflows tab.
  - Onboarding tab uses same wizard calls as above (skips `/clients` POST because id exists).

### Campaigns page (`/campaigns`)
- **UI**: “Create campaign” form (client select + name), list of campaigns with `Start planning` button on each card, status message text.
- **API**:
  - GET `/campaigns` to list.
  - GET `/clients` for the select options.
  - POST `/campaigns` `{ client_id, name }` on create; then re-GET `/campaigns`.
  - POST `/campaigns/{campaignId}/plan` `{ business_goal_id: "goal-" + Date.now() }` when “Start planning” is clicked.

### Campaign detail (`/campaigns/:campaignId`)
- **UI**: Placeholder card showing the id; no interactive controls yet.
- **API**: None currently (display-only placeholder).

### Library (`/library`) → Swipes
- **UI**: Grid of “Company Swipes” cards (title, platforms); empty-state text when none.
- **API**: GET `/swipes/company` on mount. View-only.

### Workflows page (`/workflows`)
- **UI**: Filters (status, kind, client, campaign) stored in URL params; table of workflow runs with status badges; row `Actions` menu (`Open`, `Stop`, `Copy ID`); stop-confirmation dialog; header `Clear filters` and `Refresh` buttons.
- **API**:
  - GET `/workflows` for the table.
  - GET `/clients` for client name lookup in the table.
  - POST `/workflows/{id}/signals/stop` `{}` when confirming Stop; invalidates `workflows`.

### Workflow detail (`/workflows/:workflowId`)
- **UI**: Run overview card, Review & approvals card, research artifacts table (links to Research detail + external doc), strategy sheet (campaign planning only), angle specs, creative briefs, step summaries grid, activity log table. Approvals buttons are enabled only while status is `running`.
- **API**:
  - GET `/workflows/{workflowId}` for run, artifacts, logs, research content.
  - POST `/workflows/{id}/signals/approve-canon` `{ approved: true }` (onboarding).
  - POST `/workflows/{id}/signals/approve-metric-schema` `{ approved: true }` (onboarding).
  - POST `/workflows/{id}/signals/approve-strategy` `{ approved: true }` (campaign planning).
  - Each approval invalidates relevant workflow queries; toasts on result.

### Research detail (`/workflows/:workflowId/research/:stepKey`)
- **UI**: Shows summary and full content for a single research step; `Back` button; `Open doc` external link when available.
- **API**: Reuses GET `/workflows/{workflowId}` data already fetched; no additional calls beyond that detail fetch.

## Endpoint Index (for quick ref while refactoring)
- GET `/clients`
- GET `/clients/{clientId}`
- POST `/clients`
- POST `/clients/{clientId}/onboarding`
- GET `/campaigns`
- POST `/campaigns`
- POST `/campaigns/{campaignId}/plan`
- GET `/swipes/company`
- GET `/workflows`
- GET `/workflows/{workflowId}`
- POST `/workflows/{workflowId}/signals/stop`
- POST `/workflows/{workflowId}/signals/approve-canon`
- POST `/workflows/{workflowId}/signals/approve-metric-schema`
- POST `/workflows/{workflowId}/signals/approve-strategy`
