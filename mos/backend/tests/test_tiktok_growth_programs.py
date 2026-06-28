from app.services.postiz_client import PostizClient


def _create_client(api_client, *, name: str = "TikTok Growth Test") -> str:
    resp = api_client.post("/clients", json={"name": name, "industry": "Mobile Apps"})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_tiktok_growth_program_variant_approval_and_postiz_handoff_flow(api_client):
    client_id = _create_client(api_client)

    program_resp = api_client.post(
        f"/clients/{client_id}/growth-programs",
        json={
            "name": "Demo App TikTok Loop",
            "objective": "Find TikTok carousel hooks that drive trial starts.",
            "platformKey": "tiktok",
            "formatKey": "tiktok_carousel",
            "authorityMode": "approval_required",
            "settings": {"timezone": "America/Chicago"},
        },
    )
    assert program_resp.status_code == 201
    program = program_resp.json()
    assert program["formatKey"] == "tiktok_carousel"

    conversion_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/conversion-sources",
        json={
            "provider": "custom_webhook",
            "name": "Trial starts",
            "goalEvents": ["trial_started"],
            "config": {"eventKey": "trial_started"},
            "credentialsMetadata": {"mode": "webhook"},
        },
    )
    assert conversion_resp.status_code == 201
    conversion_source = conversion_resp.json()
    assert conversion_source["provider"] == "custom_webhook"

    experiment_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/experiments",
        json={
            "name": "Conflict hook batch",
            "hypothesis": "Person plus conflict hooks will get better qualified reach.",
            "hookFamily": "person_conflict",
            "ctaFamily": "soft_app_name",
            "audience": "mobile app prospects",
        },
    )
    assert experiment_resp.status_code == 201
    experiment = experiment_resp.json()

    slides = [
        {
            "slideIndex": idx,
            "visualRole": "hook" if idx == 1 else "proof",
            "prompt": f"Realistic phone photo for slide {idx}",
            "overlayText": f"Slide {idx}\\nmanual line break",
        }
        for idx in range(1, 7)
    ]
    variant_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/variants",
        json={
            "experimentId": experiment["id"],
            "title": "First carousel",
            "caption": "Story caption with CTA.",
            "cta": "Search DemoApp",
            "slideCount": 6,
            "storyboard": {"hook": "person conflict"},
            "slides": slides,
        },
    )
    assert variant_resp.status_code == 201
    variant = variant_resp.json()
    assert len(variant["slides"]) == 6
    assert variant["status"] == "draft"

    media_urls = [f"https://cdn.example.test/carousel-{idx}.png" for idx in range(1, 7)]

    handoff_before_approval = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/variants/{variant['id']}/postiz-handoff-proposals",
        json={
            "postType": "draft",
            "mediaUrls": media_urls,
        },
    )
    assert handoff_before_approval.status_code == 409

    approve_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/variants/{variant['id']}/approve",
        json={"notes": "Rendered slides approved"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    handoff_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/variants/{variant['id']}/postiz-handoff-proposals",
        json={
            "postType": "draft",
            "channelIds": ["postiz-channel-1"],
            "mediaUrls": media_urls,
            "providerSettingsByIdentifier": {"tiktok": {"privacy": "public"}},
            "metadata": {"operatorIntent": "open_in_postiz"},
        },
    )
    assert handoff_resp.status_code == 201
    handoff = handoff_resp.json()
    assert handoff["actionType"] == "postiz.composer_handoff"
    assert handoff["targetProvider"] == "postiz"
    assert handoff["postizPayload"]["postizOwnership"]["systemOfRecord"] == "postiz"
    assert handoff["postizPayload"]["mediaUrls"] == media_urls

    publication_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/publications",
        json={"variantId": variant["id"]},
    )
    assert publication_resp.status_code == 404

    conversion_event_resp = api_client.post(
        f"/clients/{client_id}/growth-programs/{program['id']}/conversion-events",
        json={
            "conversionSourceId": conversion_source["id"],
            "providerEventId": "evt_trial_1",
            "eventName": "trial_started",
            "occurredAt": "2026-05-22T15:00:00Z",
            "contentVariantId": variant["id"],
            "postizPostId": "postiz-post-123",
            "postizChannelId": "postiz-channel-1",
            "attribution": {"method": "tagged_link", "confidence": "concrete"},
            "rawPayload": {"event": "trial_started"},
            "provenance": "concrete",
        },
    )
    assert conversion_event_resp.status_code == 201
    assert conversion_event_resp.json()["eventName"] == "trial_started"
    assert conversion_event_resp.json()["contentVariantId"] == variant["id"]
    assert conversion_event_resp.json()["postizPostId"] == "postiz-post-123"


class _DummyResponse:
    status_code = 200
    text = "{}"

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _DummyHttpClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        self.calls.append(("GET", url, headers, params, None))
        return _DummyResponse([{"label": "Views", "data": [{"total": "10"}]}])

    def put(self, url, headers=None, json=None):
        self.calls.append(("PUT", url, headers, None, json))
        return _DummyResponse({"ok": True, "releaseId": json["releaseId"]})


def test_postiz_client_exposes_analytics_and_release_reconciliation(monkeypatch):
    from app.services import postiz_client as postiz_module

    _DummyHttpClient.calls = []
    monkeypatch.setattr(postiz_module.httpx, "Client", _DummyHttpClient)

    client = PostizClient(api_key="test-key", base_url="https://postiz.example/api")
    assert client.get_platform_analytics("int_1")[0]["label"] == "Views"
    assert client.get_post_analytics("post_1")[0]["label"] == "Views"
    assert client.list_missing_release_candidates("post_1")[0]["label"] == "Views"
    assert client.attach_release_id("post_1", "release_1")["releaseId"] == "release_1"

    called_urls = [call[1] for call in _DummyHttpClient.calls]
    assert "https://postiz.example/api/public/v1/analytics/int_1" in called_urls
    assert "https://postiz.example/api/public/v1/analytics/post/post_1" in called_urls
    assert "https://postiz.example/api/public/v1/posts/post_1/missing" in called_urls
    assert "https://postiz.example/api/public/v1/posts/post_1/release-id" in called_urls
