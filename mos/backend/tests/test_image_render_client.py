from __future__ import annotations

import pytest

from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services import image_render_client as image_render


def test_get_image_render_provider_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setattr(image_render.settings, "IMAGE_RENDER_PROVIDER", "invalid_provider")
    monkeypatch.delenv("SWIPE_IMAGE_RENDER_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_RENDER_MODEL", raising=False)

    with pytest.raises(ValueError, match="Unsupported IMAGE_RENDER_PROVIDER"):
        image_render.get_image_render_provider()


def test_get_image_render_provider_uses_creative_service_for_gemini_models(monkeypatch) -> None:
    monkeypatch.setattr(image_render.settings, "IMAGE_RENDER_PROVIDER", "higgsfield")

    assert image_render.get_image_render_provider(model_id="gemini-3.1-flash-image-preview") == "creative_service"
    assert image_render.get_image_render_provider(model_id="models/gemini-3-pro-image-preview") == "creative_service"


def test_get_image_render_provider_uses_higgsfield_for_nano_banana_models(monkeypatch) -> None:
    monkeypatch.setattr(image_render.settings, "IMAGE_RENDER_PROVIDER", "creative_service")

    assert image_render.get_image_render_provider(model_id="nano-banana-pro") == "higgsfield"


def test_higgsfield_create_image_ads_uses_model_defaults(monkeypatch) -> None:
    client = image_render.HiggsfieldImageRenderClient(
        base_url="https://platform.higgsfield.ai",
        hf_key="hf-test-key",
        default_model="nano-banana-pro",
        default_resolution="1k",
    )

    responses = iter(
        [
            {"request_id": "req-1"},
            {"request_id": "req-2"},
        ]
    )
    captured_requests: list[tuple[str, str, dict[str, object] | None]] = []

    def _fake_request_json(
        method: str,
        path: str,
        *,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        captured_requests.append((method, path, json_payload))
        return next(responses)

    monkeypatch.setattr(client, "_request_json", _fake_request_json)

    payload = CreativeServiceImageAdsCreateIn(
        prompt="Create an ad image",
        count=2,
        aspect_ratio="1:1",
    )
    job = client.create_image_ads(payload=payload, idempotency_key="idem-1")

    assert job.id.startswith("higgsfield:")
    assert job.status == "queued"
    assert job.model_id == "nano-banana-pro"
    assert job.count == 2
    assert len(captured_requests) == 2
    assert captured_requests[0][0] == "POST"
    assert captured_requests[0][1] == "/nano-banana-pro"
    assert captured_requests[0][2] == {
        "prompt": "Create an ad image",
        "aspect_ratio": "1:1",
        "resolution": "1k",
    }


def test_higgsfield_get_image_ads_job_maps_completed_status(monkeypatch) -> None:
    client = image_render.HiggsfieldImageRenderClient(
        base_url="https://platform.higgsfield.ai",
        hf_key="hf-test-key",
        default_model="nano-banana-pro",
    )
    job_id = image_render._encode_higgs_job_state(
        model_id="nano-banana-pro",
        prompt="Prompt",
        count=2,
        aspect_ratio="1:1",
        request_ids=["req-1", "req-2"],
    )

    def _fake_request_json(
        method: str,
        path: str,
        *,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "GET"
        assert json_payload is None
        if path == "/requests/req-1/status":
            return {"status": "completed", "images": [{"url": "https://img.example/1.png"}]}
        if path == "/requests/req-2/status":
            return {
                "status": "completed",
                "images": [
                    {"url": "https://img.example/2.png"},
                    {"url": "https://img.example/3.png"},
                ],
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(client, "_request_json", _fake_request_json)

    job = client.get_image_ads_job(job_id=job_id)

    assert job.status == "succeeded"
    assert [asset.primary_url for asset in job.outputs] == [
        "https://img.example/1.png",
        "https://img.example/2.png",
        "https://img.example/3.png",
    ]
    assert job.outputs[0].asset_id == "higgsfield:req-1:0"
    assert job.outputs[1].asset_id == "higgsfield:req-2:0"
    assert job.outputs[2].asset_id == "higgsfield:req-2:1"


def test_higgsfield_get_image_ads_job_maps_failed_status(monkeypatch) -> None:
    client = image_render.HiggsfieldImageRenderClient(
        base_url="https://platform.higgsfield.ai",
        hf_key="hf-test-key",
        default_model="nano-banana-pro",
    )
    job_id = image_render._encode_higgs_job_state(
        model_id="nano-banana-pro",
        prompt="Prompt",
        count=2,
        aspect_ratio="1:1",
        request_ids=["req-1", "req-2"],
    )

    def _fake_request_json(
        method: str,
        path: str,
        *,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "GET"
        assert json_payload is None
        if path == "/requests/req-1/status":
            return {"status": "completed", "images": [{"url": "https://img.example/1.png"}]}
        if path == "/requests/req-2/status":
            return {"status": "failed", "detail": "generation failed"}
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(client, "_request_json", _fake_request_json)

    job = client.get_image_ads_job(job_id=job_id)

    assert job.status == "failed"
    assert job.error_detail == "generation failed"
    assert [asset.primary_url for asset in job.outputs] == ["https://img.example/1.png"]


def test_higgsfield_create_image_ads_uploads_and_attaches_reference_image(monkeypatch) -> None:
    client = image_render.HiggsfieldImageRenderClient(
        base_url="https://platform.higgsfield.ai",
        hf_key="hf-test-key",
        default_model="nano-banana-pro",
        default_resolution="1k",
    )

    captured_requests: list[tuple[str, str, dict[str, object] | None]] = []

    def _fake_request_json(
        method: str,
        path: str,
        *,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        captured_requests.append((method, path, json_payload))
        assert method == "POST"
        assert path == "/nano-banana-pro"
        return {"request_id": "req-1"}

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    monkeypatch.setattr(
        client,
        "_prepare_reference_image_urls",
        lambda **kwargs: ["https://cdn.higgsfield.ai/uploads/product-ref-1.png"],
    )

    payload = CreativeServiceImageAdsCreateIn(
        prompt="Create an ad image",
        count=1,
        aspect_ratio="1:1",
        reference_image_urls=["https://example.com/product-reference.png"],
    )

    job = client.create_image_ads(payload=payload, idempotency_key="idem-1")

    assert job.status == "queued"
    assert len(job.references) == 1
    assert job.references[0].primary_url == "https://cdn.higgsfield.ai/uploads/product-ref-1.png"
    assert captured_requests[0][2] == {
        "prompt": "Create an ad image",
        "input_images": [
            {
                "type": "image_url",
                "image_url": "https://cdn.higgsfield.ai/uploads/product-ref-1.png",
            }
        ],
        "aspect_ratio": "1:1",
        "resolution": "1k",
    }


def test_higgsfield_create_image_ads_uses_image_url_reference_for_non_nano_models(monkeypatch) -> None:
    client = image_render.HiggsfieldImageRenderClient(
        base_url="https://platform.higgsfield.ai",
        hf_key="hf-test-key",
        default_model="seedream_v5_lite",
        default_resolution="1k",
    )

    captured_requests: list[tuple[str, str, dict[str, object] | None]] = []

    def _fake_request_json(
        method: str,
        path: str,
        *,
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        captured_requests.append((method, path, json_payload))
        assert method == "POST"
        assert path == "/seedream_v5_lite"
        return {"request_id": "req-1"}

    monkeypatch.setattr(client, "_request_json", _fake_request_json)
    monkeypatch.setattr(
        client,
        "_prepare_reference_image_urls",
        lambda **kwargs: ["https://cdn.higgsfield.ai/uploads/product-ref-1.png"],
    )

    payload = CreativeServiceImageAdsCreateIn(
        prompt="Create an ad image",
        count=1,
        aspect_ratio="1:1",
        reference_image_urls=["https://example.com/product-reference.png"],
    )

    job = client.create_image_ads(payload=payload, idempotency_key="idem-1")

    assert job.status == "queued"
    assert len(job.references) == 1
    assert job.references[0].primary_url == "https://cdn.higgsfield.ai/uploads/product-ref-1.png"
    assert captured_requests[0][2] == {
        "prompt": "Create an ad image",
        "image_url": "https://cdn.higgsfield.ai/uploads/product-ref-1.png",
        "aspect_ratio": "1:1",
        "resolution": "1k",
    }
