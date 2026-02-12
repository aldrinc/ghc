from copy import deepcopy

from fastapi.testclient import TestClient

from app.services.design_system_generation import load_base_tokens_template


def _base_tokens() -> dict:
    return deepcopy(load_base_tokens_template())


def test_first_design_system_sets_client_default(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    first_resp = api_client.post(
        "/design-systems",
        json={"name": "First DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert first_resp.status_code == 201
    first_id = first_resp.json()["id"]

    client_after_first = api_client.get(f"/clients/{client_id}")
    assert client_after_first.status_code == 200
    assert client_after_first.json()["design_system_id"] == first_id

    second_tokens = _base_tokens()
    second_tokens["brand"]["name"] = "Second DS Brand"
    second_resp = api_client.post(
        "/design-systems",
        json={"name": "Second DS", "tokens": second_tokens, "clientId": client_id},
    )
    assert second_resp.status_code == 201

    client_after_second = api_client.get(f"/clients/{client_id}")
    assert client_after_second.status_code == 200
    assert client_after_second.json()["design_system_id"] == first_id


def test_create_design_system_rejects_invalid_text_tokens(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    tokens = _base_tokens()
    tokens["cssVars"]["--color-text"] = "var(--color-brand)"

    resp = api_client.post(
        "/design-systems",
        json={"name": "Invalid DS", "tokens": tokens, "clientId": client_id},
    )
    assert resp.status_code == 422
    assert "--color-text" in (resp.json().get("detail") or "")


def test_update_design_system_rejects_invalid_text_tokens(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    invalid_tokens = _base_tokens()
    invalid_tokens["cssVars"]["--color-muted"] = "#cbd5e1"

    update_resp = api_client.patch(
        f"/design-systems/{design_system_id}",
        json={"tokens": invalid_tokens},
    )
    assert update_resp.status_code == 422
    assert "--color-muted" in (update_resp.json().get("detail") or "")


def test_create_design_system_rejects_locked_layout_tokens(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    tokens = _base_tokens()
    tokens["cssVars"]["--reviews-height"] = "auto"

    resp = api_client.post(
        "/design-systems",
        json={"name": "Invalid DS", "tokens": tokens, "clientId": client_id},
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail") or ""
    assert "template-locked layout tokens" in detail
    assert "--reviews-height" in detail


def test_update_design_system_rejects_locked_layout_tokens(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    create_resp = api_client.post(
        "/design-systems",
        json={"name": "Valid DS", "tokens": _base_tokens(), "clientId": client_id},
    )
    assert create_resp.status_code == 201
    design_system_id = create_resp.json()["id"]

    invalid_tokens = _base_tokens()
    invalid_tokens["cssVars"]["--cta-height-lg"] = "72px"

    update_resp = api_client.patch(
        f"/design-systems/{design_system_id}",
        json={"tokens": invalid_tokens},
    )
    assert update_resp.status_code == 422
    detail = update_resp.json().get("detail") or ""
    assert "template-locked layout tokens" in detail
    assert "--cta-height-lg" in detail
