import json
import os
from pathlib import Path

from loop.contracts import (
    DesignSystemPreflight,
    LiveReferenceContext,
    ReferenceBundle,
)
from loop.gemini import GeminiPart, data_url_to_part, generate_structured_output, text_part


DESIGN_SYSTEM_PREFLIGHT_SYSTEM_INSTRUCTION = """
You generate a screenshot-to-code design-system preflight artifact.

Focus on what is actually visible in the supplied screenshots, videos, and browser renders.
If a live page summary is provided, use it to strengthen precision, but do not invent styles that are not supported by the visible reference.

Return a concise, implementation-ready design system that a frontend coding agent can execute directly.
Be explicit about motion-bearing components and section-level typography whenever they are visible.
Also capture section sizing consistency whenever it is visible, especially repeated section heights, vertical padding cadence, container widths, media aspect ratios, and any hero or card min-heights that define the rhythm of the page.
Every structured field in the response schema is a JSON array of strings, not an object. Do not return keyed maps such as `{ "hero_h1": "..." }` for typography, section sizing, components, motion components, brand, or source notes.
Capture distinct chrome layers and state variants when they are visible, such as announcement bars, promo bands, sticky header states, modal overlays, dropdown shells, mega-menus, newsletter/legal bands, or closing accessibility regions. Record those in layout, components, or source notes instead of flattening them into a generic header/footer description.
If a shared shell, canvas, card, or wrapper spans multiple neighboring sections, call out that relationship explicitly in layout or source notes so later blueprinting can preserve it.
If the live reference summary includes DOM landmarks, section inventory, chrome layers, heading hierarchy, or shell relationships, treat those as structural evidence rather than optional notes.
If the live reference summary includes concrete image URLs, SVG references, or CSS background-image assets in `asset_inventory`, preserve those sources in components or source notes so later blueprinting can require the same site assets instead of placeholders.
When the DOM or computed styles expose component geometry, capture it explicitly. This includes horizontal-vs-vertical card orientation, left/right media-to-text splits, full-height media panels, full-bleed image coverage, repeated row/card patterns, and gradient or image-backed shells.

For typography, do not stop at a global type scale. Capture section-specific roles and visible values such as:
- header/nav links
- announcement or marquee banners under the header
- hero badges, eyebrow text, H1/H2/H3, body copy, CTA text, legal/support text
- card titles, stat numerals, FAQ questions, footer links

For each visible typography role, include the exact or best-supported font family, font size, weight, line-height, letter-spacing, casing, and where it appears.

For motion components, identify each moving UI element explicitly and describe:
- component/location
- trigger (auto, scroll, hover, loop)
- direction/path of motion
- pacing/timing/easing if visible
- repeat behavior / resting state

For section sizing, identify visible sizing patterns such as:
- hero height or min-height
- section top/bottom padding rhythm
- repeated container max-widths
- card/media aspect ratios
- consistent section-to-section spacing relationships

Example: a marquee or moving banner directly beneath the header should be called out as a motion-bearing component instead of being buried in generic motion notes.
Do not include speculation or fake assets.
""".strip()


class DesignSystemPreflightBuilder:
    def __init__(self, gemini_api_key: str):
        self._gemini_api_key = gemini_api_key
        self._model_name = "gemini-3-flash-preview"

    async def build(self, reference_bundle: ReferenceBundle) -> DesignSystemPreflight:
        live_reference_block = ""
        if reference_bundle.live_reference is not None:
            live_reference_block = json.dumps(
                _live_reference_payload(reference_bundle.live_reference), indent=2
            )

        parts: list[GeminiPart] = [
            text_part(
                "\n".join(
                    [
                        "Generate the required design-system preflight artifact for this screenshot-to-code task.",
                        "Prioritize styles and components that are actually visible in the supplied media.",
                        "Output implementation-ready sections for philosophy, typography, section-level typography, colors, spacing, radii, layout, section sizing, components, motion, motion-bearing components, and brand.",
                        "Return each schema field as a JSON array of strings where the schema expects a list; never emit keyed objects for section typography, section sizing, components, motion components, brand, or source notes.",
                        "If browser inspection context exists, use it to improve precision, especially for exact font names and colors.",
                        "If browser inspection exposes concrete image, SVG, or background asset URLs, preserve those references in components or source notes so the executor can reuse the same site media later.",
                        "Call out moving UI components explicitly, such as marquees, scrolling banners, carousels, sliding review strips, or animated badges.",
                        "For typography, map visible text roles to section-specific font details instead of only giving a global scale.",
                        "For layout consistency, map visible section sizing patterns instead of leaving section heights and paddings vague.",
                        "If browser inspection exposes section inventory, chrome layers, heading hierarchy, or shell relationships, promote those facts into layout, section sizing, components, or source notes.",
                        "If browser inspection exposes component geometry such as horizontal-vs-vertical rows, media-to-text splits, full-height media panels, repeated card patterns, or gradient shells, capture those facts explicitly in layout or components.",
                        "Call out structurally distinct chrome layers, shared shells, and closing regions explicitly in layout/components/source notes instead of flattening them into generic header/footer notes.",
                        (
                            "<live_reference_summary>\n"
                            + live_reference_block
                            + "\n</live_reference_summary>"
                        )
                        if live_reference_block
                        else "",
                    ]
                ).strip()
            )
        ]

        for index, image in enumerate(reference_bundle.images, start=1):
            parts.append(text_part(f"Reference image {index}:"))
            _append_media_part_if_valid(parts, image)

        if reference_bundle.live_reference is not None:
            for index, render in enumerate(reference_bundle.live_reference.renders, start=1):
                parts.append(
                    text_part(
                        f"Live browser render {index} ({render.label}) from {reference_bundle.live_reference.url}:"
                    )
                )
                _append_media_part_if_valid(parts, render.data_url)

        for index, video in enumerate(reference_bundle.videos, start=1):
            parts.append(text_part(f"Reference video {index}:"))
            _append_media_part_if_valid(parts, video)

        return await generate_structured_output(
            api_key=self._gemini_api_key,
            model_name=self._model_name,
            thinking_level="high",
            system_instruction=DESIGN_SYSTEM_PREFLIGHT_SYSTEM_INSTRUCTION,
            parts=parts,
            response_schema=DesignSystemPreflight,
        )


class DesignSystemDocumentRenderer:
    def render(self, design_system: DesignSystemPreflight) -> tuple[str, str]:
        paper_command = os.getenv("PAPER_MCP_RENDER_COMMAND", "").strip()
        if paper_command:
            raise RuntimeError(
                "Paper MCP command support is not wired in this runtime yet. "
                "Unset PAPER_MCP_RENDER_COMMAND or add the adapter implementation first."
            )

        rendered = design_system.model_copy(
            update={"renderer": "local_html", "paper_mcp_status": "not_configured"}
        )
        return rendered.model_dump_json(indent=2), _render_html(rendered)


def build_design_system_artifact_paths(run_dir: str) -> tuple[Path, Path]:
    artifact_dir = Path(run_dir) / "design-system"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir / "design-system.json", artifact_dir / "design-system.html"


def _live_reference_payload(live_reference: LiveReferenceContext) -> dict[str, object]:
    return {
        "url": live_reference.url,
        "page_title": live_reference.design_system.page_title,
        "typography": live_reference.design_system.typography,
        "colors": live_reference.design_system.colors,
        "spacing": live_reference.design_system.spacing,
        "radii": live_reference.design_system.radii,
        "layout": live_reference.design_system.layout,
        "components": live_reference.design_system.components,
        "asset_inventory": live_reference.design_system.asset_inventory,
        "dom_landmarks": live_reference.design_system.dom_landmarks,
        "section_inventory": live_reference.design_system.section_inventory,
        "chrome_layers": live_reference.design_system.chrome_layers,
        "heading_hierarchy": live_reference.design_system.heading_hierarchy,
        "shell_relationships": live_reference.design_system.shell_relationships,
        "dom_evidence": live_reference.design_system.dom_evidence.model_dump(
            mode="json"
        ),
        "raw_observations": live_reference.design_system.raw_observations,
        "render_labels": [render.label for render in live_reference.renders],
    }


def _render_html(design_system: DesignSystemPreflight) -> str:
    sections = [
        ("Philosophy", design_system.philosophy),
        ("Typography", design_system.typography),
        ("Section Typography", design_system.section_typography),
        ("Colors", design_system.colors),
        ("Spacing & Radius", [*design_system.spacing, *design_system.radii]),
        ("Layout", design_system.layout),
        ("Section Sizing", design_system.section_sizing),
        ("Components", design_system.components),
        ("Motion", design_system.motion),
        ("Motion Components", design_system.motion_components),
        ("Brand", design_system.brand),
        ("Source Notes", design_system.source_notes),
    ]

    cards = "".join(
        f"<section class='card'><h2>{title}</h2>{_render_list(items)}</section>"
        for title, items in sections
        if items
    )

    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{_escape(design_system.title or 'Design System Preflight')}</title>
    <style>
      :root {{ color-scheme: light; font-family: Inter, system-ui, sans-serif; }}
      body {{ margin: 0; background: #111; color: #f7f3ec; }}
      .shell {{ padding: 24px; }}
      .header {{ margin-bottom: 24px; }}
      .header h1 {{ margin: 0 0 8px; font-size: 28px; }}
      .header p {{ margin: 0; max-width: 960px; color: #d6d0c7; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
      .card {{ background: #f8f4ee; color: #222; border-radius: 18px; padding: 24px; min-height: 240px; }}
      .card h2 {{ margin: 0 0 12px; font-size: 24px; font-weight: 500; }}
      ul {{ margin: 0; padding-left: 18px; }}
      li {{ margin: 0 0 8px; line-height: 1.5; }}
    </style>
  </head>
  <body>
    <main class="shell">
      <header class="header">
        <h1>{_escape(design_system.title or 'Design System Preflight')}</h1>
        <p>{_escape(design_system.summary)}</p>
      </header>
      <div class="grid">{cards}</div>
    </main>
  </body>
</html>
""".strip()


def _render_list(items: list[str]) -> str:
    if not items:
        return "<p>No items captured.</p>"
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _append_media_part_if_valid(parts: list[GeminiPart], data_url: str) -> None:
    try:
        parts.append(data_url_to_part(data_url))
    except Exception:
        parts.append(
            text_part(
                "A reference media item was present but could not be decoded for preflight inspection; rely on the rest of the provided evidence."
            )
        )
