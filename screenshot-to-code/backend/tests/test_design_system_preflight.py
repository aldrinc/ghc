import os

import pytest

from loop.contracts import DesignSystemPreflight
from loop.design_system_preflight import DesignSystemDocumentRenderer


def test_design_system_document_renderer_defaults_to_local_html(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAPER_MCP_RENDER_COMMAND", raising=False)
    renderer = DesignSystemDocumentRenderer()

    design_system_json, design_system_html = renderer.render(
        DesignSystemPreflight(
            title="Design System",
            summary="A local preview.",
            typography=["Body uses 'Inter'."],
            section_typography=["Hero H1 uses 'Inter' at 64px / 700."],
            section_sizing=["Hero section uses ~120px top padding and a tall media column."],
            motion_components=["Header marquee moves left-to-right in a continuous loop."],
        )
    )

    assert '"renderer": "local_html"' in design_system_json
    assert "Design System" in design_system_html
    assert "Section Typography" in design_system_html
    assert "Section Sizing" in design_system_html
    assert "Motion Components" in design_system_html


def test_design_system_document_renderer_fails_cleanly_when_paper_command_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPER_MCP_RENDER_COMMAND", "paper-render")
    renderer = DesignSystemDocumentRenderer()

    with pytest.raises(RuntimeError, match="Paper MCP command support"):
        renderer.render(DesignSystemPreflight(title="Needs Paper"))
