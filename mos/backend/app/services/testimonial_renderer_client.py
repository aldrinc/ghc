from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


class TestimonialRendererConfigError(RuntimeError):
    pass


@dataclass
class TestimonialRendererRequestError(RuntimeError):
    message: str
    status_code: int | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.message}{status}".strip()


class TestimonialRendererClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        resolved_base_url = (base_url or settings.TESTIMONIAL_RENDERER_URL or "").strip()
        if not resolved_base_url:
            raise TestimonialRendererConfigError(
                "TESTIMONIAL_RENDERER_URL is required for Shopify testimonial image generation."
            )
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)

    def render_png(self, *, payload: dict[str, Any]) -> bytes:
        if not isinstance(payload, dict) or not payload:
            raise TestimonialRendererRequestError(
                "Testimonial renderer payload must be a non-empty JSON object."
            )

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.post(
                    "/render",
                    params={"format": "png"},
                    json=payload,
                    headers={"Accept": "image/png"},
                )
        except httpx.HTTPError as exc:
            raise TestimonialRendererRequestError(
                "Testimonial renderer request failed.",
                details={"base_url": self.base_url, "error": str(exc)},
            ) from None

        if response.status_code >= 400:
            detail = response.text.strip() or "Unknown testimonial renderer error."
            raise TestimonialRendererRequestError(
                f"Testimonial renderer rejected the request: {detail}",
                status_code=response.status_code,
            )

        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type and content_type != "image/png":
            raise TestimonialRendererRequestError(
                "Testimonial renderer returned an unexpected content type.",
                status_code=response.status_code,
                details={"content_type": content_type},
            )

        body = response.content
        if not body:
            raise TestimonialRendererRequestError(
                "Testimonial renderer returned an empty response body.",
                status_code=response.status_code,
            )
        return body
