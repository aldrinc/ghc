from __future__ import annotations

import pytest

from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services import embedded_freestyle_image_client as embedded_freestyle
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


def test_build_image_render_client_returns_embedded_freestyle_for_creative_service_provider(monkeypatch) -> None:
    monkeypatch.setattr(image_render.settings, "IMAGE_RENDER_PROVIDER", "creative_service")

    client = image_render.build_image_render_client(org_id="org-123")

    assert isinstance(client, embedded_freestyle.EmbeddedFreestyleImageRenderClient)
    assert client.org_id == "org-123"


def test_embedded_freestyle_rejects_reference_image_urls() -> None:
    client = embedded_freestyle.EmbeddedFreestyleImageRenderClient()

    with pytest.raises(image_render.CreativeServiceRequestError, match="does not accept reference_image_urls"):
        client.create_image_ads(
            payload=CreativeServiceImageAdsCreateIn(
                prompt="Create an ad image",
                count=1,
                reference_image_urls=["https://example.com/reference.png"],
            ),
            idempotency_key="idem-1",
        )


def test_embedded_freestyle_create_image_ads_uses_local_reference_assets(monkeypatch) -> None:
    client = embedded_freestyle.EmbeddedFreestyleImageRenderClient(org_id="org-123")
    captured_prompts: list[str] = []
    uploaded_objects: list[tuple[str, str, bytes, str | None]] = []

    class _FakeStorage:
        bucket = "media-bucket"

        def build_key(self, *, sha256: str, ext: str, kind: str = "orig") -> str:
            assert kind == "orig"
            return f"orig/{sha256}.{ext.lstrip('.')}"

        def object_exists(self, *, bucket: str, key: str) -> bool:
            assert bucket == self.bucket
            return any(existing_key == key for _, existing_key, _, _ in uploaded_objects)

        def upload_bytes(
            self,
            *,
            bucket: str,
            key: str,
            data: bytes,
            content_type: str | None,
            cache_control: str | None = None,
            extra_metadata: dict[str, str] | None = None,
        ) -> None:
            del cache_control, extra_metadata
            uploaded_objects.append((bucket, key, data, content_type))

        def presign_get(self, *, bucket: str, key: str, expires_in: int | None = None) -> str:
            del expires_in
            return f"https://cdn.example/{bucket}/{key}"

    class _FakeNanoBananaClient:
        def __init__(self, config=None) -> None:
            self.config = config

        def generate_image(self, *, prompt: str, reference_images=None, reference_text=None):
            del reference_text
            captured_prompts.append(prompt)
            assert reference_images == [(b"reference-bytes", "image/png")]
            return f"generated-{len(captured_prompts)}".encode("utf-8"), "image/png"

    monkeypatch.setattr(embedded_freestyle, "MediaStorage", _FakeStorage)
    monkeypatch.setattr(embedded_freestyle, "NanoBananaClient", _FakeNanoBananaClient)
    monkeypatch.setattr(
        client,
        "_load_reference_images",
        lambda *, storage, reference_asset_ids: (
            [
                embedded_freestyle.CreativeServiceAssetRef(
                    asset_id="asset-1",
                    position=0,
                    primary_url="https://cdn.example/reference.png",
                )
            ],
            [(b"reference-bytes", "image/png")],
        ),
    )

    job = client.create_image_ads(
        payload=CreativeServiceImageAdsCreateIn(
            prompt="Create an ad image",
            reference_asset_ids=["asset-1"],
            count=2,
            aspect_ratio="1:1",
            model_id="models/gemini-3-pro-image-preview",
        ),
        idempotency_key="idem-embedded-1",
    )

    assert job.status == "succeeded"
    assert job.model_id == "models/gemini-3-pro-image-preview"
    assert [ref.asset_id for ref in job.references] == ["asset-1"]
    assert len(job.outputs) == 2
    assert "Variation 1:" in captured_prompts[0]
    assert "Variation 2:" in captured_prompts[1]
    assert all("Aspect ratio: 1:1." in prompt for prompt in captured_prompts)
    assert len(uploaded_objects) == 2


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
