#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import httpx
import json
import os
from pathlib import Path
import re
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
from app.db.models import Client, ClientComplianceProfile, Product, SiteTemplate  # noqa: E402
from app.db.repositories.products import ProductOffersRepository, ProductVariantsRepository  # noqa: E402
from app.main import app  # noqa: E402
from app.services.compliance import list_policy_page_keys, render_policy_template_markdown  # noqa: E402
from app.services.ember_skills_flow import EmberSkillsFlowService  # noqa: E402
from app.services.medusa_catalog import (  # noqa: E402
    create_medusa_variant,
    get_medusa_product,
    update_medusa_variant,
)
from app.services.medusa_connection import (  # noqa: E402
    medusa_admin_login,
    test_medusa_connection,
    upsert_client_medusa_config,
)
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
LOCAL_MEDUSA_BASE_URL = "http://localhost:9000"
LOCAL_MEDUSA_ADMIN_EMAIL = os.environ.get("MEDUSA_ADMIN_EMAIL", "admin@test.com")
LOCAL_MEDUSA_ADMIN_PASSWORD = os.environ.get("MEDUSA_ADMIN_PASSWORD", "supersecret")
_PRICING_LINE_RE = re.compile(
    r"^\*\*(?P<label>.+?):\*\*\s*\$(?P<price>\d+)(?:\s*\(save\s*\$(?P<save>\d+)\))?",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"(?P<days>\d+)\s*day", re.IGNORECASE)
_DAY_TITLE_SUFFIX_RE = re.compile(r"^\s*\d+\s*day\s+(?P<suffix>.+?)\s*$", re.IGNORECASE)


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

    subparsers.add_parser(
        "sync-commerce",
        help="Sync EMBER offer-document pricing into local product variants and Medusa variants.",
    )

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


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_duration_days(value: str) -> int | None:
    match = _DURATION_RE.search(str(value or ""))
    if not match:
        return None
    return int(match.group("days"))


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return normalized.strip("-")


def _selected_variant_suffix(selected_variant_name: str) -> str | None:
    match = _DAY_TITLE_SUFFIX_RE.match(str(selected_variant_name or ""))
    if not match:
        return None
    suffix = match.group("suffix").strip()
    return suffix or None


def _extract_offer_document(bundle: dict[str, Any]) -> dict[str, Any]:
    for item in bundle.get("items", []):
        if str(item.get("role") or "").strip() != "offer_document":
            continue
        artifact_data = item.get("artifactData")
        if not isinstance(artifact_data, dict):
            raise RuntimeError("Offer document artifact payload is missing artifactData.")
        if str(artifact_data.get("documentFormat") or "").strip().lower() != "json":
            raise RuntimeError("Offer document artifact is not stored as JSON.")
        payload = artifact_data.get("json")
        if not isinstance(payload, dict):
            raise RuntimeError("Offer document JSON payload is missing.")
        return payload
    raise RuntimeError("Active skills handoff bundle is missing the offer_document artifact.")


def _parse_offer_variants(offer_document: dict[str, Any]) -> list[dict[str, Any]]:
    offer_markdown = str(offer_document.get("offerDetailsMarkdown") or "").strip()
    if not offer_markdown:
        raise RuntimeError("Offer document is missing offerDetailsMarkdown.")

    selected_variant_name = str(offer_document.get("selectedVariantName") or "").strip()
    selected_variant_id = str(offer_document.get("selectedVariantId") or "").strip()
    title_suffix = _selected_variant_suffix(selected_variant_name)
    selected_variant_days = _extract_duration_days(selected_variant_name)

    variants: list[dict[str, Any]] = []
    for raw_line in offer_markdown.splitlines():
        line = raw_line.strip()
        match = _PRICING_LINE_RE.match(line)
        if not match:
            continue

        source_label = match.group("label").strip()
        price_cents = int(match.group("price")) * 100
        savings_cents = int(match.group("save")) * 100 if match.group("save") else None
        compare_at_cents = price_cents + savings_cents if savings_cents else None
        duration_days = _extract_duration_days(source_label)
        if duration_days and title_suffix:
            title = f"{duration_days} Day {title_suffix}"
        else:
            title = source_label
        if duration_days and selected_variant_days == duration_days and selected_variant_id:
            variant_id = selected_variant_id
        elif duration_days:
            variant_id = f"ember-{duration_days}-day-supply"
        else:
            variant_id = _slugify(title)
        variants.append(
            {
                "id": variant_id,
                "title": title,
                "sourceLabel": source_label,
                "priceCents": price_cents,
                "compareAtCents": compare_at_cents,
                "currency": "USD",
                "durationDays": duration_days,
            }
        )

    if not variants:
        raise RuntimeError("Offer document pricing section did not yield any variants.")

    deduped_by_id: dict[str, dict[str, Any]] = {}
    for variant in variants:
        deduped_by_id[str(variant["id"])] = variant
    return sorted(
        deduped_by_id.values(),
        key=lambda variant: (
            int(variant["durationDays"]) if isinstance(variant.get("durationDays"), int) else 9999,
            int(variant["priceCents"]),
            str(variant["title"]),
        ),
    )


def _resolve_ember_offer_id(*, session, product_id: str) -> str | None:
    offers = ProductOffersRepository(session).list_by_product(product_id=product_id)
    if len(offers) == 1:
        return str(offers[0].id)
    return None


def _find_matching_existing_variant(
    *,
    desired_variant: dict[str, Any],
    existing_rows: list[Any],
    retained_row_ids: set[str],
) -> Any | None:
    desired_offer_id = str(desired_variant["id"]).strip().lower()
    desired_title = _normalize_text(str(desired_variant["title"]))
    desired_days = desired_variant.get("durationDays")

    def row_matches(row: Any) -> bool:
        option_values = row.option_values if isinstance(row.option_values, dict) else {}
        option_offer_id = str(option_values.get("offerId") or "").strip().lower()
        if option_offer_id and option_offer_id == desired_offer_id:
            return True
        row_title = _normalize_text(str(row.title or ""))
        if row_title and row_title == desired_title:
            return True
        row_days = _extract_duration_days(str(row.title or ""))
        if isinstance(desired_days, int) and row_days == desired_days:
            return True
        return False

    for row in existing_rows:
        row_id = str(row.id)
        if row_id in retained_row_ids:
            continue
        if row_matches(row):
            return row

    for row in existing_rows:
        row_id = str(row.id)
        if row_id in retained_row_ids:
            continue
        if str(row.provider or "").strip().lower() == "medusa" and str(row.external_price_id or "").strip():
            return row
    return None


def _ensure_local_medusa_admin_token(*, session, client: Client) -> dict[str, Any]:
    status = test_medusa_connection(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
    )
    session.commit()
    if status.state == "connected":
        return {"refreshed": False, "state": status.state, "message": status.message}

    base_url = str(status.base_url or LOCAL_MEDUSA_BASE_URL).rstrip("/")
    if base_url not in {LOCAL_MEDUSA_BASE_URL, "http://127.0.0.1:9000"}:
        raise RuntimeError(
            "Medusa admin authentication failed and the workspace is not pointed at the local Medusa dev instance. "
            f"base_url={base_url!r} message={status.message!r}"
        )

    token = medusa_admin_login(
        base_url=base_url,
        email=LOCAL_MEDUSA_ADMIN_EMAIL,
        password=LOCAL_MEDUSA_ADMIN_PASSWORD,
    )
    upsert_client_medusa_config(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        base_url=base_url,
        admin_api_key=token.token,
    )
    session.commit()
    refreshed_status = test_medusa_connection(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
    )
    session.commit()
    if refreshed_status.state != "connected":
        raise RuntimeError(
            "Refreshing the local Medusa admin token did not restore workspace connectivity. "
            f"message={refreshed_status.message!r}"
        )
    return {
        "refreshed": True,
        "state": refreshed_status.state,
        "message": refreshed_status.message,
        "baseUrl": base_url,
    }


def _ensure_medusa_product_option_values(*, product: Product, variant_titles: list[str]) -> None:
    medusa_product_id = str(product.medusa_product_id or "").strip()
    if not medusa_product_id:
        raise RuntimeError("Cannot sync Medusa option values because medusa_product_id is missing.")
    normalized_titles = [str(title).strip() for title in variant_titles if str(title).strip()]
    if not normalized_titles:
        raise RuntimeError("Cannot sync Medusa option values without at least one variant title.")

    token = medusa_admin_login(
        base_url=LOCAL_MEDUSA_BASE_URL,
        email=LOCAL_MEDUSA_ADMIN_EMAIL,
        password=LOCAL_MEDUSA_ADMIN_PASSWORD,
    ).token
    response = httpx.post(
        f"{LOCAL_MEDUSA_BASE_URL}/admin/products/{medusa_product_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "options": [
                {
                    "title": "Variant",
                    "values": normalized_titles,
                }
            ]
        },
        timeout=30,
    )
    if response.status_code >= 400 and "already exists" not in response.text.lower():
        raise RuntimeError(
            "Updating Medusa product option values failed. "
            f"status={response.status_code} body={response.text}"
        )


def _sync_ember_offer_variants(*, session, client: Client, product: Product) -> dict[str, Any]:
    medusa_auth = _ensure_local_medusa_admin_token(session=session, client=client)
    bundle_service = _bundle_service(session=session, client=client, product=product)
    handoff_bundle = bundle_service.get_active_bundle(bundle_type="skills_handoff")
    offer_document = _extract_offer_document(handoff_bundle)
    desired_variants = _parse_offer_variants(offer_document)
    _ensure_medusa_product_option_values(
        product=product,
        variant_titles=[str(variant["title"]) for variant in desired_variants],
    )
    variants_repo = ProductVariantsRepository(session)
    existing_rows = variants_repo.list_by_product(product_id=str(product.id))
    retained_row_ids: set[str] = set()
    offer_id = _resolve_ember_offer_id(session=session, product_id=str(product.id))
    selected_variant_id = str(offer_document.get("selectedVariantId") or "").strip().lower()

    remote_processing_order = sorted(
        desired_variants,
        key=lambda variant: (
            str(variant.get("id") or "").strip().lower() != selected_variant_id,
            int(variant.get("durationDays") or 9999),
        ),
    )

    synced_variants: list[dict[str, Any]] = []
    if not str(product.medusa_product_id or "").strip():
        raise RuntimeError(
            "EMBER product is missing medusa_product_id, so Medusa variant sync cannot proceed."
        )
    remote_product = get_medusa_product(
        session=session,
        org_id=str(client.org_id),
        client_id=str(client.id),
        medusa_product_id=str(product.medusa_product_id),
    )
    remote_variants_by_title = {
        _normalize_text(str(variant.get("title") or "")): variant
        for variant in (remote_product.get("variants") if isinstance(remote_product.get("variants"), list) else [])
        if isinstance(variant, dict) and str(variant.get("title") or "").strip()
    }

    for desired_variant in remote_processing_order:
        matched_row = _find_matching_existing_variant(
            desired_variant=desired_variant,
            existing_rows=existing_rows,
            retained_row_ids=retained_row_ids,
        )
        row_id = str(matched_row.id) if matched_row is not None else None
        remote_variant_id = str(matched_row.external_price_id or "").strip() if matched_row is not None else ""
        if not remote_variant_id:
            remote_variant = remote_variants_by_title.get(_normalize_text(str(desired_variant["title"])))
            if isinstance(remote_variant, dict):
                remote_variant_id = str(remote_variant.get("id") or "").strip()
        variant_title = str(desired_variant["title"])
        price_cents = int(desired_variant["priceCents"])
        compare_at_cents = (
            int(desired_variant["compareAtCents"])
            if isinstance(desired_variant.get("compareAtCents"), int)
            else None
        )
        option_values = {"offerId": str(desired_variant["id"]).strip()}

        if remote_variant_id:
            update_medusa_variant(
                session=session,
                org_id=str(client.org_id),
                client_id=str(client.id),
                product_id=str(product.medusa_product_id),
                variant_id=remote_variant_id,
                fields={
                    "title": variant_title,
                    "priceCents": price_cents,
                    "currency": str(desired_variant["currency"]),
                },
            )
        else:
            created_remote = create_medusa_variant(
                session=session,
                org_id=str(client.org_id),
                client_id=str(client.id),
                product=product,
                title=variant_title,
                price_cents=price_cents,
                currency=str(desired_variant["currency"]),
                option_values={"Variant": variant_title},
            )
            remote_variant_id = str(created_remote["id"])
            remote_variants_by_title[_normalize_text(variant_title)] = created_remote

        if matched_row is not None and row_id is not None:
            updated_row = variants_repo.update(
                variant_id=row_id,
                offer_id=offer_id,
                title=variant_title,
                price=price_cents,
                currency=str(desired_variant["currency"]).upper(),
                provider="medusa",
                external_price_id=remote_variant_id,
                compare_at_price=compare_at_cents,
                option_values=option_values,
            )
            if updated_row is None:
                raise RuntimeError(f"Failed to update local EMBER variant row {row_id}.")
            retained_row_ids.add(str(updated_row.id))
        else:
            created_row = variants_repo.create(
                product_id=str(product.id),
                offer_id=offer_id,
                title=variant_title,
                price=price_cents,
                currency=str(desired_variant["currency"]).upper(),
                provider="medusa",
                external_price_id=remote_variant_id,
                compare_at_price=compare_at_cents,
                option_values=option_values,
            )
            retained_row_ids.add(str(created_row.id))
            existing_rows.append(created_row)

        synced_variants.append(
            {
                "id": str(desired_variant["id"]),
                "title": variant_title,
                "priceCents": price_cents,
                "compareAtCents": compare_at_cents,
                "medusaVariantId": remote_variant_id,
            }
        )

    for row in existing_rows:
        row_id = str(row.id)
        if row_id in retained_row_ids:
            continue
        variants_repo.delete(variant_id=row_id)

    return {
        "productId": str(product.id),
        "medusaProductId": str(product.medusa_product_id),
        "offerId": offer_id,
        "medusaAuth": medusa_auth,
        "offerDocumentSelectedVariantId": offer_document.get("selectedVariantId"),
        "variants": sorted(synced_variants, key=lambda variant: (int(_extract_duration_days(str(variant["title"])) or 9999), int(variant["priceCents"]))),
    }


def _policy_placeholder_values(
    *,
    profile: ClientComplianceProfile,
    workspace_name: str,
    website_url: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    scalar_fields = {
        "legal_business_name": profile.legal_business_name,
        "operating_entity_name": profile.operating_entity_name,
        "company_address_text": profile.company_address_text,
        "business_license_identifier": profile.business_license_identifier,
        "support_email": profile.support_email,
        "support_phone": profile.support_phone,
        "support_hours_text": profile.support_hours_text,
        "response_time_commitment": profile.response_time_commitment,
    }
    for key, value in scalar_fields.items():
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()
    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        placeholder_key = key.strip()
        if not placeholder_key or raw_value is None:
            continue
        if isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if cleaned:
                values[placeholder_key] = cleaned
            continue
        if isinstance(raw_value, (int, float, bool)):
            values[placeholder_key] = str(raw_value)
    values["brand_name"] = workspace_name
    values["website_url"] = website_url
    return values


def _validate_policy_page_renderability(
    *,
    session,
    client: Client,
    website_url: str,
) -> dict[str, Any]:
    workspace_name = str(client.name or "").strip()
    profile = session.scalars(
        select(ClientComplianceProfile).where(
            ClientComplianceProfile.org_id == client.org_id,
            ClientComplianceProfile.client_id == client.id,
        )
    ).first()
    if not profile:
        return {
            "ok": False,
            "error": "Compliance profile not found for this workspace.",
            "missingFields": [],
            "pages": [],
        }

    placeholder_values = _policy_placeholder_values(
        profile=profile,
        workspace_name=workspace_name,
        website_url=website_url,
    )
    page_results: list[dict[str, Any]] = []
    missing_fields: set[str] = set()
    for page_key in list_policy_page_keys():
        try:
            render_policy_template_markdown(
                page_key=page_key,
                placeholder_values=placeholder_values,
            )
            page_results.append({"pageKey": page_key, "status": "ok"})
        except ValueError as exc:
            message = str(exc)
            missing_match = re.search(r"Missing placeholder values for page '[^']+': (?P<fields>.+)$", message)
            if missing_match:
                for field in missing_match.group("fields").split(","):
                    cleaned = field.strip()
                    if cleaned:
                        missing_fields.add(cleaned)
            page_results.append({"pageKey": page_key, "status": "failed", "error": message})

    return {
        "ok": not any(page["status"] == "failed" for page in page_results),
        "profileId": str(profile.id),
        "missingFields": sorted(missing_fields),
        "pages": page_results,
    }


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


def _run_sync_commerce() -> None:
    session = SessionLocal()
    try:
        client, product = _load_workspace(session)
        result = _sync_ember_offer_variants(session=session, client=client, product=product)
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
        commerce_sync = _sync_ember_offer_variants(session=session, client=client, product=product)
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
                            "Respect every provided slot-level copy limit exactly. "
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
                            "keep the CTA and benefit language grounded in the approved strategy bundle, "
                            "and stay within the provided slot-level copy limits."
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
            preview_validation_payload = (
                json.loads(preview_validation.stdout)
                if (preview_validation.stdout or "").strip()
                else {
                    "stdout": preview_validation.stdout,
                    "stderr": preview_validation.stderr,
                }
            )
            compliance_preflight = _validate_policy_page_renderability(
                session=session,
                client=client,
                website_url=f"{stack_info['baseUrl']}/workspaces/sites/{instantiation['siteId']}/preview/{args.country}",
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
                "commerceSync": commerce_sync,
                "compliancePreflight": compliance_preflight,
                "previewBaseUrl": stack_info["baseUrl"],
                "previewStack": stack_info,
                "previewValidation": preview_validation_payload,
            }
            report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
            _print(report_payload)
            if preview_validation.returncode != 0:
                raise RuntimeError(
                    "Preview validation failed:\n"
                    + (preview_validation.stdout or "")
                    + "\n"
                    + (preview_validation.stderr or "")
                )
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
    if args.command == "sync-commerce":
        _run_sync_commerce()
        return
    if args.command == "page-copy":
        _run_page_copy(args)
        return
    raise RuntimeError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
