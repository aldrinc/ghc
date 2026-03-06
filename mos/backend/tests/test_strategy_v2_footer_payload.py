from contextlib import contextmanager
from types import SimpleNamespace

from app.temporal.activities import strategy_v2_activities


def test_build_policy_footer_links_returns_links_and_brand_name(monkeypatch):
    profile = SimpleNamespace(
        privacy_policy_url="https://example.com/privacy",
        terms_of_service_url="https://example.com/terms",
        returns_refunds_policy_url="https://example.com/returns",
        shipping_policy_url="https://example.com/shipping",
        subscription_terms_and_cancellation_url="https://example.com/subscription",
        operating_entity_name="Fallback Entity",
        legal_business_name="Fallback Legal",
        client_id="client-123",
    )
    design_system = SimpleNamespace(tokens={"brand": {"name": "The Honest Herbalist"}})

    @contextmanager
    def _session_scope_override():
        yield object()

    class _ComplianceRepo:
        def __init__(self, _session):
            pass

        def get(self, *, org_id, client_id):
            assert org_id == "org-123"
            assert client_id == "client-123"
            return profile

    class _DesignRepo:
        def __init__(self, _session):
            pass

        def list(self, *, org_id, client_id):
            assert org_id == "org-123"
            assert client_id == "client-123"
            return [design_system]

    monkeypatch.setattr(strategy_v2_activities, "session_scope", _session_scope_override)
    monkeypatch.setattr(strategy_v2_activities, "ClientComplianceProfilesRepository", _ComplianceRepo)
    monkeypatch.setattr(strategy_v2_activities, "DesignSystemsRepository", _DesignRepo)

    links, brand_name = strategy_v2_activities._build_policy_footer_links(
        org_id="org-123",
        client_id="client-123",
    )

    assert links == [
        {"label": "Privacy", "href": "https://example.com/privacy"},
        {"label": "Terms", "href": "https://example.com/terms"},
        {"label": "Returns", "href": "https://example.com/returns"},
        {"label": "Shipping", "href": "https://example.com/shipping"},
        {"label": "Subscription", "href": "https://example.com/subscription"},
    ]
    assert brand_name == "The Honest Herbalist"
