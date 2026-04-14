#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from fastapi.testclient import TestClient
from sqlalchemy import select

SCRIPT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import AuthContext, get_current_user  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.deps import get_session  # noqa: E402
from app.db.models import Client, Product, SiteTemplate  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ember_skills_flow import EmberSkillsFlowService  # noqa: E402
from app.services.product_strategy_bundles import ProductStrategyBundlesService  # noqa: E402
from app.services.skills_runtime_registry import (  # noqa: E402
    DEFAULT_SKILL_BUNDLE_KEY,
    SkillsRuntimeRegistryService,
)


WORKSPACE_NAME = "Ember Gummies"
PRODUCT_TITLE = "Ember: Brain Clarity Protocol"
TEMPLATE_NAME = "Honest Herbalist One Product Final"
DEFAULT_RELEASE_VERSION = "2026-04-01-ember-skills-hermes-v1"
DEFAULT_STRATEGY_ROOT = REPO_ROOT.parent / "mos_strategy_v3"
DEFAULT_FOUNDATIONAL_ROOT = (
    DEFAULT_STRATEGY_ROOT
    / "FutrGroup-Hookd-Project"
    / "EMBER"
    / "prod-sync"
    / "foundational"
    / "content"
)
REPORTS_ROOT = REPO_ROOT / ".local" / "hermes" / "ember-skills-validation"
PREVIEW_SCRIPT = REPO_ROOT / "mos" / "frontend" / "scripts" / "validate-site-preview.mjs"
LOCAL_DATABASE_URL = "postgresql+psycopg2://app:app@localhost:5433/app"
LOCAL_BACKEND_URL = "http://127.0.0.1:8008"
LOCAL_FRONTEND_URL = "http://127.0.0.1:5275"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the EMBER skills + Hermes local validation flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Import skills release, bind it, and seed foundational bundles.")
    bootstrap.add_argument("--release-version", default=DEFAULT_RELEASE_VERSION)
    bootstrap.add_argument("--strategy-root", default=str(DEFAULT_STRATEGY_ROOT))
    bootstrap.add_argument("--foundational-root", default=str(DEFAULT_FOUNDATIONAL_ROOT))

    approve_foundation = subparsers.add_parser(
        "approve-foundation",
        help="Approve the active foundational bundle and seed the initial working/handoff bundles.",
    )
    approve_foundation.add_argument("--allow-incomplete", action="store_true")

    stage = subparsers.add_parser("stage", help="Run one EMBER strategy stage.")
    stage.add_argument("--stage-key", required=True, choices=[
        "signal_report",
        "angle_library",
        "knowledge_base",
        "cso",
        "offer_document",
        "headline_pool",
        "presell_page",
        "sales_page",
    ])

    select_angle = subparsers.add_parser("select-angle", help="Create the angle selection artifact.")
    select_angle.add_argument("--angle-id", required=True)
    select_angle.add_argument("--rationale", required=True)

    select_headline = subparsers.add_parser("select-headline", help="Create the headline selection artifact.")
    select_headline.add_argument("--headline-id", required=True)
    select_headline.add_argument("--rationale", required=True)

    approve_role = subparsers.add_parser("approve-role", help="Create a pending approved handoff bundle from the active working role.")
    approve_role.add_argument("--role", required=True)

    activate_handoff = subparsers.add_parser("activate-handoff", help="Activate a pending approved handoff bundle.")
    activate_handoff.add_argument("--bundle-id", required=True)

    status = subparsers.add_parser("status", help="Print the active foundational and working bundles.")

    page_copy = subparsers.add_parser("page-copy", help="Instantiate the template and run Hermes page-copy.")
    page_copy.add_argument("--base-url", default="http://localhost:5275")
    page_copy.add_argument("--country", default="us")

    return parser.parse_args()


def _load_workspace(session) -> tuple[Client, Product]:
    client_candidates = list(
        session.scalars(
            select(Client)
            .where(Client.name == WORKSPACE_NAME)
            .order_by(Client.created_at.desc())
        ).all()
    )
    if not client_candidates:
        raise RuntimeError(f"Could not find workspace '{WORKSPACE_NAME}' in the local database.")

    for client in client_candidates:
        product = session.scalars(
            select(Product).where(
                Product.client_id == client.id,
                Product.title == PRODUCT_TITLE,
            )
        ).first()
        if product:
            return client, product
    raise RuntimeError(
        f"Found '{WORKSPACE_NAME}' workspaces, but none had the '{PRODUCT_TITLE}' product."
    )


def _load_template(session) -> SiteTemplate:
    template = session.scalars(
        select(SiteTemplate)
        .where(SiteTemplate.name == TEMPLATE_NAME)
        .order_by(SiteTemplate.created_at.desc())
    ).first()
    if template is None:
        raise RuntimeError(f"Could not find site template '{TEMPLATE_NAME}' in the local database.")
    return template


def _bundle_service(*, session, client: Client, product: Product) -> ProductStrategyBundlesService:
    return ProductStrategyBundlesService(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        product_id=str(product.id),
        created_by_user="script:ember-skills-validation",
    )


def _runtime_service(*, session, client: Client, product: Product) -> SkillsRuntimeRegistryService:
    return SkillsRuntimeRegistryService(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        product_id=str(product.id),
        created_by_user="script:ember-skills-validation",
    )


def _flow_service(*, session, client: Client, product: Product) -> EmberSkillsFlowService:
    return EmberSkillsFlowService(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        product_id=str(product.id),
        created_by_user="script:ember-skills-validation",
    )


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _is_local_url(value: str) -> bool:
    return value.startswith("http://localhost:") or value.startswith("http://127.0.0.1:")


def _normalized_local_base_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    host = parsed.hostname or ""
    if host not in {"localhost", "127.0.0.1"}:
        return value.rstrip("/")
    port = parsed.port or 80
    return f"http://127.0.0.1:{port}"


def _port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_http(
    url: str,
    *,
    timeout_seconds: float,
    label: str,
    process: subprocess.Popen[str] | None = None,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"{label} exited early with code {process.returncode}.")
        try:
            with urlopen(url, timeout=2):  # noqa: S310 - local health checks only
                return
        except URLError:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {label} at {url}.")


@contextmanager
def _launch_local_preview_stack(*, run_dir: Path, requested_base_url: str):
    normalized_base_url = _normalized_local_base_url(requested_base_url)
    if not _is_local_url(normalized_base_url):
        yield {"baseUrl": normalized_base_url, "startedBackend": False, "startedFrontend": False}
        return

    backend_host = "127.0.0.1"
    backend_port = 8008
    frontend_host = "127.0.0.1"
    frontend_port = 5275
    if normalized_base_url != LOCAL_FRONTEND_URL:
        raise RuntimeError(
            "The local preview stack launcher only supports "
            f"{LOCAL_FRONTEND_URL}. Received baseUrl={normalized_base_url!r}."
        )

    started_processes: list[subprocess.Popen[str]] = []
    backend_log = run_dir / "backend.log"
    frontend_log = run_dir / "frontend.log"
    started_backend = False
    started_frontend = False
    reused_backend = False
    reused_frontend = False

    with ExitStack() as stack:
        if _port_is_listening(backend_host, backend_port):
            reused_backend = True
            _wait_for_http(
                f"{LOCAL_BACKEND_URL}/health",
                timeout_seconds=30,
                label="running local backend",
            )
        else:
            backend_handle = stack.enter_context(backend_log.open("w", encoding="utf-8"))
            backend_env = os.environ.copy()
            backend_env["DATABASE_URL"] = LOCAL_DATABASE_URL
            backend = subprocess.Popen(
                [
                    ".venv/bin/python",
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    backend_host,
                    "--port",
                    str(backend_port),
                ],
                cwd=str(BACKEND_ROOT),
                env=backend_env,
                stdout=backend_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            started_processes.append(backend)
            started_backend = True
            _wait_for_http(
                f"{LOCAL_BACKEND_URL}/health",
                timeout_seconds=60,
                process=backend,
                label="local backend",
            )

        if _port_is_listening(frontend_host, frontend_port):
            reused_frontend = True
            _wait_for_http(
                LOCAL_FRONTEND_URL,
                timeout_seconds=45,
                label="running local frontend",
            )
        else:
            frontend_handle = stack.enter_context(frontend_log.open("w", encoding="utf-8"))
            frontend_env = os.environ.copy()
            frontend = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host", frontend_host, "--port", str(frontend_port)],
                cwd=str(REPO_ROOT / "mos" / "frontend"),
                env=frontend_env,
                stdout=frontend_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            started_processes.append(frontend)
            started_frontend = True
            _wait_for_http(
                LOCAL_FRONTEND_URL,
                timeout_seconds=90,
                process=frontend,
                label="local frontend",
            )

        try:
            yield {
                "baseUrl": LOCAL_FRONTEND_URL,
                "startedBackend": started_backend,
                "startedFrontend": started_frontend,
                "reusedBackend": reused_backend,
                "reusedFrontend": reused_frontend,
                "backendLog": str(backend_log) if started_backend else None,
                "frontendLog": str(frontend_log) if started_frontend else None,
            }
        finally:
            for process in reversed(started_processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


def _run_bootstrap(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        runtime = _runtime_service(session=session, client=client, product=product)
        release = runtime.sync_ember_skills_release(
            strategy_root=Path(args.strategy_root),
            version=args.release_version,
        )
        binding = runtime.ensure_workspace_binding(release_id=release["releaseId"])

        bundles = _bundle_service(session=session, client=client, product=product)
        foundational = bundles.import_foundational_bundle(
            source_dir=Path(args.foundational_root),
            title="EMBER Foundational Docs",
            doc_key_prefix="foundational",
        )
        _print(
            {
                "workspaceId": str(client.id),
                "productId": str(product.id),
                "release": release,
                "binding": binding,
                "foundationalBundle": foundational,
            }
        )
    finally:
        session.close()


def _run_stage(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.run_stage(stage_key=args.stage_key)
        _print(result)
    finally:
        session.close()


def _run_approve_foundation(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.seed_working_bundle_from_foundation(allow_incomplete=bool(args.allow_incomplete))
        _print(result)
    finally:
        session.close()


def _run_select_angle(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.select_angle(angle_id=args.angle_id, rationale=args.rationale)
        _print(result)
    finally:
        session.close()


def _run_select_headline(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.select_headline(headline_id=args.headline_id, rationale=args.rationale)
        _print(result)
    finally:
        session.close()


def _run_status() -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        bundles = _bundle_service(session=session, client=client, product=product)
        foundational = bundles.get_active_bundle(bundle_type="foundational_docs")
        working = bundles.get_active_bundle(bundle_type="skills_working")
        handoff = bundles.get_active_bundle(bundle_type="skills_handoff")
        pending_handoffs = [
            bundle
            for bundle in bundles.list_bundles(bundle_type="skills_handoff")
            if not bool(bundle.get("isActive"))
        ]
        _print(
            {
                "workspaceId": str(client.id),
                "productId": str(product.id),
                "foundationalBundle": foundational,
                "workingBundle": working,
                "handoffBundle": handoff,
                "pendingHandoffBundles": pending_handoffs,
            }
        )
    finally:
        session.close()


def _run_approve_role(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.approve_working_role(role=args.role)
        _print(result)
    finally:
        session.close()


def _run_activate_handoff(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        flow = _flow_service(session=session, client=client, product=product)
        result = flow.activate_handoff_bundle(bundle_id=args.bundle_id)
        _print(result)
    finally:
        session.close()


def _instantiate_site(
    *,
    api_client: TestClient,
    client_id: str,
    product_id: str,
    template_id: str,
    run_label: str,
) -> dict[str, Any]:
    response = api_client.post(
        f"/site-templates/{template_id}/instantiate?clientId={client_id}",
        json={
            "clientId": client_id,
            "productId": product_id,
            "name": f"EMBER Skills Validation {run_label}",
            "description": "Hermes sidecar validation run against the EMBER product strategy bundle.",
        },
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Template instantiation failed ({response.status_code}): {response.text}"
        )
    payload = response.json()
    site_id = payload["siteId"]
    site_detail = api_client.get(f"/sites/{site_id}?clientId={client_id}")
    if site_detail.status_code >= 400:
        raise RuntimeError(
            f"Loading instantiated site failed ({site_detail.status_code}): {site_detail.text}"
        )
    site = site_detail.json()
    entry_page_id = site.get("entryPageId")
    if not entry_page_id:
        raise RuntimeError("Instantiated site did not return an entryPageId.")
    return {
        "siteId": site_id,
        "site": site,
        "entryPageId": entry_page_id,
    }


def _run_page_copy(args: argparse.Namespace) -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        template = _load_template(session)
        bundles = _bundle_service(session=session, client=client, product=product)
        handoff = bundles.get_active_bundle(bundle_type="skills_handoff")

        auth_context = AuthContext(
            user_id="ember-skills-validation-user",
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

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()
        run_dir = REPORTS_ROOT / f"ember-skills-page-copy-{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        with _launch_local_preview_stack(run_dir=run_dir, requested_base_url=args.base_url) as stack_info:
            with TestClient(app) as api_client:
                instantiation = _instantiate_site(
                    api_client=api_client,
                    client_id=str(client.id),
                    product_id=str(product.id),
                    template_id=str(template.id),
                    run_label=timestamp,
                )

                create_thread_response = api_client.post(
                    "/agent-threads",
                    json={
                        "clientId": str(client.id),
                        "productId": str(product.id),
                        "agentProfile": "copy",
                        "objectiveType": "page_copy_agent",
                        "bundleKey": DEFAULT_SKILL_BUNDLE_KEY,
                        "runtimeProfileKey": "page-copy",
                        "strategyBundleId": handoff["id"],
                        "title": "EMBER one-product-store page-copy validation",
                        "siteId": instantiation["siteId"],
                        "pageId": instantiation["entryPageId"],
                    },
                )
                if create_thread_response.status_code >= 400:
                    raise RuntimeError(
                        f"Agent thread creation failed ({create_thread_response.status_code}): {create_thread_response.text}"
                    )
                thread_id = create_thread_response.json()["thread"]["id"]

                first_turn = api_client.post(
                    f"/agent-threads/{thread_id}/messages",
                    json={
                        "content": (
                            "Rewrite this one-product store home page for Ember: Brain Clarity Protocol. "
                            "Use the active approved strategy bundle as the source of truth. "
                            "Preserve the imported page structure and rewrite copy slots only. "
                            "Keep the hero CTA concise and review-friendly. "
                            "Do not invent prices, testimonials, scientific claims, or guarantees."
                        )
                    },
                )
                if first_turn.status_code >= 400:
                    raise RuntimeError(
                        f"First page-copy turn failed ({first_turn.status_code}): {first_turn.text}"
                    )

                revision_turn = api_client.post(
                    f"/agent-threads/{thread_id}/messages",
                    json={
                        "content": (
                            "Revise the same page. Tighten the above-the-fold clarity, improve flow into the purchase section, "
                            "and keep the CTA and benefit language grounded in the approved strategy bundle."
                        )
                    },
                )
                if revision_turn.status_code >= 400:
                    raise RuntimeError(
                        f"Revision page-copy turn failed ({revision_turn.status_code}): {revision_turn.text}"
                    )

                validation_response = api_client.get(f"/agent-threads/{thread_id}/validation")
                validation_response.raise_for_status()
                validation_payload = validation_response.json()
                latest_run = validation_payload["validation"]["runs"][-1]
                page_version = latest_run.get("sitePageVersion") or {}
                page_version_id = page_version.get("id")
                if not page_version_id:
                    raise RuntimeError("Latest page-copy validation run did not expose a draft site page version.")

                approval_response = api_client.post(
                    f"/agent-threads/{thread_id}/approve",
                    json={
                        "targetKind": "site_page_version",
                        "targetId": page_version_id,
                        "decision": "approved",
                        "notes": "Approved EMBER page-copy validation draft for preview verification.",
                    },
                )
                if approval_response.status_code >= 400:
                    raise RuntimeError(
                        f"Approving the page-copy draft failed ({approval_response.status_code}): {approval_response.text}"
                    )

                publish_response = api_client.post(
                    f"/sites/{instantiation['siteId']}/publish?clientId={client.id}"
                )
                if publish_response.status_code >= 400:
                    raise RuntimeError(
                        f"Publishing the instantiated site failed ({publish_response.status_code}): {publish_response.text}"
                    )

            preview_validation = subprocess.run(
                [
                    "node",
                    str(PREVIEW_SCRIPT),
                    "--site-id",
                    instantiation["siteId"],
                    "--base-url",
                    stack_info["baseUrl"],
                    "--country",
                    args.country,
                ],
                cwd=str(REPO_ROOT / "mos" / "frontend"),
                capture_output=True,
                text=True,
                check=False,
            )
            if preview_validation.returncode != 0:
                raise RuntimeError(
                    "Preview validation failed:\n"
                    + (preview_validation.stdout or "")
                    + "\n"
                    + (preview_validation.stderr or "")
                )

            report_path = run_dir / "page-copy-validation.json"
            report_payload = {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "workspaceId": str(client.id),
                "productId": str(product.id),
                "templateId": str(template.id),
                "siteId": instantiation["siteId"],
                "entryPageId": instantiation["entryPageId"],
                "threadId": thread_id,
                "strategyBundleId": handoff["id"],
                "previewBaseUrl": stack_info["baseUrl"],
                "previewStack": stack_info,
                "previewValidation": json.loads(preview_validation.stdout),
            }
            report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
            _print(report_payload)
    finally:
        app.dependency_overrides.clear()
        session.close()


def main() -> None:
    args = _parse_args()
    if args.command == "bootstrap":
        _run_bootstrap(args)
        return
    if args.command == "approve-foundation":
        _run_approve_foundation(args)
        return
    if args.command == "stage":
        _run_stage(args)
        return
    if args.command == "select-angle":
        _run_select_angle(args)
        return
    if args.command == "select-headline":
        _run_select_headline(args)
        return
    if args.command == "approve-role":
        _run_approve_role(args)
        return
    if args.command == "activate-handoff":
        _run_activate_handoff(args)
        return
    if args.command == "status":
        _run_status()
        return
    if args.command == "page-copy":
        _run_page_copy(args)
        return
    raise RuntimeError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
