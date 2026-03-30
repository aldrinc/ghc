from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import (
    Site,
    SiteImport,
    SiteImportSnapshot,
    SiteLink,
    SitePage,
    SitePageVersion,
    SiteTemplatePage,
)
from app.db.repositories.storefront_imports import StorefrontImportsRepository
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.site_import_adapter import (
    AdapterResult,
    adapt_generator_result,
    DEFAULT_MODEL_SLOTS,
    SiteImportAdapterError,
)
from app.services.site_import_archive import (
    analyze_site_import_archive,
    SiteImportArchiveError,
)
from app.services.site_import_capture import CaptureResult, capture_site
from app.services.site_import_generator_client import (
    GeneratorRunResult,
    generate_react_tailwind_from_screenshot,
    SiteImportGeneratorError,
)
from app.services.site_import_normalize import normalize_capture
from app.services.template_synthesis import (
    FAMILY_TO_TEMPLATE_ID,
    synthesize_import,
    SynthesisResult,
)
from app.services.template_variant_governance import (
    append_provenance_event,
    build_convert_provenance,
    build_template_draft_provenance,
)
from app.services.funnel_templates import apply_template_assets, get_funnel_template
from app.services.puck_data_validation import (
    LegacySectionPropError,
    validate_puck_data_no_legacy_section_props,
)
from app.services.site_templates import SiteTemplateError, create_template_from_site

logger = logging.getLogger(__name__)


def _extract_hostname(url: str) -> str | None:
    """Extract hostname from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


def _validate_url(url: str) -> None:
    """Validate URL format."""
    try:
        result = urlparse(url)
        if not result.scheme:
            raise ValueError("URL must include a scheme (http:// or https://)")
        if result.scheme not in ("http", "https"):
            raise ValueError("URL must use http:// or https:// scheme")
        if not result.netloc:
            raise ValueError("URL must include a valid domain")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid URL: {e}") from e


class SiteImportError(Exception):
    """Error during site import."""

    pass


def _load_completed_import(
    session: Session, *, org_id: str, client_id: str, site_import_id: str
) -> SiteImport:
    repo = StorefrontImportsRepository(session)
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)
    if site_import is None:
        raise SiteImportError("Import not found")
    if site_import.status != "completed":
        raise SiteImportError(f"Cannot apply import with status: {site_import.status}")
    return site_import


def _collect_screenshot_refs(snapshot: SiteImportSnapshot | None) -> list[str]:
    screenshot_refs: list[str] = []
    if snapshot is not None:
        if snapshot.desktop_screenshot_data_url:
            screenshot_refs.append(snapshot.desktop_screenshot_data_url)
        if snapshot.mobile_screenshot_data_url:
            screenshot_refs.append(snapshot.mobile_screenshot_data_url)
    return screenshot_refs


_PLACEHOLDER_IMPORT_BLOCK_TYPES = {"ProductCard", "ProductCollection", "Cart", "Checkout"}


def _import_page_raw_puck_data(adapted_page: dict[str, Any]) -> dict[str, Any]:
    raw_puck_data = adapted_page.get("puck_data") or adapted_page.get("puckData") or {}
    if not isinstance(raw_puck_data, dict):
        return {}
    return deepcopy(raw_puck_data)


def _is_imported_runtime_block_type(block_type: str) -> bool:
    return block_type == "ImportedRuntimeSection" or (
        block_type.startswith("Imported") and block_type.endswith("Section")
    )


def _should_materialize_template_puck_data(puck_data: dict[str, Any]) -> bool:
    content = puck_data.get("content")
    if not isinstance(content, list) or not content:
        return True

    top_level_types = [
        item.get("type")
        for item in content
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    ]
    if not top_level_types:
        return True

    if any(block_type in _PLACEHOLDER_IMPORT_BLOCK_TYPES for block_type in top_level_types):
        return True

    if any(_is_imported_runtime_block_type(block_type) for block_type in top_level_types):
        return False

    has_structural_blocks = any(
        block_type == "Section" or "Page" in block_type for block_type in top_level_types
    )
    return not has_structural_blocks


def _has_imported_runtime_block(puck_data: dict[str, Any]) -> bool:
    found = False

    def walk(node: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(node, list):
            for entry in node:
                walk(entry)
            return
        if not isinstance(node, dict):
            return
        block_type = node.get("type")
        if isinstance(block_type, str) and _is_imported_runtime_block_type(block_type):
            found = True
            return
        for value in node.values():
            walk(value)

    walk(puck_data.get("content"))
    return found


def _migrate_legacy_section_props(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "Section" and isinstance(node.get("props"), dict):
            props = node["props"]
            layout = props.get("layout")
            container_width = props.get("containerWidth")
            variant = props.get("variant")
            padding = props.get("padding")

            if "bandWidth" not in props and isinstance(layout, str):
                props["bandWidth"] = "full" if layout == "full" else "contained"
            if "contentWidth" not in props and isinstance(container_width, str):
                props["contentWidth"] = container_width
            if "surface" not in props and isinstance(variant, str):
                props["surface"] = {
                    "default": "default",
                    "muted": "muted",
                    "primary": "primary",
                    "dark": "dark",
                }.get(variant, "default")
            if "padY" not in props and isinstance(padding, str):
                props["padY"] = {"none": "none", "sm": "sm", "md": "md", "lg": "lg"}.get(
                    padding, "md"
                )
            if "padX" not in props and isinstance(padding, str):
                props["padX"] = {"none": "none", "sm": "sm", "md": "md", "lg": "lg"}.get(
                    padding, "md"
                )

            props.pop("layout", None)
            props.pop("containerWidth", None)
            props.pop("variant", None)
            props.pop("padding", None)

        for value in node.values():
            _migrate_legacy_section_props(value)
        return

    if isinstance(node, list):
        for item in node:
            _migrate_legacy_section_props(item)


def _apply_import_root_metadata(
    puck_data: dict[str, Any],
    *,
    adapted_page: dict[str, Any],
    source_url: str,
) -> None:
    root = puck_data.setdefault("root", {})
    if not isinstance(root, dict):
        root = {}
        puck_data["root"] = root
    props = root.setdefault("props", {})
    if not isinstance(props, dict):
        props = {}
        root["props"] = props

    if not isinstance(props.get("title"), str) or not props.get("title"):
        props["title"] = (
            adapted_page.get("name")
            or adapted_page.get("page_type")
            or adapted_page.get("pageType")
            or "Imported Page"
        )
    if not isinstance(props.get("description"), str):
        props["description"] = source_url


def _humanize_page_type(page_type: str | None) -> str:
    tokens = (page_type or "page").replace("-", "_").split("_")
    return " ".join(token.capitalize() for token in tokens if token) or "Page"


def _slugify_page_type(page_type: str | None) -> str:
    return ((page_type or "page").strip().lower().replace("_", "-")) or "page"


def _default_site_type_for_page(page_type: str | None) -> str:
    if page_type in {"product_detail", "category", "collection", "store", "cart", "checkout"}:
        return "ecommerce"
    if page_type in {"pre_sell", "landing"}:
        return "landing"
    return "content"


def _materialize_import_page_puck_data(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    adapted_page: dict[str, Any],
    source_url: str,
) -> dict[str, Any]:
    raw_puck_data = _import_page_raw_puck_data(adapted_page)
    puck_data = raw_puck_data

    if _should_materialize_template_puck_data(raw_puck_data):
        template_id = adapted_page.get("template_id") or adapted_page.get("templateId")
        if not isinstance(template_id, str) or not template_id.strip():
            raise SiteImportError(
                "Imported page does not contain editor-renderable Puck data and is missing a template_id for reconstruction."
            )

        template = get_funnel_template(template_id.strip())
        if template is None:
            raise SiteImportError(
                f"Imported page references unknown template '{template_id.strip()}'."
            )
        puck_data = apply_template_assets(
            session=session,
            org_id=org_id,
            client_id=client_id,
            template=template,
        )

    _migrate_legacy_section_props(puck_data)
    _apply_import_root_metadata(
        puck_data,
        adapted_page=adapted_page,
        source_url=source_url,
    )
    return puck_data


def create_import_record(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    source_url: str,
    page_type_hint: str | None,
    site_family_hint: str | None,
    created_by_user_external_id: str | None,
    model_slots: list[int] | None = None,
) -> SiteImport:
    """
    Create a new site import job.

    This creates the import record and runs the full pipeline:
    1. Capture website and take screenshots
    2. Generate React/Tailwind code from screenshot
    3. Adapt generated code to Site runtime format
    """
    _validate_url(source_url)
    source_hostname = _extract_hostname(source_url)
    slots = model_slots or DEFAULT_MODEL_SLOTS
    repo = StorefrontImportsRepository(session)
    return repo.create_import(
        org_id=org_id,
        client_id=client_id,
        source_url=source_url,
        source_hostname=source_hostname,
        input_mode="image",
        page_type_hint=page_type_hint,
        site_family_hint=site_family_hint,
        model_slots=slots,
        created_by_user_external_id=created_by_user_external_id,
    )


def create_archive_import_record(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    archive_name: str,
    archive_bytes: bytes,
    page_type_hint: str | None,
    site_family_hint: str | None,
    created_by_user_external_id: str | None,
) -> SiteImport:
    """
    Create a completed import record from a trusted React/Tailwind archive export.

    This path is intentionally strict:
    - accepts only zip archives
    - derives screenshot-to-code review artifacts from the archive
    - preserves the same review/convert flow shape used by normal imports
    - does not fabricate screenshots
    """
    try:
        analysis = analyze_site_import_archive(
            archive_name=archive_name,
            archive_bytes=archive_bytes,
            page_type_hint=page_type_hint,
            site_family_hint=site_family_hint,
        )
    except SiteImportArchiveError as exc:
        raise SiteImportError(str(exc)) from exc

    repo = StorefrontImportsRepository(session)
    site_import = repo.create_import(
        org_id=org_id,
        client_id=client_id,
        source_url=analysis.source_url,
        source_hostname=None,
        input_mode=analysis.input_mode,
        page_type_hint=page_type_hint,
        site_family_hint=site_family_hint,
        model_slots=[],
        created_by_user_external_id=created_by_user_external_id,
    )

    try:
        repo.create_snapshot(
            site_import=site_import,
            html_snapshot=analysis.html_snapshot,
            desktop_screenshot_data_url="",
            mobile_screenshot_data_url="",
            capture_metadata=analysis.capture_metadata,
        )
        refreshed_import = repo.get_import_by_id(site_import_id=str(site_import.id))
        if refreshed_import is None:
            raise SiteImportError("Archive import record disappeared before persistence.")
        repo.store_upstream_generation(
            site_import=refreshed_import,
            upstream_request_payload=analysis.upstream_request_payload,
            upstream_transcript=analysis.upstream_transcript,
            upstream_variants=analysis.upstream_variants,
            upstream_metadata=analysis.upstream_metadata,
        )
        refreshed_import = repo.get_import_by_id(site_import_id=str(site_import.id))
        if refreshed_import is None:
            raise SiteImportError("Archive import record disappeared before completion.")
        repo.mark_import_completed(
            site_import=refreshed_import,
            title=analysis.title,
            meta_description=analysis.meta_description,
            suggested_template_family=analysis.suggested_template_family,
            resolved_site_family=analysis.resolved_site_family,
            resolved_page_type=analysis.resolved_page_type,
            resolved_template_id=analysis.resolved_template_id,
            theme_candidate=analysis.theme_candidate,
            normalized_sections=analysis.normalized_sections,
            adapted_site=analysis.adapted_site,
            adapted_pages=analysis.adapted_pages,
            adapted_puck_data=analysis.adapted_puck_data,
        )
    except Exception as exc:
        refresh_import = repo.get_import_by_id(site_import_id=str(site_import.id))
        if refresh_import is not None:
            repo.mark_import_failed(
                site_import=refresh_import,
                error_message=str(exc) if str(exc) else "Archive import failed",
                stage="adapting",
            )
        if isinstance(exc, SiteImportError):
            raise
        raise SiteImportError("Failed to persist archive import.") from exc

    completed_import = repo.get_import_by_id(site_import_id=str(site_import.id))
    if completed_import is None:
        raise SiteImportError("Archive import record could not be reloaded after completion.")
    return completed_import


async def _process_import_job_with_session(session: Session, *, site_import_id: str) -> None:
    repo = StorefrontImportsRepository(session)
    site_import = repo.get_import_by_id(site_import_id=site_import_id)
    if site_import is None:
        logger.error("Site import %s not found for processing", site_import_id)
        return

    source_url = site_import.source_url
    page_type_hint = site_import.page_type_hint
    site_family_hint = site_import.site_family_hint
    slots = site_import.model_slots or DEFAULT_MODEL_SLOTS

    current_stage = "capturing"
    try:
        repo.update_import_status(site_import=site_import, status="capturing")
        capture_result = await capture_site(source_url)

        repo.create_snapshot(
            site_import=site_import,
            html_snapshot=capture_result.html_snapshot,
            desktop_screenshot_data_url=capture_result.desktop_screenshot_data_url,
            mobile_screenshot_data_url=capture_result.mobile_screenshot_data_url,
            capture_metadata=capture_result.capture_metadata,
        )

        captured_title = capture_result.title
        captured_meta_description = capture_result.meta_description

        current_stage = "generating"
        repo.update_import_status(site_import=site_import, status="generating")

        async def _persist_upstream_event(event: dict[str, Any]) -> None:
            refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
            if refresh_import is None:
                return
            repo.append_upstream_event(site_import=refresh_import, event=event)

        generator_result = await generate_react_tailwind_from_screenshot(
            screenshot_data_url=capture_result.desktop_screenshot_data_url,
            source_url=source_url,
            page_type_hint=page_type_hint,
            input_mode="image",
            model_slots=slots,
            on_event=_persist_upstream_event,
        )

        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is None:
            return
        repo.store_upstream_generation(
            site_import=refresh_import,
            upstream_request_payload=generator_result.request_payload,
            upstream_transcript=generator_result.transcript,
            upstream_variants=generator_result.variants,
            upstream_metadata=generator_result.metadata,
        )

        current_stage = "adapting"
        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is None:
            return
        repo.update_import_status(site_import=refresh_import, status="adapting")

        adapter_result = adapt_generator_result(
            generator_result=generator_result,
            page_type_hint=page_type_hint,
            site_family_hint=site_family_hint,
        )

        normalization_result = normalize_capture(
            html_snapshot=capture_result.html_snapshot,
            capture_metadata=capture_result.capture_metadata,
            page_type_hint=page_type_hint,
            title=captured_title,
            meta_description=captured_meta_description,
        )

        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is None:
            return
        repo.mark_import_completed(
            site_import=refresh_import,
            title=captured_title,
            meta_description=captured_meta_description,
            suggested_template_family=getattr(
                normalization_result,
                "suggested_template_family",
                adapter_result.resolved_site_family,
            ),
            resolved_site_family=adapter_result.resolved_site_family,
            resolved_page_type=adapter_result.resolved_page_type,
            resolved_template_id=adapter_result.resolved_template_id,
            theme_candidate=normalization_result.theme_candidate,
            normalized_sections=normalization_result.normalized_sections,
            adapted_site=adapter_result.adapted_site,
            adapted_pages=adapter_result.adapted_pages,
            adapted_puck_data=adapter_result.adapted_puck_data,
        )

    except SiteImportGeneratorError as e:
        logger.exception("Failed to generate from site: %s", source_url)
        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is not None:
            repo.mark_import_failed(
                site_import=refresh_import,
                error_message=str(e) if str(e) else "Generation failed",
                stage="generating",
            )
    except SiteImportAdapterError as e:
        logger.exception("Failed to adapt imported site: %s", source_url)
        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is not None:
            repo.mark_import_failed(
                site_import=refresh_import,
                error_message=str(e) if str(e) else "Adapter failed",
                stage="adapting",
            )
    except Exception as e:
        logger.exception("Failed to process import: %s", source_url)
        refresh_import = repo.get_import_by_id(site_import_id=site_import_id)
        if refresh_import is not None:
            repo.mark_import_failed(
                site_import=refresh_import,
                error_message=str(e) if str(e) else "Processing failed",
                stage=current_stage,
            )


async def process_import_job(*, site_import_id: str) -> None:
    session = SessionLocal()
    try:
        await _process_import_job_with_session(session, site_import_id=site_import_id)
    finally:
        session.close()


def list_imports(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    limit: int = 25,
) -> list[SiteImport]:
    """List site imports for a workspace."""
    repo = StorefrontImportsRepository(session)
    return repo.list_imports(org_id=org_id, client_id=client_id, limit=limit)


def get_import_detail(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
) -> SiteImport | None:
    """Get detailed import information including snapshot."""
    repo = StorefrontImportsRepository(session)
    return repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)


def get_import_snapshot(
    session: Session,
    *,
    site_import_id: str,
) -> SiteImportSnapshot | None:
    """Get the snapshot for an import."""
    repo = StorefrontImportsRepository(session)
    return repo.get_import_snapshot(site_import_id=site_import_id)


def save_import_as_site(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    site_name: str,
    description: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """Persist a completed site import into the dedicated Site runtime.

    Current save behavior is intentionally strict:
    - create a NEW site only
    - save all adapted pages in one transaction
    - fail the entire save if any page cannot be created
    """
    imports_repo = StorefrontImportsRepository(session)
    runtime_repo = SitesRuntimeRepository(session)

    site_import = imports_repo.get_import(
        org_id=org_id,
        client_id=client_id,
        site_import_id=site_import_id,
    )
    if site_import is None:
        raise SiteImportError("Import not found")
    if site_import.status != "completed":
        raise SiteImportError(f"Cannot save import with status: {site_import.status}")
    if site_import.saved_site_id:
        raise SiteImportError(f"Import already saved to site {site_import.saved_site_id}")

    adapted_site = site_import.adapted_site or {}
    adapted_pages = site_import.adapted_pages or []
    if not adapted_pages:
        raise SiteImportError(
            "This import does not have a first-party site runtime translation. Use the existing import review flow instead of saving it as a site."
        )

    materialized_puck_data: list[dict[str, Any]] = []

    # Validate all adapted pages for legacy Section props before saving
    for idx, adapted_page in enumerate(adapted_pages):
        puck_data = _materialize_import_page_puck_data(
            session,
            org_id=org_id,
            client_id=client_id,
            adapted_page=adapted_page,
            source_url=site_import.source_url,
        )
        page_label = f"page[{idx}]"  # Human-friendly label for errors
        try:
            validate_puck_data_no_legacy_section_props(puck_data)
        except LegacySectionPropError as e:
            raise SiteImportError(
                f"Cannot save import: legacy Section prop '{e.prop_name}' found in {page_label}. "
                f"These props are no longer supported. Use design-system tokens instead."
            ) from e
        materialized_puck_data.append(puck_data)

    snapshot = imports_repo.get_import_snapshot(site_import_id=site_import_id)
    screenshot_refs: list[str] = []
    if snapshot is not None:
        if snapshot.desktop_screenshot_data_url:
            screenshot_refs.append(snapshot.desktop_screenshot_data_url)
        if snapshot.mobile_screenshot_data_url:
            screenshot_refs.append(snapshot.mobile_screenshot_data_url)

    created_pages: list[dict[str, Any]] = []
    page_type_to_id: dict[str, str] = {}

    try:
        site = runtime_repo.create_site(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            product_id=None,
            name=site_name,
            description=description,
            site_type=(adapted_site.get("site_type") or adapted_site.get("siteType")),
            site_family=(
                adapted_site.get("site_family")
                or adapted_site.get("siteFamily")
                or site_import.resolved_site_family
            ),
            commerce_provider=(
                adapted_site.get("commerce_provider") or adapted_site.get("commerceProvider")
            ),
            source_hostname=site_import.source_hostname,
            entry_page_type=(
                adapted_site.get("entry_page_type")
                or adapted_site.get("entryPageType")
                or site_import.resolved_page_type
            ),
            imported_page_count=len(adapted_pages),
            completeness_state=(
                adapted_site.get("completeness_state")
                or adapted_site.get("completenessState")
                or ("complete" if len(adapted_pages) > 0 else "partial")
            ),
            created_by_user_external_id=created_by_user_external_id,
        )

        for index, adapted_page in enumerate(adapted_pages):
            puck_data = materialized_puck_data[index]
            page_type = adapted_page.get("page_type") or adapted_page.get("pageType")
            template_id = adapted_page.get("template_id") or adapted_page.get("templateId")
            page = runtime_repo.create_page(
                site_id=str(site.id),
                name=adapted_page.get("name") or page_type or f"Imported Page {index + 1}",
                slug=adapted_page.get("slug") or (page_type or f"page-{index + 1}"),
                page_type=page_type,
                template_id=template_id,
                ordering=int(adapted_page.get("ordering", index)),
                source_url=site_import.source_url,
                source_screenshot_refs=screenshot_refs,
                generated_code=adapted_page.get("generated_code")
                or adapted_page.get("generatedCode"),
                adapted_puck_data=puck_data,
                outbound_links=adapted_page.get("outbound_links")
                or adapted_page.get("outboundLinks")
                or [],
            )
            version = runtime_repo.create_page_version(
                page_id=str(page.id),
                puck_data=puck_data,
                provenance={
                    "source_type": "site_import",
                    "site_import_id": site_import_id,
                    "source_url": site_import.source_url,
                    "source_hostname": site_import.source_hostname,
                    "generator": site_import.upstream_metadata or {},
                    "resolved_site_family": site_import.resolved_site_family,
                    "resolved_page_type": page_type,
                    "resolved_template_id": template_id,
                },
            )
            if page_type:
                page_type_to_id[page_type] = str(page.id)
            created_pages.append(
                {
                    "pageId": str(page.id),
                    "pageType": page_type,
                    "templateId": template_id,
                    "versionId": str(version.id),
                    "outboundLinks": adapted_page.get("outbound_links")
                    or adapted_page.get("outboundLinks")
                    or [],
                }
            )

        for created_page in created_pages:
            for link in created_page.get("outboundLinks", []):
                to_page_type = link.get("to_page_type") or link.get("toPageType")
                runtime_repo.create_link(
                    site_id=str(site.id),
                    from_page_id=created_page["pageId"],
                    to_page_id=page_type_to_id.get(to_page_type) if to_page_type else None,
                    from_page_type=created_page.get("pageType"),
                    to_page_type=to_page_type,
                    label=link.get("label"),
                    link_kind=link.get("link_kind") or link.get("linkKind") or "internal",
                    meta=link,
                )

        site_import.saved_site_id = str(site.id)
        site_import.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(site)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to save import into site runtime.") from exc

    return {
        "siteId": str(site.id),
        "siteName": site.name,
        "pageCount": len(created_pages),
        "entryPageType": site.entry_page_type,
        "createdPages": [
            {
                "pageId": page["pageId"],
                "pageType": page.get("pageType"),
                "templateId": page.get("templateId"),
                "versionId": page.get("versionId"),
            }
            for page in created_pages
        ],
        "createdAt": site.created_at,
    }


def add_import_pages_to_site(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    site_id: str,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """Add imported pages into an existing site runtime with explicit collision errors."""
    imports_repo = StorefrontImportsRepository(session)
    runtime_repo = SitesRuntimeRepository(session)

    site_import = _load_completed_import(
        session, org_id=org_id, client_id=client_id, site_import_id=site_import_id
    )
    site = runtime_repo.get_site(org_id=org_id, client_id=client_id, site_id=site_id)
    if site is None:
        raise SiteImportError("Target site not found")

    adapted_pages = site_import.adapted_pages or []
    if not adapted_pages:
        raise SiteImportError("Import has no adapted pages to add")

    snapshot = imports_repo.get_import_snapshot(site_import_id=site_import_id)
    screenshot_refs = _collect_screenshot_refs(snapshot)
    created_pages: list[dict[str, Any]] = []
    page_type_to_id: dict[str, str] = {}
    materialized_puck_data = [
        _materialize_import_page_puck_data(
            session,
            org_id=org_id,
            client_id=client_id,
            adapted_page=adapted_page,
            source_url=site_import.source_url,
        )
        for adapted_page in adapted_pages
    ]

    try:
        for index, adapted_page in enumerate(adapted_pages):
            puck_data = materialized_puck_data[index]
            page_type = adapted_page.get("page_type") or adapted_page.get("pageType")
            slug = adapted_page.get("slug") or (page_type or f"page-{index + 1}")
            if not runtime_repo.check_slug_unique(site_id=site_id, slug=slug):
                raise SiteImportError(
                    f"Slug collision for '{slug}'. Choose explicit collision handling."
                )
            template_id = adapted_page.get("template_id") or adapted_page.get("templateId")
            page = runtime_repo.create_page(
                site_id=site_id,
                name=adapted_page.get("name") or page_type or f"Imported Page {index + 1}",
                slug=slug,
                page_type=page_type,
                page_role=page_type,
                template_id=template_id,
                page_template_id=template_id,
                ordering=int(adapted_page.get("ordering", index)),
                source_url=site_import.source_url,
                source_screenshot_refs=screenshot_refs,
                generated_code=adapted_page.get("generated_code")
                or adapted_page.get("generatedCode"),
                adapted_puck_data=puck_data,
                outbound_links=adapted_page.get("outbound_links")
                or adapted_page.get("outboundLinks")
                or [],
            )
            version = runtime_repo.create_page_version(
                page_id=str(page.id),
                puck_data=puck_data,
                provenance={
                    "source_type": "site_import",
                    "site_import_id": site_import_id,
                    "source_url": site_import.source_url,
                    "source_hostname": site_import.source_hostname,
                    "generator": site_import.upstream_metadata or {},
                },
                status="draft",
                source_type="site_import",
                source_id=site_import_id,
            )
            if page_type:
                page_type_to_id[page_type] = str(page.id)
            created_pages.append(
                {
                    "pageId": str(page.id),
                    "pageType": page_type,
                    "templateId": template_id,
                    "versionId": str(version.id),
                    "outboundLinks": adapted_page.get("outbound_links")
                    or adapted_page.get("outboundLinks")
                    or [],
                }
            )
        for created_page in created_pages:
            for link in created_page.get("outboundLinks", []):
                to_page_type = link.get("to_page_type") or link.get("toPageType")
                runtime_repo.create_link(
                    site_id=site_id,
                    from_page_id=created_page["pageId"],
                    to_page_id=page_type_to_id.get(to_page_type) if to_page_type else None,
                    from_page_type=created_page.get("pageType"),
                    to_page_type=to_page_type,
                    label=link.get("label"),
                    link_kind=link.get("link_kind") or link.get("linkKind") or "internal",
                    meta=link,
                )

        site.updated_at = datetime.now(timezone.utc)
        session.add(site)
        session.commit()
    except Exception as exc:
        session.rollback()
        if isinstance(exc, SiteImportError):
            raise
        raise SiteImportError("Failed to add imported pages into site runtime.") from exc

    return {
        "siteId": site_id,
        "pageCount": len(created_pages),
        "createdPages": [
            {
                "pageId": page["pageId"],
                "pageType": page.get("pageType"),
                "templateId": page.get("templateId"),
                "versionId": page.get("versionId"),
            }
            for page in created_pages
        ],
    }


def create_import_as_site_template(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    name: str,
    family: str,
    description: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """Persist an import as a reusable multi-page site template."""
    site_import = _load_completed_import(
        session, org_id=org_id, client_id=client_id, site_import_id=site_import_id
    )
    if not site_import.saved_site_id:
        raise SiteImportError(
            "Import must first be saved as a site before it can be converted into a reusable site template."
        )

    try:
        template = create_template_from_site(
            session,
            site_id=str(site_import.saved_site_id),
            org_id=org_id,
            client_id=client_id,
            name=name,
            description=description,
            created_by_user_external_id=created_by_user_external_id,
        )
        if template.family != family:
            template.family = family
            session.add(template)
        session.commit()
        session.refresh(template)
    except Exception as exc:
        session.rollback()
        if isinstance(exc, SiteImportError):
            raise
        if isinstance(exc, SiteTemplateError):
            raise SiteImportError(str(exc)) from exc
        raise SiteImportError("Failed to persist site template from import.") from exc

    created_pages = session.scalars(
        select(SiteTemplatePage).where(SiteTemplatePage.site_template_id == str(template.id))
    ).all()

    return {
        "siteTemplateId": str(template.id),
        "name": template.name,
        "family": template.family,
        "pageCount": len(created_pages),
        "funnelCount": 0,
        "createdAt": template.created_at,
    }


def convert_import_to_variant(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    name: str,
    family: str,
    page_type: str,
    accepted_section_ids: list[str],
    review_notes: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """
    Convert an import into a draft template variant.

    This creates:
    1. A style preset from the theme candidate
    2. A template variant with the accepted sections
    """
    repo = StorefrontImportsRepository(session)

    # Get the import
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)
    if site_import is None:
        raise SiteImportError("Import not found")

    if site_import.status != "completed":
        raise SiteImportError(f"Cannot convert import with status: {site_import.status}")

    # Validate accepted section IDs
    normalized_sections = site_import.normalized_sections or []
    section_ids = {s.get("id") for s in normalized_sections}
    invalid_ids = set(accepted_section_ids) - section_ids
    if invalid_ids:
        raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")

    # Filter to accepted sections
    accepted_sections = [s for s in normalized_sections if s.get("id") in accepted_section_ids]

    theme_candidate = site_import.theme_candidate or {}
    # Create provenance record using the helper function
    # Note: This path does not include synthesis, so we pass an empty synthesis dict
    provenance = build_convert_provenance(
        source_url=site_import.source_url,
        source_hostname=site_import.source_hostname,
        imported_at=site_import.created_at.isoformat() if site_import.created_at else None,
        page_type_hint=site_import.page_type_hint,
        synthesis={},  # No synthesis for basic convert
        actor=created_by_user_external_id,
    )

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            name=f"{name} - Style",
            tokens=theme_candidate,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=accepted_sections,
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist template variant draft.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
    }


def list_variant_drafts(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    limit: int = 25,
) -> list:
    """List template variant drafts for a workspace."""
    repo = StorefrontImportsRepository(session)
    return repo.list_variant_drafts(org_id=org_id, client_id=client_id, limit=limit)


def get_import_synthesis(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    target_family: str | None = None,
    target_page_type: str | None = None,
    accepted_section_ids: list[str] | None = None,
) -> SynthesisResult | None:
    """
    Get synthesis result for an import.

    Synthesizes normalized sections into structured puckData with
    block coverage scoring and missing block requests.
    """
    repo = StorefrontImportsRepository(session)
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)

    if site_import is None:
        return None

    if site_import.status != "completed":
        return None

    if site_import.resolved_site_family == "imported-template":
        return None

    normalized_sections = site_import.normalized_sections or []
    theme_candidate = site_import.theme_candidate or {}
    suggested_family = site_import.suggested_template_family

    # Filter to accepted sections if provided (for preview matching convert behavior)
    if accepted_section_ids:
        section_ids = {s.get("id") for s in normalized_sections}
        invalid_ids = set(accepted_section_ids) - section_ids
        if invalid_ids:
            raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")
        normalized_sections = [
            s for s in normalized_sections if s.get("id") in accepted_section_ids
        ]

    return synthesize_import(
        normalized_sections=normalized_sections,
        theme_candidate=theme_candidate,
        suggested_family=suggested_family,
        target_family=target_family,
        target_page_type=target_page_type,
    )


def convert_import_to_variant_with_synthesis(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    site_import_id: str,
    name: str,
    family: str,
    page_type: str,
    accepted_section_ids: list[str],
    review_notes: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """
    Convert an import into a draft template variant with synthesis.

    This creates:
    1. A style preset from the theme candidate
    2. A template variant with the accepted sections
    3. Synthesis output stored in provenance
    """
    repo = StorefrontImportsRepository(session)

    # Get the import
    site_import = repo.get_import(org_id=org_id, client_id=client_id, site_import_id=site_import_id)
    if site_import is None:
        raise SiteImportError("Import not found")

    if site_import.status != "completed":
        raise SiteImportError(f"Cannot convert import with status: {site_import.status}")

    if site_import.resolved_site_family == "imported-template":
        raise SiteImportError(
            "Imported-template archive imports no longer synthesize into legacy draft families. Save the imported page set into My Sites instead."
        )

    # Validate accepted section IDs
    normalized_sections = site_import.normalized_sections or []
    section_ids = {s.get("id") for s in normalized_sections}
    invalid_ids = set(accepted_section_ids) - section_ids
    if invalid_ids:
        raise SiteImportError(f"Invalid section IDs: {invalid_ids}. Valid IDs: {section_ids}")

    # Filter to accepted sections
    accepted_sections = [s for s in normalized_sections if s.get("id") in accepted_section_ids]

    theme_candidate = site_import.theme_candidate or {}

    # Run synthesis using ACCEPTED sections (reviewer-approved), not all normalized sections
    synthesis = synthesize_import(
        normalized_sections=accepted_sections,
        theme_candidate=theme_candidate,
        suggested_family=site_import.suggested_template_family,
        target_family=family,
        target_page_type=page_type,
    )

    # Build synthesis dict for provenance
    synthesis_dict = {
        "target_family": synthesis.targetFamily,
        "target_page_type": synthesis.targetPageType,
        "block_coverage": {
            "total_sections": synthesis.blockCoverage.totalSections,
            "exact_matches": synthesis.blockCoverage.exactMatches,
            "partial_matches": synthesis.blockCoverage.partialMatches,
            "missing_matches": synthesis.blockCoverage.missingMatches,
            "coverage_score": synthesis.blockCoverage.coverageScore,
        },
        "missing_block_requests": [
            {
                "request_id": req.requestId,
                "section_type": req.sectionType,
                "reason": req.reason,
                "source_selector": req.sourceSelector,
                "text_preview": req.textPreview,
                "suggested_family": req.suggestedFamily,
                "suggested_page_type": req.suggestedPageType,
            }
            for req in synthesis.missingBlockRequests
        ],
        "synthesized_puck_data": synthesis.synthesizedPuckData,
    }

    # Create provenance record using the helper function
    provenance = build_convert_provenance(
        source_url=site_import.source_url,
        source_hostname=site_import.source_hostname,
        imported_at=site_import.created_at.isoformat() if site_import.created_at else None,
        page_type_hint=site_import.page_type_hint,
        synthesis=synthesis_dict,
        actor=created_by_user_external_id,
    )

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            name=f"{name} - Style",
            tokens=theme_candidate,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=site_import_id,
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=accepted_sections,
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist synthesized template variant draft.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
        "synthesis": synthesis,
    }


def create_draft_from_template(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    template_id: str,
    name: str,
    family: str,
    page_type: str,
    puck_data: dict[str, Any],
    review_notes: str | None,
    created_by_user_external_id: str | None,
    product_id: str | None = None,
    variant_id: str | None = None,
    variant_provider: str | None = None,
    variant_external_id: str | None = None,
    product: Any = None,
    variant: Any = None,
) -> dict[str, Any]:
    """
    Create a draft variant from a built-in storefront template.

    This creates:
    1. A style preset with base design system tokens
    2. A template variant with the template's puckData in provenance

    Args:
        session: Database session.
        org_id: Organization ID.
        client_id: Client/workspace ID.
        template_id: Template ID (e.g., 'sales-pdp').
        name: Name for the draft variant.
        family: Template family.
        page_type: Template page type.
        puck_data: The template's puckData.
        review_notes: Optional review notes.
        created_by_user_external_id: User who created the draft.
        product_id: Product ID for binding context.
        variant_id: Variant ID for binding context.
        variant_provider: Variant provider (e.g., 'medusa').
        variant_external_id: External Medusa variant ID.
        product: Product ORM object for hydration.
        variant: Variant ORM object for hydration.

    Returns:
        Dict with 'variant' and 'style_preset' keys.
    """
    from app.services.design_system_generation import load_base_tokens_template
    from app.services.funnel_templates import get_funnel_template
    from app.services.template_hydration import (
        hydrate_template_puckdata,
        materialize_template_assets,
    )

    repo = StorefrontImportsRepository(session)

    # Get the funnel template for asset materialization
    funnel_template = get_funnel_template(template_id)

    # Step 1: Hydrate puckData with product/variant context
    hydrated_puck_data = puck_data
    if product is not None:
        hydrated_puck_data = hydrate_template_puckdata(
            puck_data=puck_data,
            product=product,
            variant=variant,
        )

    # Step 2: Materialize assets (upload and get public IDs)
    materialized_puck_data = hydrated_puck_data
    if funnel_template is not None:
        materialized_puck_data = materialize_template_assets(
            session=session,
            org_id=org_id,
            client_id=client_id,
            template=funnel_template,
            puck_data=hydrated_puck_data,
        )

    # Build provenance for template draft with binding context
    provenance = build_template_draft_provenance(
        template_id=template_id,
        template_family=family,
        template_page_type=page_type,
        synthesized_puck_data=materialized_puck_data,
        actor=created_by_user_external_id,
        product_id=product_id,
        variant_id=variant_id,
        variant_provider=variant_provider,
        variant_external_id=variant_external_id,
    )

    # Create style preset from base tokens template
    # The base tokens have a flat cssVars structure; we need to structure them
    # into the expected groups (palette, fonts) for governance validation.
    base_tokens = load_base_tokens_template()
    css_vars = base_tokens.get("cssVars", {})

    # Derive storefront token groups from actual base token values
    # These groups are required by validate_token_presence in governance
    storefront_tokens = {
        # Palette: extract color-related CSS variables
        "palette": {
            "brand": css_vars.get("--color-brand"),
            "bg": css_vars.get("--color-bg"),
            "text": css_vars.get("--color-text"),
            "pageBg": css_vars.get("--color-page-bg"),
            "muted": css_vars.get("--color-muted"),
            "border": css_vars.get("--color-border"),
            "soft": css_vars.get("--color-soft"),
            "cta": css_vars.get("--color-cta"),
            "ctaText": css_vars.get("--color-cta-text"),
        },
        # Fonts: extract font-related CSS variables
        "fonts": {
            "sans": css_vars.get("--font-sans"),
            "heading": css_vars.get("--font-heading"),
            "cta": css_vars.get("--font-cta"),
        },
        # Preserve the full cssVars for complete token coverage
        "cssVars": css_vars,
        "dataTheme": base_tokens.get("dataTheme"),
        "fontUrls": base_tokens.get("fontUrls", []),
        "funnelDefaults": base_tokens.get("funnelDefaults", {}),
        "brand": base_tokens.get("brand", {}),
    }

    try:
        style_preset = repo.create_style_preset(
            org_id=org_id,
            client_id=client_id,
            site_import_id=None,  # No site import for template drafts
            name=f"{name} - Style",
            tokens=storefront_tokens,
            commit=False,
        )

        variant = repo.create_variant_draft(
            org_id=org_id,
            client_id=client_id,
            site_import_id=None,  # No site import for template drafts
            style_preset_id=style_preset.id,
            name=name,
            family=family,
            page_type=page_type,
            accepted_sections=[],  # Template drafts don't have sections from import
            provenance=provenance,
            review_notes=review_notes,
            created_by_user_external_id=created_by_user_external_id,
            commit=False,
        )
        session.commit()
        session.refresh(style_preset)
        session.refresh(variant)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to persist template draft variant.") from exc

    return {
        "variant": variant,
        "style_preset": style_preset,
    }


def create_site_from_variant(
    session: Session,
    *,
    org_id: str,
    client_id: str,
    variant_id: str,
    site_name: str,
    description: str | None,
    created_by_user_external_id: str | None,
) -> dict[str, Any]:
    """Materialize an approved template variant into the canonical site runtime."""
    repo = StorefrontImportsRepository(session)
    runtime_repo = SitesRuntimeRepository(session)

    variant = repo.get_variant(org_id=org_id, client_id=client_id, variant_id=variant_id)
    if variant is None:
        raise SiteImportError("Variant not found")
    if variant.status != "approved":
        raise SiteImportError(
            f"Cannot create site from variant with status: {variant.status}. Approve it for publish first."
        )

    provenance = deepcopy(variant.provenance or {})
    existing_site_id = provenance.get("materialized_site_id")
    if isinstance(existing_site_id, str) and existing_site_id.strip():
        raise SiteImportError(f"Variant already materialized to site {existing_site_id}.")

    source_import = None
    screenshot_refs: list[str] = []
    source_url = provenance.get("source_url")
    source_hostname = provenance.get("source_hostname")
    materialized_puck_data: dict[str, Any] | None = None
    materialized_page_type = variant.page_type
    materialized_template_id: str | None = None
    materialization_mode = "synthesized_variant"
    if variant.site_import_id:
        source_import = repo.get_import(
            org_id=org_id,
            client_id=client_id,
            site_import_id=str(variant.site_import_id),
        )
        if source_import is not None:
            if not isinstance(source_url, str) or not source_url.strip():
                source_url = source_import.source_url
            if not isinstance(source_hostname, str) or not source_hostname.strip():
                source_hostname = source_import.source_hostname
            screenshot_refs = _collect_screenshot_refs(
                repo.get_import_snapshot(site_import_id=str(source_import.id))
            )
            for adapted_page in source_import.adapted_pages or []:
                raw_puck_data = _import_page_raw_puck_data(adapted_page)
                if not _has_imported_runtime_block(raw_puck_data):
                    continue
                materialized_puck_data = _materialize_import_page_puck_data(
                    session,
                    org_id=org_id,
                    client_id=client_id,
                    adapted_page=adapted_page,
                    source_url=source_import.source_url,
                )
                materialized_page_type = (
                    adapted_page.get("page_type") or adapted_page.get("pageType") or variant.page_type
                )
                candidate_template_id = adapted_page.get("template_id") or adapted_page.get("templateId")
                if isinstance(candidate_template_id, str) and candidate_template_id.strip():
                    materialized_template_id = candidate_template_id.strip()
                materialization_mode = "import_runtime"
                break

    if materialized_puck_data is None:
        synthesis = provenance.get("synthesis")
        if not isinstance(synthesis, dict):
            raise SiteImportError(
                "Variant has no synthesized puckData. Rebuild the draft from the import first."
            )

        synthesized_puck_data = synthesis.get("synthesized_puck_data")
        if not isinstance(synthesized_puck_data, dict) or not synthesized_puck_data:
            raise SiteImportError(
                "Variant has no synthesized puckData. Rebuild the draft from the import first."
            )
        materialized_puck_data = synthesized_puck_data

    try:
        validate_puck_data_no_legacy_section_props(materialized_puck_data)
    except LegacySectionPropError as exc:
        raise SiteImportError(
            f"Cannot create site: legacy Section prop '{exc.prop_name}' is still present in the materialized draft."
        ) from exc

    resolved_template_id = materialized_template_id or provenance.get("template_id")
    if not isinstance(resolved_template_id, str) or not resolved_template_id.strip():
        resolved_template_id = (
            None if materialization_mode == "import_runtime" else FAMILY_TO_TEMPLATE_ID.get(variant.family, variant.family)
        )

    product_id = provenance.get("product_id")
    if not isinstance(product_id, str) or not product_id.strip():
        product_id = None

    commerce_provider = provenance.get("variant_provider")
    if not isinstance(commerce_provider, str) or not commerce_provider.strip():
        commerce_provider = None
    if not commerce_provider and source_import is not None:
        adapted_site = source_import.adapted_site or {}
        adapted_provider = adapted_site.get("commerce_provider") or adapted_site.get("commerceProvider")
        if isinstance(adapted_provider, str) and adapted_provider.strip():
            commerce_provider = adapted_provider

    route_slug = runtime_repo._generate_unique_route_slug(desired_slug=site_name or variant.name)
    page_slug = _slugify_page_type(materialized_page_type)
    page_name = _humanize_page_type(materialized_page_type)

    site_type = _default_site_type_for_page(materialized_page_type)
    if source_import is not None:
        adapted_site = source_import.adapted_site or {}
        adapted_site_type = adapted_site.get("site_type") or adapted_site.get("siteType")
        if isinstance(adapted_site_type, str) and adapted_site_type.strip():
            site_type = adapted_site_type

    try:
        site = runtime_repo.create_site(
            org_id=org_id,
            client_id=client_id,
            site_import_id=str(variant.site_import_id) if variant.site_import_id else None,
            product_id=product_id,
            name=site_name,
            description=description,
            site_type=site_type,
            site_family=(
                source_import.resolved_site_family
                if materialization_mode == "import_runtime"
                and source_import is not None
                and source_import.resolved_site_family
                else variant.family
            ),
            commerce_provider=commerce_provider,
            route_slug=route_slug,
            source_hostname=source_hostname if isinstance(source_hostname, str) else None,
            entry_page_type=materialized_page_type,
            imported_page_count=1,
            completeness_state="complete",
            created_by_user_external_id=created_by_user_external_id,
        )

        page = runtime_repo.create_page(
            site_id=str(site.id),
            name=page_name,
            slug=page_slug,
            page_type=materialized_page_type,
            page_role=materialized_page_type,
            template_id=resolved_template_id if isinstance(resolved_template_id, str) else None,
            page_template_id=resolved_template_id if isinstance(resolved_template_id, str) else None,
            ordering=0,
            source_url=source_url if isinstance(source_url, str) else None,
            source_screenshot_refs=screenshot_refs,
            adapted_puck_data=materialized_puck_data,
        )
        page_provenance = {
            "source_type": "template_variant",
            "variant_id": str(variant.id),
            "variant_name": variant.name,
            "variant_family": variant.family,
            "variant_page_type": variant.page_type,
            "site_import_id": str(variant.site_import_id) if variant.site_import_id else None,
            "source_url": source_url if isinstance(source_url, str) else None,
            "source_hostname": source_hostname if isinstance(source_hostname, str) else None,
            "template_id": resolved_template_id if isinstance(resolved_template_id, str) else None,
            "materialization_mode": materialization_mode,
        }
        draft_version = runtime_repo.create_page_version(
            page_id=str(page.id),
            puck_data=materialized_puck_data,
            provenance=page_provenance,
            status="draft",
            source_type="template_variant",
            source_id=str(variant.id),
        )
        approved_version = runtime_repo.create_page_version(
            page_id=str(page.id),
            puck_data=materialized_puck_data,
            provenance=page_provenance,
            status="approved",
            source_type="template_variant",
            source_id=str(variant.id),
        )

        site.entry_page_id = str(page.id)
        runtime_repo.update_site(site=site)

        updated_provenance = append_provenance_event(
            provenance,
            "materialize_site",
            actor=created_by_user_external_id,
            metadata={
                "site_id": str(site.id),
                "site_name": site.name,
                "page_id": str(page.id),
            },
        )
        updated_provenance["materialized_site_id"] = str(site.id)
        updated_provenance["materialized_site_name"] = site.name
        updated_provenance["materialized_page_id"] = str(page.id)
        repo.update_variant_status(
            org_id=org_id,
            client_id=client_id,
            variant_id=str(variant.id),
            new_status=variant.status,
            provenance_update=updated_provenance,
        )

        session.commit()
        session.refresh(site)
    except Exception as exc:
        session.rollback()
        raise SiteImportError("Failed to create site from approved template variant.") from exc

    return {
        "siteId": str(site.id),
        "siteName": site.name,
        "pageCount": 1,
        "entryPageType": materialized_page_type,
        "createdPages": [
            {
                "pageId": str(page.id),
                "pageType": materialized_page_type,
                "templateId": resolved_template_id if isinstance(resolved_template_id, str) else None,
                "versionId": str(draft_version.id),
                "approvedVersionId": str(approved_version.id),
            }
        ],
        "createdAt": site.created_at,
    }
