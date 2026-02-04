from fastapi.testclient import TestClient


def test_first_design_system_sets_client_default(api_client: TestClient):
    client_resp = api_client.post("/clients", json={"name": "Design System Client", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    first_resp = api_client.post(
        "/design-systems",
        json={"name": "First DS", "tokens": {"dataTheme": "light"}, "clientId": client_id},
    )
    assert first_resp.status_code == 201
    first_id = first_resp.json()["id"]

    client_after_first = api_client.get(f"/clients/{client_id}")
    assert client_after_first.status_code == 200
    assert client_after_first.json()["design_system_id"] == first_id

    second_resp = api_client.post(
        "/design-systems",
        json={"name": "Second DS", "tokens": {"dataTheme": "dark"}, "clientId": client_id},
    )
    assert second_resp.status_code == 201

    client_after_second = api_client.get(f"/clients/{client_id}")
    assert client_after_second.status_code == 200
    assert client_after_second.json()["design_system_id"] == first_id
