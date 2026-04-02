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
REPORTS_ROOT = REPO_ROOT / ".local" / "hermes" / "page-agent-reports"
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
from app.db.models import Client, Product, Site, SiteTemplate  # noqa: E402
from app.main import app  # noqa: E402


BUNDLE_KEY = "honest_herbalist_v1"
PAGE_AGENT_OBJECTIVE_TYPE = "page_copy_agent"
SOURCE_SITE_NAME = "OMNI Creatine Gummy"
ONE_PRODUCT_TEMPLATE_NAME = "OMNI One Product Store"
OUTPUT_PUCK_NAME = "HONEST-HERBALIST-ONE-PRODUCT-STORE-HOME.json"
OUTPUT_SUMMARY_NAME = "HONEST-HERBALIST-ONE-PRODUCT-STORE-HOME-SUMMARY.json"
OUTPUT_ASSIGNMENTS_NAME = "HONEST-HERBALIST-ONE-PRODUCT-STORE-HOME-SLOT-ASSIGNMENTS.json"


def _load_workspace(session) -> tuple[Client, Product]:
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
        if product:
            return client, product

    raise RuntimeError(
        "Found Honest Herbalist workspaces, but none had the handbook product needed for the page-agent run."
    )


def _load_source_site(session, *, client_id: str) -> Site:
    source_site = session.scalars(
        select(Site)
        .where(
            Site.client_id == client_id,
            Site.name == SOURCE_SITE_NAME,
        )
        .order_by(Site.created_at.desc())
    ).first()
    if source_site is None:
        raise RuntimeError(f"Could not find source site '{SOURCE_SITE_NAME}' in the local database.")
    if not source_site.site_import_id:
        raise RuntimeError(f"Source site '{SOURCE_SITE_NAME}' is missing its import provenance.")
    return source_site


def _find_existing_one_product_template(session, *, source_site_id: str) -> SiteTemplate | None:
    source_note = f"source_site_id:{source_site_id}"
    mode_note = "template_mode:medusa_one_product_store"
    templates = session.scalars(select(SiteTemplate).order_by(SiteTemplate.created_at.desc())).all()
    for template in templates:
        notes = template.provenance_notes or []
        if source_note in notes and mode_note in notes:
            return template
    return None


def _ensure_one_product_template(
    *,
    api_client: TestClient,
    session,
    client_id: str,
    source_site_id: str,
) -> dict[str, Any]:
    existing = _find_existing_one_product_template(session, source_site_id=source_site_id)
    if existing is not None:
        return {
            "id": str(existing.id),
            "name": existing.name,
            "family": existing.family,
        }

    response = api_client.post(
        f"/sites/{source_site_id}/create-template?clientId={client_id}",
        json={
            "name": ONE_PRODUCT_TEMPLATE_NAME,
            "description": "Imported OMNI one-product store template for Hermes copy-agent validation.",
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Creating the one-product store template failed ({response.status_code}): {response.text}"
        )
    return response.json()


def _instantiate_one_product_site(
    *,
    api_client: TestClient,
    template_id: str,
    client_id: str,
    product_id: str,
    run_label: str,
) -> dict[str, Any]:
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate",
        json={
            "clientId": client_id,
            "name": f"Honest Herbalist One Product Store {run_label}",
            "description": "Hermes sidecar page-agent validation run on the OMNI one-product template.",
            "productId": product_id,
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Instantiating the one-product store template failed ({response.status_code}): {response.text}"
        )
    site_payload = response.json()
    site_id = site_payload["siteId"]

    site_detail = api_client.get(f"/sites/{site_id}?clientId={client_id}")
    if site_detail.status_code >= 400:
        raise RuntimeError(
            f"Loading instantiated site detail failed ({site_detail.status_code}): {site_detail.text}"
        )
    site = site_detail.json()
    entry_page_id = site.get("entryPageId")
    if not entry_page_id:
        raise RuntimeError("Instantiated site did not return an entryPageId.")
    entry_page = next((page for page in site.get("pages") or [] if page.get("id") == entry_page_id), None)
    if entry_page is None:
        raise RuntimeError("Instantiated site entry page was not found in site detail payload.")

    return {
        "site": site,
        "siteId": site_id,
        "entryPageId": entry_page_id,
        "entryPage": entry_page,
    }


def _run_page_thread_flow(
    *,
    api_client: TestClient,
    client_id: str,
    product_id: str,
    site_id: str,
    page_id: str,
    report_root: Path,
) -> dict[str, Any]:
    create_response = api_client.post(
        "/agent-threads",
        json={
            "clientId": client_id,
            "productId": product_id,
            "agentProfile": "copy",
            "objectiveType": PAGE_AGENT_OBJECTIVE_TYPE,
            "bundleKey": BUNDLE_KEY,
            "title": "Honest Herbalist one-product store copy agent",
            "siteId": site_id,
            "pageId": page_id,
        },
    )
    if create_response.status_code >= 400:
        raise RuntimeError(f"Thread creation failed ({create_response.status_code}): {create_response.text}")
    thread_id = create_response.json()["thread"]["id"]

    first_turn = api_client.post(
        f"/agent-threads/{thread_id}/messages",
        json={
            "content": (
                "Rewrite this one-product store home page for The Honest Herbalist Handbook. "
                "Use the Honest Herbalist foundational docs, shared context, offer framing, approved headlines, and worked examples from the active bundle. "
                "Preserve the imported page structure and existing runtime sections, but replace the OMNI/creatine-specific copy with honest-herbalist-specific copy that stays source-grounded. "
                "Do not invent prices, testimonials, scientific claims, or guarantees that are not present in the bundle."
            )
        },
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
        json={
            "content": (
                "Revise the same page. Keep the imported layout and runtime sections intact, make the safety-first positioning clearer above the fold, "
                "tighten the CTA language, and make the section-to-section flow feel ready for human review. Keep every claim source-grounded."
            )
        },
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
    latest_page_version = latest_run.get("sitePageVersion") or {}
    latest_page_version_id = latest_page_version.get("id")
    if not latest_page_version_id:
        raise RuntimeError("Latest validation run did not expose a draft site page version.")

    approval_response = api_client.post(
        f"/agent-threads/{thread_id}/approve",
        json={
            "targetKind": "site_page_version",
            "targetId": latest_page_version_id,
            "decision": "approved",
            "notes": "Approved Honest Herbalist one-product store copy-agent validation run",
        },
    )
    if approval_response.status_code >= 400:
        raise RuntimeError(f"Approval failed ({approval_response.status_code}): {approval_response.text}")

    final_validation = api_client.get(f"/agent-threads/{thread_id}/validation")
    final_validation.raise_for_status()
    final_payload = final_validation.json()
    _assert_validation_snapshot(payload=final_payload, expected_run_count=2, require_approval=True)

    step_reports = _step_reports(final_payload)
    latest_step = step_reports[-1]
    if latest_step.get("outputMode") != "page_copy_slots":
        raise RuntimeError(
            f"Expected page_copy_slots output mode for the final step, found {latest_step.get('outputMode')}."
        )

    final_puck_data = latest_step.get("pageDraftPuckData")
    if not isinstance(final_puck_data, dict):
        raise RuntimeError("Final step did not include persisted page puckData.")

    final_page_summary = latest_step.get("pageDraftSummary")
    final_slot_assignments = latest_step.get("slotAssignments") or []

    outputs_root = report_root / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    output_puck_path = outputs_root / OUTPUT_PUCK_NAME
    output_summary_path = outputs_root / OUTPUT_SUMMARY_NAME
    output_assignments_path = outputs_root / OUTPUT_ASSIGNMENTS_NAME
    output_puck_path.write_text(json.dumps(final_puck_data, indent=2), encoding="utf-8")
    output_summary_path.write_text(json.dumps(final_page_summary or {}, indent=2), encoding="utf-8")
    output_assignments_path.write_text(json.dumps(final_slot_assignments, indent=2), encoding="utf-8")

    report_prefix = f"honest-herbalist-page-agent-validation-{thread_id}"
    json_report_path = report_root / f"{report_prefix}.json"
    markdown_report_path = report_root / f"{report_prefix}.md"
    html_report_path = report_root / f"{report_prefix}.html"

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
            "outputPuckPath": str(output_puck_path),
            "outputSummaryPath": str(output_summary_path),
            "outputAssignmentsPath": str(output_assignments_path),
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
                "Validated the Hermes sidecar page-agent flow on a real OMNI-derived one-product store template instantiated for Honest Herbalist."
            ),
        ),
        encoding="utf-8",
    )
    html_report_path.write_text(
        _build_html_report(payload=final_payload, step_reports=step_reports),
        encoding="utf-8",
    )

    return {
        "threadId": thread_id,
        "siteId": site_id,
        "pageId": page_id,
        "model": final_payload["validation"]["runtime"]["model"],
        "hermesSessionId": final_payload["validation"]["runtime"]["hermesSessionId"],
        "outputPuckPath": str(output_puck_path),
        "outputSummaryPath": str(output_summary_path),
        "outputAssignmentsPath": str(output_assignments_path),
        "reportJson": str(json_report_path),
        "reportMarkdown": str(markdown_report_path),
        "reportHtml": str(html_report_path),
    }


def _build_summary_markdown(
    *,
    generated_at: str,
    client_id: str,
    product_id: str,
    source_site_id: str,
    template_id: str,
    instantiated_site_id: str,
    entry_page_id: str,
    run_result: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Honest Herbalist Page-Agent Review Run",
            "",
            "## Decision",
            "Completed the Hermes sidecar page-agent validation on an OMNI-derived one-product store template instantiated for Honest Herbalist.",
            "",
            "## Workspace",
            f"- Generated at: `{generated_at}`",
            f"- Client ID: `{client_id}`",
            f"- Product ID: `{product_id}`",
            f"- Source site ID: `{source_site_id}`",
            f"- Template ID: `{template_id}`",
            f"- Instantiated site ID: `{instantiated_site_id}`",
            f"- Entry page ID: `{entry_page_id}`",
            f"- Bundle key: `{BUNDLE_KEY}`",
            "",
            "## Review Artifacts",
            f"- Page puckData: `{run_result['outputPuckPath']}`",
            f"- Page summary: `{run_result['outputSummaryPath']}`",
            f"- Slot assignments: `{run_result['outputAssignmentsPath']}`",
            f"- HTML report: `{run_result['reportHtml']}`",
            f"- JSON report: `{run_result['reportJson']}`",
            "",
            "## Runtime",
            f"- Thread ID: `{run_result['threadId']}`",
            f"- Hermes session: `{run_result['hermesSessionId']}`",
            f"- Model: `{run_result['model']}`",
        ]
    )


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = REPORTS_ROOT / f"honest-herbalist-page-agent-{timestamp}"
    run_root.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        source_site = _load_source_site(session, client_id=str(client.id))

        auth_context = AuthContext(
            user_id="hermes-page-agent-review-user",
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
            template = _ensure_one_product_template(
                api_client=api_client,
                session=session,
                client_id=str(client.id),
                source_site_id=str(source_site.id),
            )
            instantiation = _instantiate_one_product_site(
                api_client=api_client,
                template_id=template["id"],
                client_id=str(client.id),
                product_id=str(product.id),
                run_label=timestamp.lower(),
            )
            run_result = _run_page_thread_flow(
                api_client=api_client,
                client_id=str(client.id),
                product_id=str(product.id),
                site_id=instantiation["siteId"],
                page_id=instantiation["entryPageId"],
                report_root=run_root,
            )

        generated_at = datetime.now(timezone.utc).isoformat()
        summary = {
            "generatedAt": generated_at,
            "bundleKey": BUNDLE_KEY,
            "clientId": str(client.id),
            "productId": str(product.id),
            "sourceSiteId": str(source_site.id),
            "templateId": template["id"],
            "instantiatedSiteId": instantiation["siteId"],
            "entryPageId": instantiation["entryPageId"],
            "run": run_result,
        }
        summary_json_path = run_root / "honest-herbalist-page-agent-summary.json"
        summary_md_path = run_root / "honest-herbalist-page-agent-summary.md"
        summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary_md_path.write_text(
            _build_summary_markdown(
                generated_at=generated_at,
                client_id=str(client.id),
                product_id=str(product.id),
                source_site_id=str(source_site.id),
                template_id=template["id"],
                instantiated_site_id=instantiation["siteId"],
                entry_page_id=instantiation["entryPageId"],
                run_result=run_result,
            ),
            encoding="utf-8",
        )

        print(
            json.dumps(
                {
                    "bundleKey": BUNDLE_KEY,
                    "clientId": str(client.id),
                    "productId": str(product.id),
                    "sourceSiteId": str(source_site.id),
                    "templateId": template["id"],
                    "instantiatedSiteId": instantiation["siteId"],
                    "entryPageId": instantiation["entryPageId"],
                    "summaryJson": str(summary_json_path),
                    "summaryMarkdown": str(summary_md_path),
                    "outputPuck": run_result["outputPuckPath"],
                    "outputSummary": run_result["outputSummaryPath"],
                    "outputAssignments": run_result["outputAssignmentsPath"],
                    "reportHtml": run_result["reportHtml"],
                },
                indent=2,
            )
        )
    finally:
        app.dependency_overrides.clear()
        session.close()


if __name__ == "__main__":
    main()
