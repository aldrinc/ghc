from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import settings
from app.schemas.creative_service import (
    CreativeServiceVideoAttachmentIn,
    CreativeServiceVideoMessageCreateIn,
    CreativeServiceVideoResultOut,
    CreativeServiceVideoSessionCreateIn,
    CreativeServiceVideoTurnOut,
)
from app.services.creative_service_client import CreativeServiceClient


@dataclass
class VideoTurnTrace:
    turn_id: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    status: str
    error_detail: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass
class VideoVariantResult:
    session_id: str
    result: CreativeServiceVideoResultOut
    turns: list[VideoTurnTrace]


class VideoOrchestrationError(RuntimeError):
    def __init__(self, message: str, *, session_id: str | None = None, turns: list[VideoTurnTrace] | None = None) -> None:
        super().__init__(message)
        self.session_id = session_id
        self.turns = turns or []


class VideoAdsOrchestrator:
    def __init__(self, *, client: CreativeServiceClient) -> None:
        self.client = client
        self.poll_interval_seconds = float(settings.CREATIVE_SERVICE_POLL_INTERVAL_SECONDS or 2.0)
        self.poll_timeout_seconds = float(settings.CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS or 300.0)
        self.max_turns = int(settings.CREATIVE_SERVICE_MAX_VIDEO_TURNS or 3)

    def run_variant(
        self,
        *,
        title: str,
        initial_text: str,
        context: dict[str, Any],
        attachments: list[CreativeServiceVideoAttachmentIn] | None,
        session_idempotency_key: str,
        turn_idempotency_prefix: str,
    ) -> VideoVariantResult:
        session = self.client.create_video_session(
            payload=CreativeServiceVideoSessionCreateIn(title=title, kind="freestyle"),
            idempotency_key=session_idempotency_key,
        )
        session_id = session.session_id or ""
        if not session_id:
            raise VideoOrchestrationError("Video session response did not include session_id")

        turns: list[VideoTurnTrace] = []
        message_text = initial_text.strip()

        for attempt in range(1, self.max_turns + 1):
            request_payload = CreativeServiceVideoMessageCreateIn(
                text=message_text,
                attachments=attachments or [],
                context=context,
                client_request_id=f"{turn_idempotency_prefix}-attempt-{attempt}",
            )
            turn = self.client.create_video_message(
                session_id=session_id,
                payload=request_payload,
                idempotency_key=f"{turn_idempotency_prefix}-attempt-{attempt}",
            )
            turn_state = self._wait_for_turn_completion(session_id=session_id, turn_id=turn.turn_id)

            turns.append(
                VideoTurnTrace(
                    turn_id=turn.turn_id,
                    request_payload=request_payload.model_dump(mode="json"),
                    response_payload=turn_state.model_dump(mode="json"),
                    status=turn_state.status,
                    error_detail=turn_state.error_detail,
                    started_at=turn_state.started_at,
                    finished_at=turn_state.finished_at,
                )
            )

            if turn_state.status == "failed":
                raise VideoOrchestrationError(
                    f"Video turn failed (session_id={session_id}, turn_id={turn.turn_id}): "
                    f"{turn_state.error_detail or 'unknown error'}",
                    session_id=session_id,
                    turns=turns,
                )

            if turn_state.status != "completed":
                raise VideoOrchestrationError(
                    f"Video turn ended in unexpected status '{turn_state.status}' "
                    f"(session_id={session_id}, turn_id={turn.turn_id})",
                    session_id=session_id,
                    turns=turns,
                )

            result = self.client.get_video_result(session_id=session_id)
            final_url = None
            if result.final_video and isinstance(result.final_video.primary_url, str):
                final_url = result.final_video.primary_url.strip()
            if final_url:
                return VideoVariantResult(session_id=session_id, result=result, turns=turns)

            if attempt >= self.max_turns:
                raise VideoOrchestrationError(
                    f"Video session {session_id} did not produce final_video.primary_url after {self.max_turns} turns",
                    session_id=session_id,
                    turns=turns,
                )

            message_text = (
                "Your prior response completed without a usable final video URL. "
                "Produce one final ad video and ensure session result includes final_video.primary_url. "
                "Keep the same brief intent and constraints."
            )

        raise VideoOrchestrationError(
            "Video orchestration exhausted turn attempts unexpectedly",
            session_id=session_id,
            turns=turns,
        )

    def _wait_for_turn_completion(self, *, session_id: str, turn_id: str) -> CreativeServiceVideoTurnOut:
        started_monotonic = time.monotonic()
        while True:
            turn = self.client.get_video_turn(session_id=session_id, turn_id=turn_id)
            if turn.status in ("completed", "failed"):
                return turn
            if (time.monotonic() - started_monotonic) > self.poll_timeout_seconds:
                raise VideoOrchestrationError(
                    f"Timed out waiting for video turn completion (session_id={session_id}, turn_id={turn_id}, "
                    f"timeout_seconds={self.poll_timeout_seconds})",
                    session_id=session_id,
                )
            time.sleep(self.poll_interval_seconds)


def build_initial_video_message(
    *,
    creative_concept: str,
    channel_id: str,
    requirement: dict[str, Any],
    constraints: list[str],
    tone_guidelines: list[str],
    visual_guidelines: list[str],
    product_asset_urls: list[str],
) -> str:
    lines: list[str] = [
        "Generate one conversion-focused paid social ad video concept and render.",
        f"Creative concept: {creative_concept.strip()}",
        f"Channel: {channel_id.strip()}",
        "Format: video.",
    ]

    angle = requirement.get("angle")
    if isinstance(angle, str) and angle.strip():
        lines.append(f"Angle: {angle.strip()}")
    hook = requirement.get("hook")
    if isinstance(hook, str) and hook.strip():
        lines.append(f"Hook: {hook.strip()}")

    if constraints:
        lines.append(f"Constraints: {constraints}")
    if tone_guidelines:
        lines.append(f"Tone guidelines: {tone_guidelines}")
    if visual_guidelines:
        lines.append(f"Visual guidelines: {visual_guidelines}")
    if product_asset_urls:
        lines.append(
            "Use the attached product reference assets as the canonical product visuals. "
            "Do not invent product form factors."
        )

    lines.append(
        "Return a final produced video and include final_video.primary_url in the result payload."
    )
    return "\n".join(lines)
