from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from typing import Generator

from mcp.server.fastmcp import FastMCP

from app.agent_platform.page_editor_runtime import (
    PageEditOperation,
    PageEditorRuntimeError,
    PageEditorRuntimeService,
)
from app.db.base import SessionLocal


@contextmanager
def _runtime_service(*, thread_id: str) -> Generator[PageEditorRuntimeService, None, None]:
    session = SessionLocal()
    try:
        yield PageEditorRuntimeService(session=session, thread_id=thread_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def build_server(*, thread_id: str) -> FastMCP:
    server = FastMCP(
        name="marketi-page-editor",
        instructions=(
            "Explicit canonical page editor for mOS page-orchestrator threads. "
            "Use get_page_context to inspect the current working page state and "
            "apply_page_edits to create draft page versions through explicit JSON-pointer edits."
        ),
    )

    @server.tool(
        name="get_page_context",
        description=(
            "Read the current canonical working page context for this thread's bound page, "
            "including the current draft-or-approved puckData, page summary, site pages, "
            "and explicit editable bindings."
        ),
    )
    def get_page_context(
        include_puck_data: bool = True,
        include_editable_bindings: bool = True,
    ) -> str:
        with _runtime_service(thread_id=thread_id) as service:
            payload = service.get_page_context(
                include_puck_data=include_puck_data,
                include_editable_bindings=include_editable_bindings,
            )
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    @server.tool(
        name="apply_page_edits",
        description=(
            "Apply explicit JSON-pointer edits to the canonical working page for this thread "
            "and create a new draft site page version. This tool never edits sidecar files."
        ),
    )
    def apply_page_edits(
        edits: list[PageEditOperation],
        change_summary: str,
        expected_base_version_id: str | None = None,
    ) -> str:
        with _runtime_service(thread_id=thread_id) as service:
            payload = service.apply_page_edits(
                edits=edits,
                change_summary=change_summary,
                expected_base_version_id=expected_base_version_id,
            )
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mOS page editor MCP server.")
    parser.add_argument("--thread-id", required=True, help="Bound agent thread id.")
    args = parser.parse_args()
    try:
        server = build_server(thread_id=args.thread_id)
        server.run(transport="stdio")
    except PageEditorRuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
