# Policy Page Templates v1

This catalog is implemented in `mos/backend/app/services/compliance.py` under `_POLICY_TEMPLATES`.

## Template keys

- `privacy_policy`
- `terms_of_service`
- `returns_refunds_policy`
- `shipping_policy`
- `contact_support`
- `company_information`
- `subscription_terms_and_cancellation`

## API access

- `GET /compliance/policy-templates`
- `GET /compliance/policy-templates/{page_key}`

Each template response includes:

- `requiredSections`: section checklist for implementation QA
- `placeholders`: required merge variables to avoid synthetic/fake policy content
- `templateMarkdown`: canonical draft body scaffold
