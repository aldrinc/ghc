from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

SCRIPT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_ROOT = REPO_ROOT / ".local" / "hermes" / "honest-herbalist-reports"
sys.path.insert(0, str(SCRIPT_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from hermes_sidecar_validation_demo import (  # noqa: E402
    _assert_validation_snapshot,
    _build_html_report,
    _build_markdown_report,
    _step_reports,
)

from app.auth.dependencies import AuthContext, get_current_user  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.deps import get_session  # noqa: E402
from app.db.models import Client, Product, Site  # noqa: E402
from app.db.repositories.sites_runtime import SitesRuntimeRepository  # noqa: E402
from app.main import app  # noqa: E402


BUNDLE_KEY = "honest_herbalist_v1"
PRESALE_OUTPUT_NAME = "HONEST-HERBALIST-PRESALE-ADVERTORIAL.md"
SALES_OUTPUT_NAME = "HONEST-HERBALIST-SALES-PAGE.md"


def _seed_imported_template_stub(
    *,
    page_name: str,
    page_type: str,
    body: str,
) -> dict[str, Any]:
    return {
        "root": {"props": {"title": page_name, "description": None}},
        "content": [
            {
                "type": "ImportedPage",
                "props": {
                    "id": "page-root",
                    "pageName": page_name,
                    "pageType": page_type,
                    "renderMode": "draft",
                    "content": [
                        {
                            "type": "ImportedSection",
                            "props": {
                                "id": "agent-seed-section",
                                "displayName": "Agent Seed",
                                "sourceSectionId": "agent-seed-section",
                                "sectionKey": "agent-seed",
                                "sectionType": "narrative",
                                "renderMode": "draft",
                                "content": [
                                    {
                                        "type": "ImportedNarrativeBlock",
                                        "props": {
                                            "id": "agent-seed-block",
                                            "title": page_name,
                                            "body": body,
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


def _load_workspace(session) -> tuple[Client, Product, Site]:
    client_candidates = list(
        session.scalars(
            select(Client)
            .where(Client.name == "The Honest Herbalist")
            .order_by(Client.created_at.desc())
        ).all()
    )
    if not client_candidates:
        raise RuntimeError("Could not find the real 'The Honest Herbalist' workspace in the local database.")

    for client in client_candidates:
        product = session.scalars(
            select(Product).where(
                Product.client_id == client.id,
                Product.title == "The Honest Herbalist Handbook",
            )
        ).first()
        site = session.scalars(
            select(Site).where(
                Site.client_id == client.id,
                Site.name == "Honest Herbalist",
            )
        ).first()
        if product and site:
            return client, product, site

    raise RuntimeError(
        "Found Honest Herbalist workspaces, but none had both the handbook product and the main Honest Herbalist site."
    )


def _ensure_review_page(
    *,
    sites_repo: SitesRuntimeRepository,
    site: Site,
    slug: str,
    name: str,
    page_type: str,
    page_role: str,
    seed_body: str,
):
    page = sites_repo.get_page_by_slug(site_id=str(site.id), slug=slug)
    if not page:
        page = sites_repo.create_page(
            site_id=str(site.id),
            name=name,
            slug=slug,
            page_type=page_type,
            page_role=page_role,
            adapted_puck_data=_seed_imported_template_stub(
                page_name=name,
                page_type=page_type,
                body=seed_body,
            ),
        )

    latest_approved = sites_repo.latest_version_for_page(page_id=str(page.id), status="approved")
    if not latest_approved:
        sites_repo.create_page_version(
            page_id=str(page.id),
            puck_data=_seed_imported_template_stub(
                page_name=name,
                page_type=page_type,
                body=seed_body,
            ),
            provenance={"source": "honest_herbalist_hermes_review_seed"},
            status="approved",
            source_type="honest_herbalist_hermes_review_seed",
            source_id=slug,
            diff_summary="Seed page for Honest Herbalist Hermes review flow",
        )
    return page


def _run_thread_flow(
    *,
    api_client: TestClient,
    client_id: str,
    product_id: str,
    site_id: str,
    page_id: str,
    title: str,
    objective_type: str,
    first_message: str,
    revision_message: str,
    approval_notes: str,
    report_prefix: str,
    output_path: Path,
    decision_line: str,
) -> dict[str, Any]:
    create_response = api_client.post(
        "/agent-threads",
        json={
            "clientId": client_id,
            "productId": product_id,
            "agentProfile": "copy",
            "objectiveType": objective_type,
            "bundleKey": BUNDLE_KEY,
            "title": title,
            "siteId": site_id,
            "pageId": page_id,
        },
    )
    if create_response.status_code >= 400:
        raise RuntimeError(f"Thread creation failed ({create_response.status_code}): {create_response.text}")
    thread_id = create_response.json()["thread"]["id"]

    first_turn = api_client.post(
        f"/agent-threads/{thread_id}/messages",
        json={"content": first_message},
    )
    if first_turn.status_code >= 400:
        raise RuntimeError(f"First draft failed ({first_turn.status_code}): {first_turn.text}")

    validation_after_first = api_client.get(f"/agent-threads/{thread_id}/validation")
    validation_after_first.raise_for_status()
    first_payload = validation_after_first.json()
    _assert_validation_snapshot(payload=first_payload, expected_run_count=1)
    first_session_id = first_payload["validation"]["runtime"]["hermesSessionId"]

    revision_turn = api_client.post(
        f"/agent-threads/{thread_id}/messages",
        json={"content": revision_message},
    )
    if revision_turn.status_code >= 400:
        raise RuntimeError(f"Revision failed ({revision_turn.status_code}): {revision_turn.text}")

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
            "notes": approval_notes,
        },
    )
    if approval_response.status_code >= 400:
        raise RuntimeError(f"Approval failed ({approval_response.status_code}): {approval_response.text}")

    final_validation = api_client.get(f"/agent-threads/{thread_id}/validation")
    final_validation.raise_for_status()
    final_payload = final_validation.json()
    _assert_validation_snapshot(payload=final_payload, expected_run_count=2, require_approval=True)

    step_reports = _step_reports(final_payload)
    latest_output = step_reports[-1]["assistantOutput"] or ""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(latest_output.rstrip() + "\n", encoding="utf-8")

    thread_prefix = f"{report_prefix}-{thread_id}"
    json_report_path = output_path.parent.parent / f"{thread_prefix}.json"
    markdown_report_path = output_path.parent.parent / f"{thread_prefix}.md"
    html_report_path = output_path.parent.parent / f"{thread_prefix}.html"

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
            "outputPath": str(output_path),
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
            decision_line=decision_line,
        ),
        encoding="utf-8",
    )
    html_report_path.write_text(
        _build_html_report(payload=final_payload, step_reports=step_reports),
        encoding="utf-8",
    )

    return {
        "threadId": thread_id,
        "pageId": page_id,
        "objectiveType": objective_type,
        "model": final_payload["validation"]["runtime"]["model"],
        "hermesSessionId": final_payload["validation"]["runtime"]["hermesSessionId"],
        "sessionReusedAcrossRevision": first_session_id == revision_session_id,
        "outputPath": str(output_path),
        "reportJson": str(json_report_path),
        "reportMarkdown": str(markdown_report_path),
        "reportHtml": str(html_report_path),
        "pageVersionId": latest_page_version_id,
    }


def _build_summary_markdown(
    *,
    generated_at: str,
    client_id: str,
    product_id: str,
    site_id: str,
    presell_result: dict[str, Any],
    sales_result: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Honest Herbalist Hermes Review Run",
            "",
            "## Decision",
            "Completed the real local Honest Herbalist Hermes sidecar run on Anthropic Haiku and persisted both Ember-shaped output documents for review.",
            "",
            "## Workspace",
            f"- Generated at: `{generated_at}`",
            f"- Client ID: `{client_id}`",
            f"- Product ID: `{product_id}`",
            f"- Site ID: `{site_id}`",
            f"- Bundle key: `{BUNDLE_KEY}`",
            "",
            "## Output Documents",
            f"- Presell advertorial: `{presell_result['outputPath']}`",
            f"- Sales page: `{sales_result['outputPath']}`",
            "",
            "## Review Reports",
            f"- Presell HTML: `{presell_result['reportHtml']}`",
            f"- Presell JSON: `{presell_result['reportJson']}`",
            f"- Sales HTML: `{sales_result['reportHtml']}`",
            f"- Sales JSON: `{sales_result['reportJson']}`",
            "",
            "## Runtime",
            f"- Presell session: `{presell_result['hermesSessionId']}`",
            f"- Sales session: `{sales_result['hermesSessionId']}`",
            f"- Model: `{presell_result['model']}`",
        ]
    )


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = REPORTS_ROOT / f"honest-herbalist-run-{timestamp}"
    pages_root = run_root / "pages"
    run_root.mkdir(parents=True, exist_ok=True)
    pages_root.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    auth_context: AuthContext | None = None
    try:
        client, product, site = _load_workspace(session)
        sites_repo = SitesRuntimeRepository(session)
        presell_page = _ensure_review_page(
            sites_repo=sites_repo,
            site=site,
            slug="interaction-first-safety-checker",
            name="Interaction-First Safety Checker",
            page_type="advertorial",
            page_role="presell",
            seed_body="Seed review page for the Honest Herbalist presell advertorial flow.",
        )
        sales_page = _ensure_review_page(
            sites_repo=sites_repo,
            site=site,
            slug="honest-herbalist-handbook-sales-page",
            name="Honest Herbalist Handbook Sales Page",
            page_type="sales_page",
            page_role="sales_page",
            seed_body="Seed review page for the Honest Herbalist sales page flow.",
        )
        session.commit()

        auth_context = AuthContext(
            user_id="hermes-honest-herbalist-review-user",
            org_id=str(client.org_id),
        )

        def get_session_override():
            try:
                yield session
            finally:
                pass

        def get_user_override():
            return auth_context

        app.dependency_overrides[get_session] = get_session_override
        app.dependency_overrides[get_current_user] = get_user_override

        with TestClient(app) as api_client:
            presell_result = _run_thread_flow(
                api_client=api_client,
                client_id=str(client.id),
                product_id=str(product.id),
                site_id=str(site.id),
                page_id=str(presell_page.id),
                title="Honest Herbalist presell review flow",
                objective_type="presell_page_draft",
                first_message=(
                    "Create a full presell advertorial for The Honest Herbalist Handbook. "
                    "Use the Honest Herbalist foundational docs, approved headlines, promise contract, and worked-example files in the active bundle. "
                    "Stay inside the interaction-first / contraindications-first safety angle, keep the safety-first voice, and return markdown only with a single H1."
                ),
                revision_message=(
                    "Revise the same presell advertorial. Keep the H1, preserve the core interaction-first angle, "
                    "shorten paragraph length, tighten transitions, and make the draft feel ready for human approval. Return markdown only."
                ),
                approval_notes="Approved local Honest Herbalist presell review run",
                report_prefix="honest-herbalist-presell-validation",
                output_path=pages_root / PRESALE_OUTPUT_NAME,
                decision_line=(
                    "Validated the local Hermes sidecar conversational path for Honest Herbalist and persisted a presell advertorial through draft, revision, and approval."
                ),
            )

            sales_result = _run_thread_flow(
                api_client=api_client,
                client_id=str(client.id),
                product_id=str(product.id),
                site_id=str(site.id),
                page_id=str(sales_page.id),
                title="Honest Herbalist sales page review flow",
                objective_type="sales_page_draft",
                first_message=(
                    "Create a full sales page for The Honest Herbalist Handbook. "
                    "Use the Honest Herbalist foundational docs, offer brief, brand/compliance context, promise contract, and worked-example sales page in the active bundle. "
                    "Stay grounded in the same interaction-first / contraindications-first angle, include the core handbook plus the documented bonus stack, and return markdown only with a single H1."
                ),
                revision_message=(
                    "Revise the same sales page. Keep the H1, preserve the calm safety-first voice, "
                    "tighten repetition, sharpen the offer section and CTA clarity, and keep every claim source-grounded. Return markdown only."
                ),
                approval_notes="Approved local Honest Herbalist sales page review run",
                report_prefix="honest-herbalist-sales-validation",
                output_path=pages_root / SALES_OUTPUT_NAME,
                decision_line=(
                    "Validated the local Hermes sidecar conversational path for Honest Herbalist and persisted a sales page through draft, revision, and approval."
                ),
            )

        generated_at = datetime.now(timezone.utc).isoformat()
        summary = {
            "generatedAt": generated_at,
            "bundleKey": BUNDLE_KEY,
            "clientId": str(client.id),
            "productId": str(product.id),
            "siteId": str(site.id),
            "presell": presell_result,
            "sales": sales_result,
        }
        summary_json_path = run_root / "honest-herbalist-run-summary.json"
        summary_md_path = run_root / "honest-herbalist-run-summary.md"
        summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary_md_path.write_text(
            _build_summary_markdown(
                generated_at=generated_at,
                client_id=str(client.id),
                product_id=str(product.id),
                site_id=str(site.id),
                presell_result=presell_result,
                sales_result=sales_result,
            ),
            encoding="utf-8",
        )

        print(
            json.dumps(
                {
                    "bundleKey": BUNDLE_KEY,
                    "clientId": str(client.id),
                    "productId": str(product.id),
                    "siteId": str(site.id),
                    "summaryJson": str(summary_json_path),
                    "summaryMarkdown": str(summary_md_path),
                    "presellOutput": presell_result["outputPath"],
                    "salesOutput": sales_result["outputPath"],
                    "presellReportHtml": presell_result["reportHtml"],
                    "salesReportHtml": sales_result["reportHtml"],
                },
                indent=2,
            )
        )
    finally:
        app.dependency_overrides.clear()
        session.close()


if __name__ == "__main__":
    main()
