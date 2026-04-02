from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.auth.dependencies import AuthContext, get_current_user
from app.db.base import engine
from app.db.deps import get_session
from app.db.models import Client, Org, Product
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.main import app


def _seed_imported_template_stub() -> dict:
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
                                            "body": "Starting point for Hermes prototype validation.",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Hermes sidecar smoke flow.")
    parser.add_argument(
        "--message",
        default=(
            "Rewrite the opening third of the EMBER presell advertorial. Keep the dementia-fear angle, "
            "tighten the emotional pacing, and make it cleaner for human review. Return markdown only."
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

    org = Org(id=uuid.uuid4(), name="Hermes Smoke Org")
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
        route_slug=f"ember-prototype-{uuid.uuid4().hex[:8]}",
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
        provenance={"source": "smoke_seed"},
        status="approved",
        source_type="smoke_seed",
        source_id="smoke_seed",
        diff_summary="Seed page for Hermes sidecar smoke test",
    )
    session.commit()

    auth_context = AuthContext(user_id="hermes-smoke-user", org_id=str(org.id))

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
                    "title": "EMBER presell rewrite",
                    "siteId": str(site.id),
                    "pageId": str(page.id),
                },
            )
            create_response.raise_for_status()
            thread_detail = create_response.json()
            thread_id = thread_detail["thread"]["id"]

            message_response = api_client.post(
                f"/agent-threads/{thread_id}/messages",
                json={"content": args.message},
            )
            if message_response.status_code >= 400:
                raise RuntimeError(
                    f"Message request failed ({message_response.status_code}): {message_response.text}"
                )
            thread_detail = message_response.json()

            last_assistant_turn = next(
                turn for turn in reversed(thread_detail["turns"]) if turn["role"] == "assistant"
            )
            assistant_content = (last_assistant_turn.get("content") or "").lstrip()
            if not assistant_content.startswith("# "):
                raise RuntimeError(
                    "Hermes run returned a non-canonical draft. The persisted assistant content did not start with an H1."
                )
            if not last_assistant_turn["sitePageVersionId"]:
                raise RuntimeError("Hermes run did not create a draft SitePageVersion.")
            draft_version = sites_repo.get_version(version_id=last_assistant_turn["sitePageVersionId"])
            if draft_version is None:
                raise RuntimeError("Hermes run returned a draft SitePageVersion id that could not be loaded.")
            draft_body = (
                (
                    (((draft_version.puck_data or {}).get("content") or [{}])[0].get("props") or {})
                    .get("content")
                    or [{}]
                )[0]
                .get("props", {})
                .get("content", [{}])[0]
                .get("props", {})
                .get("body")
            )
            if draft_body != last_assistant_turn["content"]:
                raise RuntimeError(
                    "Hermes run persisted mismatched draft bodies between the assistant turn and SitePageVersion."
                )

            approval_response = api_client.post(
                f"/agent-threads/{thread_id}/approve",
                json={
                    "targetKind": "site_page_version",
                    "targetId": last_assistant_turn["sitePageVersionId"],
                    "decision": "approved",
                    "notes": "Smoke test approval",
                },
            )
            if approval_response.status_code >= 400:
                raise RuntimeError(
                    f"Approval request failed ({approval_response.status_code}): {approval_response.text}"
                )
            final_detail = approval_response.json()
            print(json.dumps(final_detail, indent=2))
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


if __name__ == "__main__":
    main()
