from __future__ import annotations

import json

import httpx
import pytest

from app.services import testimonial_renderer_client as renderer_client


def test_testimonial_renderer_client_requires_base_url(monkeypatch) -> None:
    monkeypatch.setattr(renderer_client.settings, "TESTIMONIAL_RENDERER_URL", None)

    with pytest.raises(
        renderer_client.TestimonialRendererConfigError,
        match="TESTIMONIAL_RENDERER_URL is required",
    ):
        renderer_client.TestimonialRendererClient()


def test_testimonial_renderer_client_render_png_posts_render_request(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            content=b"png-bytes",
            headers={"content-type": "image/png"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        renderer_client.httpx,
        "Client",
        lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs),
    )

    client = renderer_client.TestimonialRendererClient(
        base_url="https://renderer.example",
        timeout_seconds=5.0,
    )
    payload = {
        "template": "review_card",
        "name": "Taylor",
        "verified": True,
        "rating": 5,
        "review": "Supportive and easy to wear.",
    }

    result = client.render_png(payload=payload)

    assert result == b"png-bytes"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://renderer.example/render?format=png"
    assert captured["body"] == payload


def test_testimonial_renderer_client_render_png_raises_on_http_error(
    monkeypatch,
) -> None:
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            text="imageModel is required",
            headers={"content-type": "text/plain"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        renderer_client.httpx,
        "Client",
        lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs),
    )

    client = renderer_client.TestimonialRendererClient(
        base_url="https://renderer.example",
        timeout_seconds=5.0,
    )

    with pytest.raises(
        renderer_client.TestimonialRendererRequestError,
        match="imageModel is required",
    ):
        client.render_png(
            payload={
                "template": "review_card",
                "name": "Taylor",
                "verified": True,
                "rating": 5,
                "review": "Supportive and easy to wear.",
            }
        )
