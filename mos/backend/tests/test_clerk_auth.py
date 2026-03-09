from app.auth import clerk as clerk_auth


def test_audience_claim_allows_private_lan_dev_origin(monkeypatch):
    monkeypatch.setattr(clerk_auth.settings, "ENVIRONMENT", "development")

    assert clerk_auth._audience_claim_allowed(
        None,
        "http://10.1.10.190:5275",
        ["http://localhost:5173", "http://localhost:5275", "backend"],
    )


def test_audience_claim_rejects_private_lan_non_dev_port(monkeypatch):
    monkeypatch.setattr(clerk_auth.settings, "ENVIRONMENT", "development")

    assert not clerk_auth._audience_claim_allowed(
        None,
        "http://10.1.10.190:8008",
        ["http://localhost:5173", "http://localhost:5275", "backend"],
    )


def test_audience_claim_allows_netbird_shared_address_space(monkeypatch):
    monkeypatch.setattr(clerk_auth.settings, "ENVIRONMENT", "development")

    assert clerk_auth._audience_claim_allowed(
        None,
        "http://100.79.158.197:5275",
        ["http://localhost:5173", "http://localhost:5275", "backend"],
    )


def test_audience_claim_rejects_private_lan_origin_outside_development(monkeypatch):
    monkeypatch.setattr(clerk_auth.settings, "ENVIRONMENT", "production")

    assert not clerk_auth._audience_claim_allowed(
        None,
        "http://10.1.10.190:5275",
        ["http://localhost:5173", "http://localhost:5275", "backend"],
    )
