from app.config import settings


def test_openai_webhook_uses_api_prefix(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_WEBHOOK_SECRET", "whsec_test")

    response = api_client.post("/api/openai/webhook", content=b"{}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Could not find webhook-signature header"


def test_openai_webhook_without_api_prefix_not_found(api_client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_WEBHOOK_SECRET", "whsec_test")

    response = api_client.post("/openai/webhook", content=b"{}")

    assert response.status_code == 404
