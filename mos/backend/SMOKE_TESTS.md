# API Smoke Tests (dev)

Run these against the local stack on http://localhost:8008 with a real Clerk dev JWT (copy the `Authorization: Bearer ...` header from the frontend after signing in, or use a dev session token from the Clerk dashboard for your dev instance). The JWT must include `org_id` matching a row in the `orgs` table.

Before running the smoke tests, ensure your database schema is up to date (from the repo root):

```bash
./scripts/migrate-backend-db.sh
```

```bash
export API_BASE=${API_BASE:-http://localhost:8008}
export CLERK_BEARER="paste_dev_jwt_here"
authz=(-H "Authorization: Bearer ${CLERK_BEARER}")
json=(-H "Content-Type: application/json")
```

## Health

```bash
curl -i "${API_BASE}/health"
curl -i "${API_BASE}/health/db"
```

## Clients

```bash
curl -i "${authz[@]}" "${json[@]}" -d '{"name":"CLI Client","industry":"SaaS"}' "${API_BASE}/clients"
curl -i "${authz[@]}" "${API_BASE}/clients"
curl -i "${authz[@]}" "${json[@]}" -d '{}' "${API_BASE}/clients/<client_id>/onboarding"
```

## Campaigns

```bash
curl -i "${authz[@]}" "${json[@]}" -d '{"client_id":"<client_id>","name":"CLI Campaign"}' "${API_BASE}/campaigns"
curl -i "${authz[@]}" "${API_BASE}/campaigns?client_id=<client_id>"
curl -i "${authz[@]}" "${json[@]}" -d '{}' "${API_BASE}/campaigns/<campaign_id>/plan"
```

## Workflows

```bash
curl -i "${authz[@]}" "${API_BASE}/workflows"
curl -i "${authz[@]}" "${API_BASE}/workflows/<workflow_run_id>/logs"
curl -i "${authz[@]}" "${json[@]}" -d '{"approved_ids":["exp-1"],"rejected_ids":[]}' "${API_BASE}/workflows/<workflow_run_id>/signals/approve-experiments"
curl -i "${authz[@]}" "${json[@]}" -d '{"approved_ids":[],"rejected_ids":[]}' "${API_BASE}/workflows/<workflow_run_id>/signals/approve-assets"
```

## Artifacts / Assets / Experiments / Swipes

```bash
curl -i "${authz[@]}" "${API_BASE}/artifacts"
curl -i "${authz[@]}" "${API_BASE}/assets"
curl -i "${authz[@]}" "${API_BASE}/experiments"
curl -i "${authz[@]}" "${API_BASE}/swipes/company"
curl -i "${authz[@]}" "${API_BASE}/swipes/client/<client_id>"
```

Expected: 200 responses with JSON bodies. Workflow signal endpoints return `{"ok": true}`. If you see 401, provide a fresh Clerk dev JWT with an `org_id` that exists in the database. If you see 400/422, ensure IDs exist before sending dependent requests.
