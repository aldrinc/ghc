import asyncio
import json
from pathlib import Path

from loop.contracts import InteractionCheckpoint, RenderArtifact, RenderTimelineFrame, ViewportSpec

VIDEO_TIMELINE_CAPTURE_DELAYS_MS = [300, 900, 1800, 3200, 5000, 7500]


class HtmlPreviewRenderer:
    def __init__(self, repo_root: Path | None = None):
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._script_path = self._repo_root / "frontend" / "render-html-preview.mjs"
        self._frontend_dir = self._repo_root / "frontend"

    async def render_html(
        self,
        html: str,
        viewport: ViewportSpec,
        interaction_checkpoints: list[InteractionCheckpoint] | None = None,
    ) -> RenderArtifact:
        timeline_plan = self._build_timeline_plan(interaction_checkpoints or [])
        request_payload = json.dumps(
            {
                "html": html,
                "width": viewport.width,
                "height": viewport.height,
                "timelinePlan": timeline_plan,
            }
        ).encode("utf-8")

        process = await asyncio.create_subprocess_exec(
            "node",
            str(self._script_path),
            cwd=str(self._frontend_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(request_payload),
                timeout=45,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError("Timed out while rendering HTML preview") from exc

        if process.returncode != 0:
            raise RuntimeError(
                "Failed to render HTML preview: "
                + stderr.decode("utf-8", errors="replace").strip()
            )

        payload = json.loads(stdout.decode("utf-8"))
        return RenderArtifact(
            viewport_screenshot_data_url=payload["viewportDataUrl"],
            full_page_screenshot_data_url=payload.get("fullPageDataUrl"),
            settled_viewport_screenshot_data_url=payload.get(
                "settledViewportDataUrl"
            ),
            settled_full_page_screenshot_data_url=payload.get(
                "settledFullPageDataUrl"
            ),
            timeline_frames=[
                RenderTimelineFrame(
                    label=frame["label"],
                    elapsed_ms=frame["elapsedMs"],
                    viewport_screenshot_data_url=frame["viewportDataUrl"],
                )
                for frame in payload.get("timelineFrames", [])
                if isinstance(frame, dict)
                and isinstance(frame.get("label"), str)
                and isinstance(frame.get("elapsedMs"), int)
                and isinstance(frame.get("viewportDataUrl"), str)
            ],
            automation_events=[
                event
                for event in payload.get("automationEvents", [])
                if isinstance(event, str)
            ],
            viewport=viewport,
        )

    def _build_timeline_plan(
        self, interaction_checkpoints: list[InteractionCheckpoint]
    ) -> list[dict[str, object]]:
        if not interaction_checkpoints:
            return [
                {"label": "early state", "elapsedMs": 600},
                {"label": "mid sequence", "elapsedMs": 2200},
                {"label": "late sequence", "elapsedMs": 5000},
            ]

        count = min(len(interaction_checkpoints), len(VIDEO_TIMELINE_CAPTURE_DELAYS_MS))
        selected_checkpoints = interaction_checkpoints[:count]
        return [
            {
                "label": checkpoint.name,
                "elapsedMs": VIDEO_TIMELINE_CAPTURE_DELAYS_MS[index],
                "trigger": checkpoint.trigger,
                "expectedResult": checkpoint.expected_result,
                "actionType": checkpoint.action_type,
                "targetDescription": checkpoint.target_description,
            }
            for index, checkpoint in enumerate(selected_checkpoints)
        ]
