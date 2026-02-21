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
        "effective_date": "2026-02-19",
        "refund_window_days": "30",
        "fulfillment_window": "2-5 business days",
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
