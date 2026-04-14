from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / ".local" / "hermes" / "validation-reports"
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import AuthContext, get_current_user
from app.db.base import engine
from app.db.deps import get_session
from app.db.models import Client, Org, Product
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.main import app


def _seed_imported_template_stub() -> dict[str, Any]:
    return {
        "root": {"props": {"title": "EMBER Draft", "description": None}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": "EMBER Presell Advertorial",
                    "pageType": "advertorial",
                    "renderMode": "draft",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "hero-section",
                                "displayName": "Hero",
                                "sourceSectionId": "hero-section",
                                "sectionKey": "hero",
                                "sectionType": "narrative",
                                "renderMode": "draft",
                                "content": [
                                    {
                                        "type": "ImportedNarrativeBlock",
                                        "props": {
                                            "id": "hero-block",
                                            "title": "EMBER Presell Advertorial",
                                            "body": "Starting point for Hermes validation demo.",
                                            "badges": [],
                                            "buttons": [],
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        ],
        "zones": {},
    }


def _assert_validation_snapshot(
    *,
    payload: dict[str, Any],
    expected_run_count: int,
    require_approval: bool = False,
) -> None:
    runs = payload["validation"]["runs"]
    if len(runs) != expected_run_count:
        raise RuntimeError(
            f"Expected {expected_run_count} validation runs, found {len(runs)}."
        )
    for index, run_entry in enumerate(runs, start=1):
        checks = run_entry["checks"]
        output_mode = checks.get("outputMode") or "markdown"
        if output_mode == "page_copy_slots":
            if checks.get("assistantMessagePresent") is not True:
                raise RuntimeError(f"Run {index} assistant message was empty.")
            if checks.get("artifactHasPuckData") is not True:
                raise RuntimeError(f"Run {index} did not persist page puckData on the artifact.")
            if checks.get("assignmentCountMatchesSlotCount") is not True:
                raise RuntimeError(f"Run {index} did not assign the full slot map.")
            if checks.get("artifactPuckDataMatchesSitePageVersion") is not True:
                raise RuntimeError(f"Run {index} artifact puckData did not match the persisted page draft.")
            if checks.get("sitePageIsImportedTemplate") is not True:
                raise RuntimeError(f"Run {index} persisted page draft was not an imported-template page.")
        else:
            if checks.get("assistantMatchesArtifact") is not True:
                raise RuntimeError(f"Run {index} assistant output does not match persisted artifact.")
            if checks.get("assistantMatchesSitePageVersion") is not True:
                raise RuntimeError(f"Run {index} assistant output does not match persisted page draft.")
            if checks.get("assistantStartsWithH1") is not True:
                raise RuntimeError(f"Run {index} assistant output did not start with the required H1.")
    if require_approval:
        if not payload["approvals"]:
            raise RuntimeError("Expected at least one approval item after approval step.")
        if payload["thread"]["status"] != "approved":
            raise RuntimeError("Expected thread status to be approved after approval step.")


def _step_reports(payload: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for index, entry in enumerate(payload["validation"]["runs"], start=1):
        run = entry.get("run") or {}
        run_inputs = run.get("inputs") or {}
        run_outputs = run.get("outputs") or {}
        artifact = entry.get("artifact") or {}
        artifact_data = artifact.get("data") or {}
        site_page_version = entry.get("sitePageVersion") or {}
        assistant_turn = entry.get("assistantTurn") or {}
        assistant_metadata = assistant_turn.get("metadata") or {}
        checks = entry.get("checks") or {}
        output_mode = checks.get("outputMode") or run_outputs.get("outputMode") or artifact_data.get("outputMode") or "markdown"
        reports.append(
            {
                "step": index,
                "outputMode": output_mode,
                "userTurn": (entry.get("userTurn") or {}).get("content"),
                "prompt": run_inputs.get("prompt"),
                "runtime": run_inputs.get("runtime") or {},
                "assistantOutput": assistant_turn.get("content"),
                "artifactContent": artifact_data.get("content"),
                "assistantMessage": artifact_data.get("assistantMessage") or assistant_turn.get("content"),
                "artifactPuckData": artifact_data.get("puckData"),
                "artifactPageSummary": artifact_data.get("pageSummary"),
                "slotAssignments": artifact_data.get("slotAssignments") or [],
                "slotCount": artifact_data.get("slotCount"),
                "pageDraftBody": site_page_version.get("body"),
                "pageDraftId": site_page_version.get("id"),
                "pageDraftPuckData": site_page_version.get("puckData"),
                "pageDraftSummary": site_page_version.get("pageSummary"),
                "runId": run.get("id"),
                "runStatus": run.get("status"),
                "startedAt": run.get("startedAt"),
                "finishedAt": run.get("finishedAt"),
                "hermesSessionId": run_outputs.get("hermesSessionId"),
                "rawAssistantResponsePreview": assistant_metadata.get("rawAssistantResponsePreview"),
                "rawOutputPreview": assistant_metadata.get("rawOutputPreview"),
                "responseNormalization": assistant_metadata.get("responseNormalization")
                or run_outputs.get("normalization")
                or {},
                "checks": checks,
            }
        )
    return reports


def _build_markdown_report(
    *,
    report_json_path: Path,
    payload: dict[str, Any],
    step_reports: list[dict[str, Any]],
    decision_line: str,
) -> str:
    runtime = payload["validation"]["runtime"]
    approvals = payload["approvals"]
    lines = [
        "# Hermes Sidecar Validation Report",
        "",
        "## Decision",
        decision_line,
        "",
        "## Runtime",
        f"- Thread ID: `{payload['thread']['id']}`",
        f"- Model: `{runtime['model']}`",
        f"- Provider: `{runtime['provider']}`",
        f"- Base URL: `{runtime['baseUrl']}`",
        f"- Hermes Session ID: `{runtime['hermesSessionId']}`",
        f"- Projection Hash: `{runtime['projectionHash']}`",
        f"- Compression Enabled: `{runtime['compressionEnabled']}`",
        f"- JSON Report: `{report_json_path}`",
        "",
    ]

    for step in step_reports:
        if step.get("outputMode") == "page_copy_slots":
            lines.extend(
                [
                    f"## Step {step['step']}",
                    "",
                    "### User Turn",
                    "",
                    step["userTurn"] or "",
                    "",
                    "### Prompt",
                    "",
                    "```text",
                    step["prompt"] or "",
                    "```",
                    "",
                    "### Assistant Message",
                    "",
                    step.get("assistantMessage") or "",
                    "",
                    "### Page Summary",
                    "",
                    "```json",
                    json.dumps(step.get("pageDraftSummary") or step.get("artifactPageSummary") or {}, indent=2),
                    "```",
                    "",
                    "### Slot Assignments",
                    "",
                    "```json",
                    json.dumps(step.get("slotAssignments") or [], indent=2),
                    "```",
                    "",
                    "### Checks",
                    "",
                    f"- assistantMessagePresent: `{step['checks'].get('assistantMessagePresent')}`",
                    f"- artifactHasPuckData: `{step['checks'].get('artifactHasPuckData')}`",
                    f"- assignmentCount: `{step['checks'].get('assignmentCount')}`",
                    f"- assignmentCountMatchesSlotCount: `{step['checks'].get('assignmentCountMatchesSlotCount')}`",
                    f"- artifactPuckDataMatchesSitePageVersion: `{step['checks'].get('artifactPuckDataMatchesSitePageVersion')}`",
                    f"- sitePageIsImportedTemplate: `{step['checks'].get('sitePageIsImportedTemplate')}`",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                f"## Step {step['step']}",
                "",
                "### User Turn",
                "",
                step["userTurn"] or "",
                "",
                "### Prompt",
                "",
                "```text",
                step["prompt"] or "",
                "```",
                "",
                "### Assistant Output",
                "",
                "```markdown",
                step["assistantOutput"] or "",
                "```",
                "",
                "### Checks",
                "",
                f"- assistantStartsWithH1: `{step['checks'].get('assistantStartsWithH1')}`",
                f"- assistantMatchesArtifact: `{step['checks'].get('assistantMatchesArtifact')}`",
                f"- assistantMatchesSitePageVersion: `{step['checks'].get('assistantMatchesSitePageVersion')}`",
                "",
            ]
        )

    if approvals:
        latest = approvals[-1]
        lines.extend(
            [
                "## Approval",
                "",
                f"- Status: `{latest['status']}`",
                f"- Decision: `{latest['decision']}`",
                f"- Target Kind: `{latest['targetKind']}`",
                f"- Target ID: `{latest['sitePageVersionId'] or latest['artifactId']}`",
                f"- Notes: `{latest['resolutionNotes']}`",
                "",
            ]
        )
    return "\n".join(lines)


def _escape_html(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _render_check_pill(label: str, value: Any) -> str:
    tone = "neutral"
    status = str(value)
    if value is True:
        tone = "good"
        status = "pass"
    elif value is False:
        tone = "bad"
        status = "fail"
    return (
        f'<span class="check-pill check-pill--{tone}">'
        f'<span class="check-pill__label">{_escape_html(label)}</span>'
        f'<span class="check-pill__value">{_escape_html(status)}</span>'
        "</span>"
    )


def _build_html_report(*, payload: dict[str, Any], step_reports: list[dict[str, Any]]) -> str:
    runtime = payload["validation"]["runtime"]
    approvals = payload["approvals"]
    first_step_id = f"step-{step_reports[0]['step']}" if step_reports else ""

    step_nav_items: list[str] = []
    step_panels: list[str] = []
    for step in step_reports:
        checks_html = "".join(
            _render_check_pill(label, value) for label, value in (step.get("checks") or {}).items()
        )
        normalization = step.get("responseNormalization") or {}
        trimmed = normalization.get("trimmedLeadingText")
        step_id = f"step-{step['step']}"
        step_nav_items.append(
            "\n".join(
                [
                    f'<button class="step-nav__item" data-step-target="{step_id}">',
                    f'  <span class="step-nav__kicker">Step {step["step"]}</span>',
                    f'  <span class="step-nav__title">{_escape_html((step.get("userTurn") or "")[:88])}</span>',
                    f'  <span class="step-nav__meta">Session {_escape_html(step.get("hermesSessionId") or "unknown")}</span>',
                    "</button>",
                ]
            )
        )
        if step.get("outputMode") == "page_copy_slots":
            page_summary = json.dumps(
                step.get("pageDraftSummary") or step.get("artifactPageSummary") or {},
                indent=2,
            )
            page_puck_data = json.dumps(step.get("pageDraftPuckData") or step.get("artifactPuckData") or {}, indent=2)
            slot_assignments = json.dumps(step.get("slotAssignments") or [], indent=2)
            step_panels.append(
                "\n".join(
                    [
                        f'<section class="step-panel" data-step-panel="{step_id}">',
                        '  <div class="step-panel__header">',
                        f'    <div><p class="eyebrow">Step {step["step"]}</p><h2>Slot-based copy-agent snapshot</h2></div>',
                        f'    <div class="step-panel__checks">{checks_html}</div>',
                        "  </div>",
                        '  <div class="inspector-grid">',
                        '    <article class="inspector-section">',
                        "      <h3>User turn</h3>",
                        f'      <pre class="text-block text-block--tight">{_escape_html(step.get("userTurn") or "")}</pre>',
                        "    </article>",
                        '    <article class="inspector-section">',
                        "      <h3>Prompt sent to Hermes</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(step.get("prompt") or "")}</pre>',
                        "    </article>",
                        '    <article class="inspector-section inspector-section--wide">',
                        "      <h3>Assistant message</h3>",
                        f'      <pre class="text-block text-block--tight">{_escape_html(step.get("assistantMessage") or "")}</pre>',
                        "    </article>",
                        '    <article class="inspector-section">',
                        "      <h3>Page summary</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(page_summary)}</pre>',
                        "    </article>",
                        '    <article class="inspector-section inspector-section--wide">',
                        "      <h3>Slot assignments</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(slot_assignments)}</pre>',
                        "    </article>",
                        '    <article class="inspector-section inspector-section--wide">',
                        "      <h3>Persisted page puckData</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(page_puck_data)}</pre>',
                        "    </article>",
                        '    <article class="inspector-section">',
                        "      <h3>Raw assistant preview</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(step.get("rawAssistantResponsePreview") or "")}</pre>',
                        "    </article>",
                        '    <article class="inspector-section">',
                        "      <h3>Raw Hermes output preview</h3>",
                        f'      <pre class="text-block text-block--code">{_escape_html(step.get("rawOutputPreview") or "")}</pre>',
                        "    </article>",
                        '    <article class="inspector-section">',
                        "      <h3>Persistence</h3>",
                        '      <dl class="detail-list">',
                        f'        <div><dt>Run ID</dt><dd>{_escape_html(step.get("runId") or "")}</dd></div>',
                        f'        <div><dt>Run status</dt><dd>{_escape_html(step.get("runStatus") or "")}</dd></div>',
                        f'        <div><dt>Draft page ID</dt><dd>{_escape_html(step.get("pageDraftId") or "")}</dd></div>',
                        f'        <div><dt>Session ID</dt><dd>{_escape_html(step.get("hermesSessionId") or "")}</dd></div>',
                        f'        <div><dt>Started</dt><dd>{_escape_html(step.get("startedAt") or "")}</dd></div>',
                        f'        <div><dt>Finished</dt><dd>{_escape_html(step.get("finishedAt") or "")}</dd></div>',
                        "      </dl>",
                        "    </article>",
                        "  </div>",
                        "</section>",
                    ]
                )
            )
            continue
        step_panels.append(
            "\n".join(
                [
                    f'<section class="step-panel" data-step-panel="{step_id}">',
                    '  <div class="step-panel__header">',
                    f'    <div><p class="eyebrow">Step {step["step"]}</p><h2>Draft and persistence snapshot</h2></div>',
                    f'    <div class="step-panel__checks">{checks_html}</div>',
                    "  </div>",
                    '  <div class="inspector-grid">',
                    '    <article class="inspector-section">',
                    "      <h3>User turn</h3>",
                    f'      <pre class="text-block text-block--tight">{_escape_html(step.get("userTurn") or "")}</pre>',
                    "    </article>",
                    '    <article class="inspector-section">',
                    "      <h3>Prompt sent to Hermes</h3>",
                    f'      <pre class="text-block text-block--code">{_escape_html(step.get("prompt") or "")}</pre>',
                    "    </article>",
                    '    <article class="inspector-section inspector-section--wide">',
                    "      <div class=\"section-header-row\"><h3>Normalized assistant draft</h3>",
                    f'      <span class="meta-chip">trimmedLeadingText={_escape_html(str(trimmed))}</span></div>',
                    f'      <pre class="text-block text-block--draft">{_escape_html(step.get("assistantOutput") or "")}</pre>',
                    "    </article>",
                    '    <article class="inspector-section">',
                    "      <h3>Raw assistant preview</h3>",
                    f'      <pre class="text-block text-block--code">{_escape_html(step.get("rawAssistantResponsePreview") or "")}</pre>',
                    "    </article>",
                    '    <article class="inspector-section">',
                    "      <h3>Raw Hermes output preview</h3>",
                    f'      <pre class="text-block text-block--code">{_escape_html(step.get("rawOutputPreview") or "")}</pre>',
                    "    </article>",
                    '    <article class="inspector-section">',
                    "      <h3>Persistence</h3>",
                    '      <dl class="detail-list">',
                    f'        <div><dt>Run ID</dt><dd>{_escape_html(step.get("runId") or "")}</dd></div>',
                    f'        <div><dt>Run status</dt><dd>{_escape_html(step.get("runStatus") or "")}</dd></div>',
                    f'        <div><dt>Draft page ID</dt><dd>{_escape_html(step.get("pageDraftId") or "")}</dd></div>',
                    f'        <div><dt>Session ID</dt><dd>{_escape_html(step.get("hermesSessionId") or "")}</dd></div>',
                    f'        <div><dt>Started</dt><dd>{_escape_html(step.get("startedAt") or "")}</dd></div>',
                    f'        <div><dt>Finished</dt><dd>{_escape_html(step.get("finishedAt") or "")}</dd></div>',
                    "      </dl>",
                    "    </article>",
                    "  </div>",
                    "</section>",
                ]
            )
        )

    approval_html = ""
    if approvals:
        latest = approvals[-1]
        approval_html = "\n".join(
            [
                '<section class="summary-section">',
                "  <h3>Approval</h3>",
                '  <dl class="detail-list">',
                f'    <div><dt>Status</dt><dd>{_escape_html(latest.get("status"))}</dd></div>',
                f'    <div><dt>Decision</dt><dd>{_escape_html(latest.get("decision"))}</dd></div>',
                f'    <div><dt>Target kind</dt><dd>{_escape_html(latest.get("targetKind"))}</dd></div>',
                f'    <div><dt>Target ID</dt><dd>{_escape_html(latest.get("sitePageVersionId") or latest.get("artifactId"))}</dd></div>',
                f'    <div><dt>Notes</dt><dd>{_escape_html(latest.get("resolutionNotes"))}</dd></div>',
                "  </dl>",
                "</section>",
            ]
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Hermes Sidecar Validation Report</title>
    <style>
      :root {{
        --bg: #f4f1ea;
        --surface: rgba(255, 252, 246, 0.92);
        --surface-strong: #fffdf8;
        --line: rgba(46, 39, 31, 0.14);
        --line-strong: rgba(46, 39, 31, 0.24);
        --text: #201913;
        --muted: #67594d;
        --accent: #a14f2b;
        --accent-soft: rgba(161, 79, 43, 0.12);
        --good: #246249;
        --good-soft: rgba(36, 98, 73, 0.14);
        --bad: #8f3d2a;
        --bad-soft: rgba(143, 61, 42, 0.14);
        --shadow: 0 22px 60px rgba(44, 34, 22, 0.10);
        --radius-xl: 28px;
        --radius-lg: 18px;
        --radius-md: 14px;
        --font-sans: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
        --font-mono: "JetBrains Mono", "SFMono-Regular", "Consolas", monospace;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top left, rgba(161, 79, 43, 0.14), transparent 26rem),
          linear-gradient(180deg, #faf7f1 0%, var(--bg) 100%);
        color: var(--text);
        font-family: var(--font-sans);
      }}
      .shell {{
        width: min(1520px, calc(100vw - 32px));
        margin: 24px auto;
        display: grid;
        grid-template-columns: 320px minmax(0, 1fr);
        gap: 20px;
      }}
      .sidebar, .main-panel {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius-xl);
        box-shadow: var(--shadow);
        backdrop-filter: blur(18px);
      }}
      .sidebar {{
        padding: 24px 20px;
        position: sticky;
        top: 20px;
        align-self: start;
      }}
      .main-panel {{
        padding: 28px;
      }}
      .eyebrow {{
        margin: 0 0 8px;
        font-size: 11px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--accent);
        font-weight: 700;
      }}
      h1, h2, h3 {{ margin: 0; font-weight: 700; }}
      h1 {{ font-size: clamp(2.2rem, 5vw, 3.8rem); line-height: 0.96; letter-spacing: -0.04em; }}
      h2 {{ font-size: 1.4rem; line-height: 1.1; letter-spacing: -0.03em; }}
      h3 {{ font-size: 0.95rem; line-height: 1.25; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }}
      p {{ margin: 0; }}
      .hero-copy {{
        display: grid;
        gap: 12px;
        margin-bottom: 28px;
      }}
      .hero-copy p {{
        max-width: 62ch;
        color: var(--muted);
        font-size: 0.98rem;
        line-height: 1.6;
      }}
      .summary-grid {{
        display: grid;
        gap: 16px;
      }}
      .summary-section {{
        border-top: 1px solid var(--line);
        padding-top: 16px;
        display: grid;
        gap: 12px;
      }}
      .detail-list {{
        margin: 0;
        display: grid;
        gap: 10px;
      }}
      .detail-list div {{
        display: grid;
        gap: 2px;
        padding: 10px 12px;
        background: var(--surface-strong);
        border: 1px solid var(--line);
        border-radius: var(--radius-md);
      }}
      .detail-list dt {{
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: var(--muted);
      }}
      .detail-list dd {{
        margin: 0;
        font-size: 0.92rem;
        line-height: 1.45;
        overflow-wrap: anywhere;
      }}
      .step-nav {{
        display: grid;
        gap: 10px;
      }}
      .step-nav__item {{
        width: 100%;
        text-align: left;
        border: 1px solid var(--line);
        background: var(--surface-strong);
        border-radius: var(--radius-lg);
        padding: 14px 14px 15px;
        display: grid;
        gap: 6px;
        cursor: pointer;
        transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
      }}
      .step-nav__item:hover {{
        transform: translateY(-1px);
        border-color: var(--line-strong);
        box-shadow: 0 16px 28px rgba(44, 34, 22, 0.08);
      }}
      .step-nav__item.is-active {{
        border-color: rgba(161, 79, 43, 0.46);
        background: linear-gradient(180deg, rgba(161, 79, 43, 0.08), rgba(255, 253, 248, 0.96));
      }}
      .step-nav__kicker {{
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: var(--accent);
        font-weight: 700;
      }}
      .step-nav__title {{
        font-size: 0.95rem;
        line-height: 1.35;
        color: var(--text);
      }}
      .step-nav__meta {{
        font-size: 0.8rem;
        color: var(--muted);
      }}
      .main-panel__header {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: end;
        padding-bottom: 20px;
        border-bottom: 1px solid var(--line);
        margin-bottom: 24px;
      }}
      .main-panel__header p {{
        color: var(--muted);
        max-width: 60ch;
        font-size: 0.95rem;
      }}
      .main-panel__meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: flex-end;
      }}
      .meta-chip {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 999px;
        background: var(--surface-strong);
        border: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.82rem;
      }}
      .step-panel {{
        display: none;
        animation: panel-in 220ms ease;
      }}
      .step-panel.is-active {{ display: block; }}
      @keyframes panel-in {{
        from {{ opacity: 0; transform: translateY(8px); }}
        to {{ opacity: 1; transform: translateY(0); }}
      }}
      .step-panel__header {{
        display: flex;
        align-items: start;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 18px;
      }}
      .step-panel__checks {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: flex-end;
      }}
      .check-pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid transparent;
      }}
      .check-pill__label {{ color: var(--muted); }}
      .check-pill--good {{ background: var(--good-soft); border-color: rgba(36, 98, 73, 0.22); color: var(--good); }}
      .check-pill--bad {{ background: var(--bad-soft); border-color: rgba(143, 61, 42, 0.22); color: var(--bad); }}
      .check-pill--neutral {{ background: rgba(32, 25, 19, 0.05); border-color: rgba(32, 25, 19, 0.08); color: var(--muted); }}
      .inspector-grid {{
        display: grid;
        gap: 16px;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .inspector-section {{
        border: 1px solid var(--line);
        background: rgba(255, 253, 248, 0.82);
        border-radius: var(--radius-lg);
        padding: 16px;
        display: grid;
        gap: 12px;
      }}
      .inspector-section--wide {{
        grid-column: 1 / -1;
      }}
      .section-header-row {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
      }}
      .text-block {{
        margin: 0;
        font-family: var(--font-mono);
        font-size: 0.83rem;
        line-height: 1.6;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        max-height: 540px;
        overflow: auto;
        padding: 14px;
        border-radius: 14px;
        background: #1d1917;
        color: #f4ede3;
        border: 1px solid rgba(255, 255, 255, 0.06);
      }}
      .text-block--tight {{
        max-height: none;
      }}
      .text-block--draft {{
        background: linear-gradient(180deg, #fffaf0 0%, #f6f0e4 100%);
        color: #221b15;
        border-color: rgba(46, 39, 31, 0.10);
        font-family: var(--font-sans);
        font-size: 0.97rem;
        line-height: 1.75;
      }}
      .text-block--code {{
        font-size: 0.78rem;
      }}
      .footer-note {{
        margin-top: 24px;
        padding-top: 18px;
        border-top: 1px solid var(--line);
        color: var(--muted);
        font-size: 0.86rem;
      }}
      @media (max-width: 1080px) {{
        .shell {{
          width: min(100vw - 20px, 100%);
          grid-template-columns: 1fr;
        }}
        .sidebar {{
          position: static;
        }}
        .inspector-grid {{
          grid-template-columns: 1fr;
        }}
        .main-panel {{
          padding: 20px;
        }}
        .step-panel__header,
        .main-panel__header {{
          flex-direction: column;
          align-items: stretch;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <aside class="sidebar">
        <div class="hero-copy">
          <p class="eyebrow">Hermes Review</p>
          <h1>Validation viewer</h1>
          <p>Local visual inspector for the real Hermes sidecar payload. It shows the user turn, exact prompt sent to Hermes, normalized draft, raw previews, persistence checks, and approval outcome.</p>
        </div>

        <div class="summary-grid">
          <section class="summary-section">
            <h3>Runtime</h3>
            <dl class="detail-list">
              <div><dt>Thread ID</dt><dd>{_escape_html(payload["thread"]["id"])}</dd></div>
              <div><dt>Model</dt><dd>{_escape_html(runtime["model"])}</dd></div>
              <div><dt>Provider</dt><dd>{_escape_html(runtime["provider"])}</dd></div>
              <div><dt>Base URL</dt><dd>{_escape_html(runtime["baseUrl"])}</dd></div>
              <div><dt>Hermes Session</dt><dd>{_escape_html(runtime["hermesSessionId"])}</dd></div>
              <div><dt>Projection Hash</dt><dd>{_escape_html(runtime["projectionHash"])}</dd></div>
            </dl>
          </section>

          <section class="summary-section">
            <h3>Thread state</h3>
            <dl class="detail-list">
              <div><dt>Status</dt><dd>{_escape_html(payload["thread"]["status"])}</dd></div>
              <div><dt>Objective</dt><dd>{_escape_html(payload["thread"]["objectiveType"])}</dd></div>
              <div><dt>Bundle</dt><dd>{_escape_html(payload["thread"]["bundleKey"])}</dd></div>
              <div><dt>Approval count</dt><dd>{_escape_html(str(len(approvals)))}</dd></div>
            </dl>
          </section>

          <section class="summary-section">
            <h3>Steps</h3>
            <div class="step-nav">
              {"".join(step_nav_items)}
            </div>
          </section>

          {approval_html}
        </div>
      </aside>

      <main class="main-panel">
        <div class="main-panel__header">
          <div>
            <p class="eyebrow">Payload Inspector</p>
            <h2>Prompt, draft, raw preview, and persistence checks</h2>
            <p>The normalized assistant output is what mOS persisted. The raw assistant preview and raw Hermes output preview show what was trimmed or noisy before canonical persistence.</p>
          </div>
          <div class="main-panel__meta">
            <span class="meta-chip">runCount={_escape_html(str(len(step_reports)))}</span>
            <span class="meta-chip">compressionEnabled={_escape_html(str(runtime["compressionEnabled"]))}</span>
            <span class="meta-chip">schema={_escape_html(runtime["runtimeSchemaVersion"])}</span>
          </div>
        </div>

        {"".join(step_panels)}

        <p class="footer-note">Generated from the local validation payload after draft, revision, and approval. If a future run regresses, compare the raw assistant preview against the normalized draft for the failing step.</p>
      </main>
    </div>
    <script>
      const navItems = Array.from(document.querySelectorAll('[data-step-target]'));
      const panels = Array.from(document.querySelectorAll('[data-step-panel]'));
      function activate(stepId) {{
        navItems.forEach((item) => {{
          item.classList.toggle('is-active', item.dataset.stepTarget === stepId);
        }});
        panels.forEach((panel) => {{
          panel.classList.toggle('is-active', panel.dataset.stepPanel === stepId);
        }});
      }}
      navItems.forEach((item) => {{
        item.addEventListener('click', () => activate(item.dataset.stepTarget));
      }});
      if ({'true' if step_reports else 'false'}) {{
        activate('{first_step_id}');
      }}
    </script>
  </body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the local Hermes sidecar validation flow with draft, revision, inspection, and approval."
    )
    parser.add_argument(
        "--message",
        default=(
            "Rewrite the opening third of the EMBER presell advertorial. Keep the dementia-fear angle, "
            "tighten the emotional pacing, and make it cleaner for human review. Return markdown only."
        ),
    )
    parser.add_argument(
        "--revision",
        default=(
            "Revise the same draft. Keep the headline and structure, but shorten the paragraphs, sharpen the 2am "
            "dementia-search scene, and compress the failed-solutions section. Return markdown only."
        ),
    )
    args = parser.parse_args()

    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        future=True,
    )
    session = TestingSessionLocal()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    org = Org(id=uuid.uuid4(), name="Hermes Validation Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    client = Client(org_id=org.id, name="EMBER Workspace", industry="Ecommerce")
    session.add(client)
    session.commit()
    session.refresh(client)

    product = Product(org_id=org.id, client_id=client.id, title="EMBER")
    session.add(product)
    session.commit()
    session.refresh(product)

    sites_repo = SitesRuntimeRepository(session)
    site = sites_repo.create_site(
        org_id=str(org.id),
        client_id=str(client.id),
        product_id=str(product.id),
        name="EMBER Site",
        site_type="presell",
        site_family="prototype",
        route_slug=f"ember-validation-{uuid.uuid4().hex[:8]}",
    )
    page = sites_repo.create_page(
        site_id=str(site.id),
        name="EMBER Presell Advertorial",
        slug="ember-presell",
        page_type="advertorial",
        page_role="presell",
        adapted_puck_data=_seed_imported_template_stub(),
    )
    sites_repo.create_page_version(
        page_id=str(page.id),
        puck_data=_seed_imported_template_stub(),
        provenance={"source": "validation_seed"},
        status="approved",
        source_type="validation_seed",
        source_id="validation_seed",
        diff_summary="Seed page for Hermes sidecar validation demo",
    )
    session.commit()

    auth_context = AuthContext(user_id="hermes-validation-user", org_id=str(org.id))

    def get_session_override():
        try:
            yield session
        finally:
            pass

    def get_user_override():
        return auth_context

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = get_user_override

    try:
        with TestClient(app) as api_client:
            create_response = api_client.post(
                "/agent-threads",
                json={
                    "clientId": str(client.id),
                    "productId": str(product.id),
                    "agentProfile": "copy",
                    "objectiveType": "presell_page_rewrite",
                    "bundleKey": "ember_v1",
                    "title": "EMBER validation flow",
                    "siteId": str(site.id),
                    "pageId": str(page.id),
                },
            )
            create_response.raise_for_status()
            thread_id = create_response.json()["thread"]["id"]

            first_message = api_client.post(
                f"/agent-threads/{thread_id}/messages",
                json={"content": args.message},
            )
            if first_message.status_code >= 400:
                raise RuntimeError(
                    f"First message failed ({first_message.status_code}): {first_message.text}"
                )
            validation_after_first = api_client.get(f"/agent-threads/{thread_id}/validation")
            validation_after_first.raise_for_status()
            first_payload = validation_after_first.json()
            _assert_validation_snapshot(payload=first_payload, expected_run_count=1)
            first_session_id = first_payload["validation"]["runtime"]["hermesSessionId"]

            revision_message = api_client.post(
                f"/agent-threads/{thread_id}/messages",
                json={"content": args.revision},
            )
            if revision_message.status_code >= 400:
                raise RuntimeError(
                    f"Revision message failed ({revision_message.status_code}): {revision_message.text}"
                )
            validation_after_revision = api_client.get(f"/agent-threads/{thread_id}/validation")
            validation_after_revision.raise_for_status()
            revision_payload = validation_after_revision.json()
            _assert_validation_snapshot(payload=revision_payload, expected_run_count=2)
            revision_session_id = revision_payload["validation"]["runtime"]["hermesSessionId"]
            if not first_session_id or first_session_id != revision_session_id:
                raise RuntimeError("Hermes session id was not reused across the revision turn.")

            latest_run = revision_payload["validation"]["runs"][-1]
            latest_page_version_id = (latest_run.get("sitePageVersion") or {}).get("id")
            if not latest_page_version_id:
                raise RuntimeError("Latest validation run did not expose a draft site page version.")

            approval_response = api_client.post(
                f"/agent-threads/{thread_id}/approve",
                json={
                    "targetKind": "site_page_version",
                    "targetId": latest_page_version_id,
                    "decision": "approved",
                    "notes": "Validation demo approval",
                },
            )
            if approval_response.status_code >= 400:
                raise RuntimeError(
                    f"Approval request failed ({approval_response.status_code}): {approval_response.text}"
                )
            final_validation = api_client.get(f"/agent-threads/{thread_id}/validation")
            final_validation.raise_for_status()
            final_payload = final_validation.json()
            _assert_validation_snapshot(payload=final_payload, expected_run_count=2, require_approval=True)

            REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            json_report_path = REPORTS_ROOT / f"hermes-sidecar-validation-{timestamp}-{thread_id}.json"
            markdown_report_path = REPORTS_ROOT / f"hermes-sidecar-validation-{timestamp}-{thread_id}.md"
            html_report_path = REPORTS_ROOT / f"hermes-sidecar-validation-{timestamp}-{thread_id}.html"

            step_reports = _step_reports(final_payload)
            report = {
                "summary": {
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "threadId": thread_id,
                    "agentProfile": final_payload["thread"]["agentProfile"],
                    "objectiveType": final_payload["thread"]["objectiveType"],
                    "model": final_payload["validation"]["runtime"]["model"],
                    "provider": final_payload["validation"]["runtime"]["provider"],
                    "baseUrl": final_payload["validation"]["runtime"]["baseUrl"],
                    "hermesSessionId": final_payload["validation"]["runtime"]["hermesSessionId"],
                    "sessionReusedAcrossRevision": first_session_id == revision_session_id,
                    "runCount": len(final_payload["validation"]["runs"]),
                    "approvedThread": final_payload["thread"]["status"] == "approved",
                    "approvalCount": len(final_payload["approvals"]),
                },
                "steps": step_reports,
                "snapshots": {
                    "afterFirstDraft": first_payload,
                    "afterRevision": revision_payload,
                    "afterApproval": final_payload,
                },
            }
            json_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            markdown_report_path.write_text(
                _build_markdown_report(
                    report_json_path=json_report_path,
                    payload=final_payload,
                    step_reports=step_reports,
                    decision_line=(
                        "Validated the local Hermes sidecar conversational path for EMBER on "
                        "Anthropic Haiku with draft, revise, and approve."
                    ),
                ),
                encoding="utf-8",
            )
            html_report_path.write_text(
                _build_html_report(payload=final_payload, step_reports=step_reports),
                encoding="utf-8",
            )

            print(
                json.dumps(
                    {
                        "threadId": thread_id,
                        "model": final_payload["validation"]["runtime"]["model"],
                        "hermesSessionId": final_payload["validation"]["runtime"]["hermesSessionId"],
                        "sessionReusedAcrossRevision": first_session_id == revision_session_id,
                        "reportJson": str(json_report_path),
                        "reportMarkdown": str(markdown_report_path),
                        "reportHtml": str(html_report_path),
                    },
                    indent=2,
                )
            )
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


if __name__ == "__main__":
    main()
