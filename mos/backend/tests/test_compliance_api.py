from app.services.compliance import RULESET_VERSION
from app.routers import compliance as compliance_router


def _create_client(api_client, *, name: str = "Compliance Workspace") -> str:
    response = api_client.post("/clients", json={"name": name, "industry": "Retail"})
    assert response.status_code == 201
    return response.json()["id"]


def _base_profile_payload() -> dict:
    return {
        "rulesetVersion": RULESET_VERSION,
        "businessModels": ["ecommerce"],
        "legalBusinessName": "Acme Labs LLC",
        "operatingEntityName": "Acme Labs LLC",
        "companyAddressText": "123 Main St, Austin, TX 78701",
        "businessLicenseIdentifier": "TX-12345",
        "supportEmail": "support@acme.test",
        "supportPhone": "+1-555-111-2222",
        "supportHoursText": "Mon-Fri 9:00-17:00 CT",
        "responseTimeCommitment": "Within 1 business day",
        "privacyPolicyUrl": "https://acme.test/privacy",
        "termsOfServiceUrl": "https://acme.test/terms",
        "returnsRefundsPolicyUrl": "https://acme.test/refunds",
        "shippingPolicyUrl": "https://acme.test/shipping",
        "contactSupportUrl": "https://acme.test/contact",
        "companyInformationUrl": "https://acme.test/company",
        "subscriptionTermsAndCancellationUrl": "https://acme.test/subscription",
        "metadata": {"owner": "ops"},
    }


def _sync_ready_profile_payload() -> dict:
    payload = _base_profile_payload()
    payload["metadata"] = {
        "owner": "ops",
        "effective_date": "2026-02-27",
        "brand_name": "Acme Labs",
        "privacy_data_collected": (
            "We collect contact, checkout, account, support, and device data including analytics/pixel events."
        ),
        "privacy_data_usage": (
            "We use data for fulfillment, customer support, billing, fraud prevention, analytics, and marketing opt-ins."
        ),
        "privacy_data_sharing": (
            "We share data with payment, shipping, analytics, and messaging vendors needed to operate the service."
        ),
        "privacy_user_choices": (
            "Users can unsubscribe from marketing and request access, correction, or deletion through support."
        ),
        "privacy_security_retention": (
            "We apply reasonable administrative and technical safeguards and retain data only as needed for business/legal use."
        ),
        "privacy_update_notice": "We post updates on this page and revise the effective date when material changes occur.",
        "terms_offer_scope": "We provide physical products, digital content, and related support as described on each product page.",
        "terms_eligibility": "Customers must provide accurate payment and delivery details and comply with applicable laws.",
        "terms_pricing_billing": (
            "Prices are shown in local currency where available and include all disclosed fees before checkout."
        ),
        "terms_fulfillment_access": (
            "Physical goods ship after processing; digital access is provided after payment confirmation."
        ),
        "terms_refund_cancellation": (
            "Refund and cancellation rights are described in our Returns and Refunds Policy and Subscription Terms pages."
        ),
        "terms_disclaimers": "Availability, delivery timelines, and promotional terms are subject to stated conditions.",
        "refund_eligibility": (
            "Eligible requests require order details and compliance with item condition requirements where applicable."
        ),
        "refund_window_policy": "Refund requests must be submitted within 30 days of delivery or purchase date.",
        "refund_request_steps": "Contact support with order number, reason, and evidence if requested.",
        "refund_method_timing": "Approved refunds are issued to original payment method within 5-10 business days.",
        "refund_fees_deductions": "Return shipping or restocking deductions, if any, are disclosed before return approval.",
        "refund_exceptions": "Final-sale, custom, and abuse-related transactions are non-refundable unless required by law.",
        "shipping_regions": "We ship within the United States and selected international destinations.",
        "shipping_processing_time": "Orders are processed within 1-2 business days.",
        "shipping_options_costs": "Shipping options and costs are shown at checkout before payment.",
        "shipping_delivery_estimates": "Standard delivery estimates are 2-7 business days after dispatch.",
        "shipping_tracking": "Tracking links are sent after dispatch and displayed in order status communications.",
        "shipping_address_changes": "Address updates are available before fulfillment lock-in; contact support immediately.",
        "shipping_lost_damaged": "Report lost or damaged packages to support for carrier claim and replacement/refund review.",
        "shipping_customs_duties": "International customs and import duties are the buyer's responsibility unless stated otherwise.",
        "shipping_return_address": "Returns are sent to the address provided by support during return authorization.",
        "support_order_help_links": (
            "Track Order: /order-status | Returns: /refunds | Subscription Cancel: /subscription-terms"
        ),
        "subscription_included_features": "Each plan includes account access, product updates, and support per plan limits.",
        "subscription_plan_table": "- Monthly Plan: $29/month\n- Annual Plan: $299/year",
        "subscription_auto_renew_terms": "Plans auto-renew at the listed interval until canceled.",
        "subscription_trial_terms": "If a trial is offered, billing begins automatically at trial end unless canceled first.",
        "subscription_explicit_consent": (
            "Checkout requires explicit consent acknowledging recurring charges before order completion."
        ),
        "cancellation_steps": "1. Open account settings\n2. Select billing\n3. Click cancel subscription",
        "subscription_refund_rules": "Subscription refunds and prorations follow plan-specific policy terms disclosed before purchase.",
        "subscription_billing_support": "Billing support is available at support@acme.test.",
    }
    return payload


def _shopify_sync_response_pages(*, pages: list[dict], shop_domain: str = "example.myshopify.com") -> list[dict]:
    response_pages: list[dict] = []
    for idx, page in enumerate(pages, start=101):
        response_pages.append(
            {
                "pageKey": page["pageKey"],
                "pageId": f"gid://shopify/Page/{idx}",
                "title": page["title"],
                "handle": page["handle"],
                "url": f"https://{shop_domain}/pages/{page['handle']}",
                "operation": "created" if idx == 101 else "updated",
            }
        )
    return response_pages


def test_list_compliance_rulesets(api_client):
    response = api_client.get("/compliance/rulesets")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["version"] == RULESET_VERSION
    assert payload[0]["ruleCount"] > 0


def test_get_compliance_ruleset(api_client):
    response = api_client.get(f"/compliance/rulesets/{RULESET_VERSION}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == RULESET_VERSION
    assert len(payload["sources"]) >= 1
    assert len(payload["rules"]) >= 1


def test_upsert_and_get_client_compliance_profile(api_client):
    client_id = _create_client(api_client)

    payload = _base_profile_payload()
    put_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=payload)

    assert put_response.status_code == 200
    put_json = put_response.json()
    assert put_json["clientId"] == client_id
    assert put_json["rulesetVersion"] == RULESET_VERSION
    assert put_json["businessModels"] == ["ecommerce"]

    get_response = api_client.get(f"/clients/{client_id}/compliance/profile")
    assert get_response.status_code == 200
    get_json = get_response.json()
    assert get_json["id"] == put_json["id"]
    assert get_json["supportEmail"] == "support@acme.test"


def test_compliance_requirements_show_missing_required_pages(api_client):
    client_id = _create_client(api_client)

    payload = _base_profile_payload()
    payload["termsOfServiceUrl"] = None
    payload["returnsRefundsPolicyUrl"] = None
    payload["shippingPolicyUrl"] = None
    payload["contactSupportUrl"] = None
    payload["companyInformationUrl"] = None
    upsert_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=payload)
    assert upsert_response.status_code == 200

    requirements_response = api_client.get(f"/clients/{client_id}/compliance/requirements")
    assert requirements_response.status_code == 200
    requirements = requirements_response.json()

    assert requirements["rulesetVersion"] == RULESET_VERSION
    assert requirements["businessModels"] == ["ecommerce"]

    missing_required = set(requirements["missingRequiredPageKeys"])
    assert "terms_of_service" in missing_required
    assert "returns_refunds_policy" in missing_required
    assert "shipping_policy" in missing_required
    assert "contact_support" in missing_required
    assert "company_information" in missing_required


def test_put_compliance_profile_rejects_invalid_ruleset_version(api_client):
    client_id = _create_client(api_client)

    payload = _base_profile_payload()
    payload["rulesetVersion"] = "meta_tiktok_compliance_ruleset_v999"

    response = api_client.put(f"/clients/{client_id}/compliance/profile", json=payload)
    assert response.status_code == 400
    assert "Unsupported rulesetVersion" in response.json()["detail"]


def test_list_policy_templates(api_client):
    response = api_client.get("/compliance/policy-templates")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    privacy = next((item for item in payload if item["pageKey"] == "privacy_policy"), None)
    assert privacy is not None
    assert len(privacy["requiredSections"]) >= 1
    assert "templateMarkdown" in privacy


def test_sync_compliance_policy_pages_to_shopify_updates_profile_urls(api_client, monkeypatch):
    client_id = _create_client(api_client)
    profile_payload = _sync_ready_profile_payload()
    upsert_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=profile_payload)
    assert upsert_response.status_code == 200

    observed: dict[str, object] = {}

    def fake_sync(*, client_id: str, pages: list[dict], shop_domain: str | None):
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["page_keys"] = [page["pageKey"] for page in pages]
        return {
            "shopDomain": "example.myshopify.com",
            "pages": [
                {
                    "pageKey": "privacy_policy",
                    "pageId": "gid://shopify/Page/101",
                    "title": "Privacy Policy",
                    "handle": "privacy-policy",
                    "url": "https://example.myshopify.com/pages/privacy-policy",
                    "operation": "created",
                },
                {
                    "pageKey": "terms_of_service",
                    "pageId": "gid://shopify/Page/102",
                    "title": "Terms of Service",
                    "handle": "terms-of-service",
                    "url": "https://example.myshopify.com/pages/terms-of-service",
                    "operation": "updated",
                },
                {
                    "pageKey": "returns_refunds_policy",
                    "pageId": "gid://shopify/Page/103",
                    "title": "Returns and Refunds Policy",
                    "handle": "returns-refunds-policy",
                    "url": "https://example.myshopify.com/pages/returns-refunds-policy",
                    "operation": "updated",
                },
                {
                    "pageKey": "shipping_policy",
                    "pageId": "gid://shopify/Page/104",
                    "title": "Shipping Policy",
                    "handle": "shipping-policy",
                    "url": "https://example.myshopify.com/pages/shipping-policy",
                    "operation": "updated",
                },
                {
                    "pageKey": "contact_support",
                    "pageId": "gid://shopify/Page/105",
                    "title": "Contact and Support",
                    "handle": "contact-support",
                    "url": "https://example.myshopify.com/pages/contact-support",
                    "operation": "updated",
                },
                {
                    "pageKey": "company_information",
                    "pageId": "gid://shopify/Page/106",
                    "title": "Company Information",
                    "handle": "company-information",
                    "url": "https://example.myshopify.com/pages/company-information",
                    "operation": "updated",
                },
            ],
        }

    monkeypatch.setattr(compliance_router, "upsert_client_shopify_policy_pages", fake_sync)

    sync_response = api_client.post(
        f"/clients/{client_id}/compliance/shopify/policy-pages/sync",
        json={},
    )
    assert sync_response.status_code == 200

    body = sync_response.json()
    assert body["shopDomain"] == "example.myshopify.com"
    assert len(body["pages"]) == 6
    assert observed["client_id"] == client_id
    assert observed["shop_domain"] is None
    assert set(observed["page_keys"]) == {
        "privacy_policy",
        "terms_of_service",
        "returns_refunds_policy",
        "shipping_policy",
        "contact_support",
        "company_information",
    }

    profile_response = api_client.get(f"/clients/{client_id}/compliance/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["privacyPolicyUrl"] == "https://example.myshopify.com/pages/privacy-policy"
    assert profile["termsOfServiceUrl"] == "https://example.myshopify.com/pages/terms-of-service"
    assert profile["returnsRefundsPolicyUrl"] == "https://example.myshopify.com/pages/returns-refunds-policy"
    assert profile["shippingPolicyUrl"] == "https://example.myshopify.com/pages/shipping-policy"
    assert profile["contactSupportUrl"] == "https://example.myshopify.com/pages/contact-support"
    assert profile["companyInformationUrl"] == "https://example.myshopify.com/pages/company-information"


def test_sync_compliance_policy_pages_requires_placeholder_values(api_client):
    client_id = _create_client(api_client)
    profile_payload = _base_profile_payload()
    upsert_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=profile_payload)
    assert upsert_response.status_code == 200

    sync_response = api_client.post(
        f"/clients/{client_id}/compliance/shopify/policy-pages/sync",
        json={"pageKeys": ["privacy_policy"]},
    )
    assert sync_response.status_code == 400
    assert "Missing placeholder values" in sync_response.json()["detail"]


def test_sync_compliance_policy_pages_requires_existing_profile(api_client):
    client_id = _create_client(api_client)

    sync_response = api_client.post(
        f"/clients/{client_id}/compliance/shopify/policy-pages/sync",
        json={},
    )

    assert sync_response.status_code == 404
    detail = sync_response.json()["detail"]
    assert detail.startswith("Compliance profile not found for this client.")
    assert f"PUT /clients/{client_id}/compliance/profile" in detail


def test_sync_compliance_policy_pages_for_subscription_model(api_client, monkeypatch):
    client_id = _create_client(api_client, name="SaaS Compliance Workspace")
    profile_payload = _sync_ready_profile_payload()
    profile_payload["businessModels"] = ["saas_subscription"]
    profile_payload["shippingPolicyUrl"] = None
    profile_payload["metadata"]["subscription_plan_table"] = "- Starter: $29/month\n- Pro: $79/month"
    profile_payload["metadata"]["cancellation_steps"] = "1. Go to Billing Settings\n2. Click Cancel Subscription"
    upsert_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=profile_payload)
    assert upsert_response.status_code == 200

    observed: dict[str, object] = {}

    def fake_sync(*, client_id: str, pages: list[dict], shop_domain: str | None):
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["page_keys"] = [page["pageKey"] for page in pages]
        return {
            "shopDomain": "example.myshopify.com",
            "pages": _shopify_sync_response_pages(pages=pages),
        }

    monkeypatch.setattr(compliance_router, "upsert_client_shopify_policy_pages", fake_sync)

    sync_response = api_client.post(
        f"/clients/{client_id}/compliance/shopify/policy-pages/sync",
        json={},
    )
    assert sync_response.status_code == 200
    body = sync_response.json()
    assert body["shopDomain"] == "example.myshopify.com"
    assert observed["client_id"] == client_id
    assert observed["shop_domain"] is None
    assert set(observed["page_keys"]) == {
        "privacy_policy",
        "terms_of_service",
        "returns_refunds_policy",
        "contact_support",
        "company_information",
        "subscription_terms_and_cancellation",
    }
    assert "shipping_policy" not in set(observed["page_keys"])

    profile_response = api_client.get(f"/clients/{client_id}/compliance/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["shippingPolicyUrl"] is None
    assert profile["subscriptionTermsAndCancellationUrl"] == (
        "https://example.myshopify.com/pages/subscription-terms-and-cancellation"
    )
    assert profile["contactSupportUrl"] == "https://example.myshopify.com/pages/contact-support"
    assert profile["returnsRefundsPolicyUrl"] == "https://example.myshopify.com/pages/returns-refunds-policy"


def test_sync_compliance_policy_pages_for_ecommerce_and_subscription_includes_all_targets(api_client, monkeypatch):
    client_id = _create_client(api_client, name="Hybrid Compliance Workspace")
    profile_payload = _sync_ready_profile_payload()
    profile_payload["businessModels"] = ["ecommerce", "saas_subscription"]
    profile_payload["metadata"]["subscription_plan_table"] = "- Monthly: $19\n- Annual: $190"
    profile_payload["metadata"]["cancellation_steps"] = "1. Open Account\n2. Select Billing\n3. Choose Cancel"
    upsert_response = api_client.put(f"/clients/{client_id}/compliance/profile", json=profile_payload)
    assert upsert_response.status_code == 200

    observed: dict[str, object] = {}

    def fake_sync(*, client_id: str, pages: list[dict], shop_domain: str | None):
        observed["client_id"] = client_id
        observed["shop_domain"] = shop_domain
        observed["page_keys"] = [page["pageKey"] for page in pages]
        return {
            "shopDomain": "example.myshopify.com",
            "pages": _shopify_sync_response_pages(pages=pages),
        }

    monkeypatch.setattr(compliance_router, "upsert_client_shopify_policy_pages", fake_sync)

    sync_response = api_client.post(
        f"/clients/{client_id}/compliance/shopify/policy-pages/sync",
        json={},
    )
    assert sync_response.status_code == 200
    assert observed["client_id"] == client_id
    assert observed["shop_domain"] is None
    assert set(observed["page_keys"]) == {
        "privacy_policy",
        "terms_of_service",
        "returns_refunds_policy",
        "shipping_policy",
        "contact_support",
        "company_information",
        "subscription_terms_and_cancellation",
    }
