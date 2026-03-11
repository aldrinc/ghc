# Policy Page Templates v1

This catalog is implemented in `mos/backend/app/services/compliance.py` under `_POLICY_TEMPLATES`.

## Template keys

- `privacy_policy`
- `terms_of_service`
- `returns_refunds_policy`
- `shipping_policy`
- `contact_support`

## API access

- `GET /compliance/policy-templates`
- `GET /compliance/policy-templates/{page_key}`

Each template response includes:

- `requiredSections`: section checklist for implementation QA
- `placeholders`: required merge variables to avoid synthetic/fake policy content
- `templateMarkdown`: canonical draft body scaffold

## Required sections by page

### `privacy_policy`

- `owner_identity`
- `data_collected`
- `data_usage`
- `data_sharing`
- `user_choices`
- `security_retention`
- `privacy_contact`
- `policy_updates`

Required placeholders:

- `brand_name`
- `website_url`
- `legal_business_name`
- `support_email`
- `company_address_text`
- `effective_date`
- `privacy_data_collected`
- `privacy_data_usage`
- `privacy_data_sharing`
- `privacy_user_choices`
- `privacy_security_retention`
- `privacy_update_notice`

### `terms_of_service`

- `business_identity`
- `offer_scope`
- `pricing_terms`
- `fulfillment_terms`
- `refund_cancellation_links`
- `disclaimers`
- `dispute_contact`
- `effective_date`

Required placeholders:

- `brand_name`
- `website_url`
- `legal_business_name`
- `company_address_text`
- `support_email`
- `effective_date`
- `terms_offer_scope`
- `terms_eligibility`
- `terms_pricing_billing`
- `terms_fulfillment_access`
- `terms_refund_cancellation`
- `terms_disclaimers`
- `terms_dispute_resolution`
- `terms_governing_law`

### `returns_refunds_policy`

- `eligibility`
- `window`
- `process`
- `method_timing`
- `fees`
- `exceptions`
- `support_contact`

Required placeholders:

- `brand_name`
- `website_url`
- `legal_business_name`
- `support_email`
- `effective_date`
- `refund_eligibility`
- `refund_window_policy`
- `refund_request_steps`
- `refund_method_timing`
- `refund_fees_deductions`
- `refund_exceptions`

### `shipping_policy`

- `coverage`
- `processing_time`
- `options_costs`
- `delivery_estimates`
- `tracking`
- `address_changes`
- `lost_damaged`
- `customs_duties`
- `return_address`
- `support_contact`
- `effective_date`

Required placeholders:

- `brand_name`
- `website_url`
- `support_email`
- `effective_date`
- `shipping_regions`
- `shipping_processing_time`
- `shipping_options_costs`
- `shipping_delivery_estimates`
- `shipping_tracking`
- `shipping_address_changes`
- `shipping_lost_damaged`
- `shipping_customs_duties`
- `shipping_return_address`

### `contact_support`

- `contact_channels`
- `support_hours`
- `business_address`

Required placeholders:

- `support_email`
- `support_phone`
- `support_hours_text`
- `company_address_text`
