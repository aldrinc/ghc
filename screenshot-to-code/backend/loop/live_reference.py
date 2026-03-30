import asyncio
import json
from pathlib import Path
from typing import Any, cast

from loop.contracts import (
    LiveReferenceContext,
    LiveReferenceDesignSystem,
    LiveReferenceRender,
    ViewportSpec,
)


class LiveReferenceExtractor:
    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._script_path = self._repo_root / "frontend" / "extract-live-reference.mjs"
        self._frontend_dir = self._repo_root / "frontend"

    async def extract(self, *, url: str, viewport: ViewportSpec) -> LiveReferenceContext:
        request_payload = json.dumps(
            {
                "url": url,
                "width": viewport.width,
                "height": viewport.height,
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
                timeout=75,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"Timed out while inspecting live reference URL: {url}"
            ) from exc

        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip() or "unknown error"
            raise RuntimeError(
                f"Failed to inspect live reference URL {url}: {detail}"
            )

        try:
            payload = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Live reference inspection returned invalid JSON for {url}"
            ) from exc

        renders = []
        raw_renders = payload.get("renders", [])
        if not isinstance(raw_renders, list):
            raw_renders = []

        for render in cast(list[object], raw_renders):
            if not isinstance(render, dict):
                continue
            render_dict = cast(dict[str, Any], render)
            label = render_dict.get("label")
            data_url = render_dict.get("dataUrl")
            if not isinstance(label, str) or not isinstance(data_url, str):
                continue
            renders.append(
                LiveReferenceRender(
                    label=label,
                    data_url=data_url,
                    viewport=viewport,
                )
            )

        if not renders:
            raise RuntimeError(f"Live reference inspection produced no renders for {url}")

        design_system_payload = payload.get("designSystem")
        if not isinstance(design_system_payload, dict):
            raise RuntimeError(
                f"Live reference inspection produced no design system for {url}"
            )

        design_system = LiveReferenceDesignSystem.model_validate(design_system_payload)
        normalized_url = payload.get("url") if isinstance(payload.get("url"), str) else url
        return LiveReferenceContext(
            url=normalized_url,
            design_system=design_system,
            renders=renders,
        )
