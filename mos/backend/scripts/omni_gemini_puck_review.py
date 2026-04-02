from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.config import settings  # noqa: F401  # ensure env files are loaded
from app.db.deps import SessionLocal
from app.db.models import Site, SiteImport, SitePage, SitePageVersion
from app.db.repositories.sites_runtime import SitesRuntimeRepository
from app.services.site_import_archive import (
    _RUNTIME_PRESERVED_COMPONENT_NAMES,
    _translate_source_backed_section,
)
from app.services.site_templates import create_template_from_site, instantiate_template


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_ROOT = REPO_ROOT / ".local" / "hermes" / "gemini-puck-review"
SOURCE_SITE_ID = "e34844f6-6eec-4de0-97e8-b635bba65f58"
SOURCE_IMPORT_ID = "5eca3b2c-d2df-40b8-900d-597e7c51aedd"
FRONTEND_BASE_URL = "http://127.0.0.1:5275"
FOCUS_SECTION_IDS = (
    "global-header",
    "snackable-packable",
    "us-vs-them",
    "any-last-questions",
)


@dataclass
class ReviewResult:
    template_id: str
    site_id: str
    page_id: str
    preview_url: str
    editor_url: str
    report_dir: Path
    section_summary: list[dict[str, object]]
    translation_mode: str


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


def _load_source_context(session):
    source_site = session.scalars(select(Site).where(Site.id == SOURCE_SITE_ID)).first()
    if source_site is None:
        raise RuntimeError(f"Source site not found: {SOURCE_SITE_ID}")

    source_import = session.scalars(select(SiteImport).where(SiteImport.id == SOURCE_IMPORT_ID)).first()
    if source_import is None:
        raise RuntimeError(f"Source import not found: {SOURCE_IMPORT_ID}")

    entry_page = session.scalars(select(SitePage).where(SitePage.id == source_site.entry_page_id)).first()
    if entry_page is None:
        raise RuntimeError(f"Source entry page not found: {source_site.entry_page_id}")

    version = session.scalars(
        select(SitePageVersion)
        .where(SitePageVersion.page_id == str(entry_page.id))
        .order_by(SitePageVersion.created_at.desc())
    ).first()
    puck_data = version.puck_data if version and isinstance(version.puck_data, dict) else entry_page.adapted_puck_data
    if not isinstance(puck_data, dict):
        raise RuntimeError("Source entry page is missing puck data.")

    return source_site, source_import, entry_page, puck_data


def _prewarm_section_translations(
    *,
    source_import: SiteImport,
    puck_data: dict[str, object],
) -> None:
    imported_page = ((puck_data.get("content") or [None])[0] or {})
    if not isinstance(imported_page, dict):
        raise RuntimeError("Expected ImportedPage puck data while prewarming section translations.")
    imported_page_props = imported_page.get("props") or {}
    if not isinstance(imported_page_props, dict):
        raise RuntimeError("Malformed ImportedPage props while prewarming section translations.")
    runtime_source = str(imported_page_props.get("sharedRuntimeSource") or "")
    if not runtime_source.strip():
        raise RuntimeError("Imported source page is missing sharedRuntimeSource for translation prewarm.")

    for section in source_import.normalized_sections or []:
        component_name = str(section.get("componentName") or "").strip() or "App"
        if component_name in _RUNTIME_PRESERVED_COMPONENT_NAMES:
            continue
        _translate_source_backed_section(section=section, runtime_source=runtime_source)


def _extract_section_map(puck_data: dict[str, object]) -> dict[str, dict[str, object]]:
    imported_page = ((puck_data.get("content") or [None])[0] or {})
    if not isinstance(imported_page, dict):
        raise RuntimeError("Expected ImportedPage puck data.")
    content = ((imported_page.get("props") or {}).get("content") or [])
    result: dict[str, dict[str, object]] = {}
    for section in content:
        if not isinstance(section, dict):
            continue
        props = section.get("props") or {}
        if not isinstance(props, dict):
            continue
        section_id = str(props.get("sourceSectionId") or "").strip()
        if section_id:
            result[section_id] = section
    return result


def _summarize_slot_items(items: list[dict[str, object]]) -> list[dict[str, str]]:
    summary: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary.append(
            {
                "label": str(item.get("label") or ""),
                "originalText": str(item.get("originalText") or ""),
                "text": str(item.get("text") or ""),
                "href": str(item.get("href") or ""),
                "originalSrc": str(item.get("originalSrc") or ""),
                "src": str(item.get("src") or ""),
                "alt": str(item.get("alt") or ""),
            }
        )
    return summary


def _build_focus_section_summary(
    section_map: dict[str, dict[str, object]]
) -> list[dict[str, object]]:
    summary: list[dict[str, object]] = []
    for section_id in FOCUS_SECTION_IDS:
        section = section_map.get(section_id)
        if not isinstance(section, dict):
            raise RuntimeError(f"Missing focus section in instantiated page: {section_id}")
        section_props = section.get("props") or {}
        if not isinstance(section_props, dict):
            raise RuntimeError(f"Malformed section props for {section_id}")
        blocks = section_props.get("content") or []
        if not isinstance(blocks, list) or not blocks:
            raise RuntimeError(f"Section {section_id} has no content blocks.")
        block = blocks[0]
        if not isinstance(block, dict):
            raise RuntimeError(f"Malformed content block for {section_id}")
        block_props = block.get("props") or {}
        if not isinstance(block_props, dict):
            raise RuntimeError(f"Malformed block props for {section_id}")
        summary.append(
            {
                "sectionId": section_id,
                "blockType": str(block.get("type") or ""),
                "textSlots": _summarize_slot_items(list(block_props.get("textSlots") or [])),
                "buttonSlots": _summarize_slot_items(list(block_props.get("buttonSlots") or [])),
                "imageSlots": _summarize_slot_items(list(block_props.get("imageSlots") or [])),
            }
        )
    return summary


def _validate_focus_sections(section_summary: list[dict[str, object]]) -> None:
    by_id = {str(item["sectionId"]): item for item in section_summary}

    header = by_id["global-header"]
    header_images = header["imageSlots"]
    if not any(item["originalText"] == "OMNI" or item["originalSrc"] for item in header_images):
        raise RuntimeError("Header section is missing a valid logo image slot.")
    if not any(item["text"] == "OMNI" for item in header["textSlots"]):
        raise RuntimeError("Header section is missing the OMNI logo text slot value.")

    proof = by_id["snackable-packable"]
    proof_texts = {item["originalText"] for item in proof["textSlots"]}
    for expected in {
        "80%",
        "65%",
        "40%",
        "92%",
        "Demonstrated increases in strength or power output.",
        "Reported better endurance during high-intensity workouts.",
        "Saw an improvement in mental clarity and cognitive tasks.",
        "Experienced faster recovery between intense exercise sets.",
    }:
        if expected not in proof_texts:
            raise RuntimeError(f"Proof section is missing required stat slot: {expected}")

    comparison = by_id["us-vs-them"]
    comparison_texts = {item["originalText"] for item in comparison["textSlots"]}
    for expected in {
        "Benefits",
        "OMNI Gummies",
        "Creatine Powders",
        "Other Gummies",
        "3g Creatine Monohydrate",
        "Travel Friendly",
    }:
        if expected not in comparison_texts:
            raise RuntimeError(f"Comparison section is missing required slot: {expected}")

    faq = by_id["any-last-questions"]
    faq_texts = {item["originalText"] for item in faq["textSlots"]}
    for expected in {
        "How many gummies should I take daily?",
        "Do I need to load creatine?",
        "When is the best time to take OMNI?",
        "Are these gummies vegan and gluten-free?",
        "Will creatine make me bloated or retain water?",
    }:
        if expected not in faq_texts:
            raise RuntimeError(f"FAQ section is missing required slot: {expected}")


def run_review() -> ReviewResult:
    timestamp = _timestamp_slug()
    run_dir = REPORTS_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    original_flag = settings.SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED
    try:
        settings.SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED = True
        source_site, source_import, _, source_puck_data = _load_source_context(session)
        _prewarm_section_translations(source_import=source_import, puck_data=source_puck_data)
        template_name = f"OMNI Gemini Puck Review {timestamp}"
        site_name = f"OMNI Gemini Review Site {timestamp}"

        template = create_template_from_site(
            session,
            site_id=str(source_site.id),
            org_id=str(source_site.org_id),
            client_id=str(source_site.client_id),
            name=template_name,
            description="Gemini-translated imported source sections rendered in native Puck blocks.",
            created_by_user_external_id="codex",
        )
        instantiated = instantiate_template(
            session,
            template_id=str(template.id),
            org_id=str(source_site.org_id),
            client_id=str(source_site.client_id),
            name=site_name,
            description="Gemini-translated imported source review site.",
            created_by_user_external_id="codex",
        )
        session.commit()

        site_id = str(instantiated["siteId"])
        site = session.scalars(select(Site).where(Site.id == site_id)).first()
        if site is None:
            raise RuntimeError(f"Instantiated review site not found: {site_id}")
        home_page = session.scalars(
            select(SitePage)
            .where(SitePage.site_id == site_id, SitePage.page_type == "home")
            .order_by(SitePage.ordering.asc())
        ).first()
        if home_page is None:
            raise RuntimeError(f"Instantiated review site is missing a home page: {site_id}")

        runtime_repo = SitesRuntimeRepository(session)
        approved = runtime_repo.latest_version_for_page(page_id=str(home_page.id), status="approved")
        if approved is None or not isinstance(approved.puck_data, dict):
            raise RuntimeError(f"Instantiated review home page is missing approved puck data: {home_page.id}")

        section_map = _extract_section_map(approved.puck_data)
        section_summary = _build_focus_section_summary(section_map)
        _validate_focus_sections(section_summary)

        preview_url = f"{FRONTEND_BASE_URL}/workspaces/sites/{site_id}/preview/us"
        editor_url = f"{FRONTEND_BASE_URL}/workspaces/sites/{site_id}/pages/{home_page.id}"

        report_payload = {
            "translationMode": "llm_source_section_translation",
            "flagName": "SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED",
            "flagValue": True,
            "templateId": str(template.id),
            "siteId": site_id,
            "pageId": str(home_page.id),
            "previewUrl": preview_url,
            "editorUrl": editor_url,
            "focusSections": section_summary,
        }
        (run_dir / "report.json").write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        (run_dir / "home-page-puck-data.json").write_text(
            json.dumps(approved.puck_data, indent=2),
            encoding="utf-8",
        )

        summary_lines = [
            "# OMNI Gemini Puck Review",
            "",
            "## Decision",
            "Built a fresh imported-template review site from the real OMNI source using the Gemini section translator instead of parsedData-derived slots.",
            "",
            "## Flag",
            "- `SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED=true`",
            "",
            "## Review Links",
            f"- Preview: {preview_url}",
            f"- Editor: {editor_url}",
            "",
            "## Focus Section Validation",
        ]
        for section in section_summary:
            summary_lines.append(
                f"- `{section['sectionId']}` -> `{section['blockType']}` "
                f"({len(section['textSlots'])} text slots, {len(section['buttonSlots'])} button slots, {len(section['imageSlots'])} image slots)"
            )
        summary_lines.extend(
            [
                "",
                "## Artifacts",
                f"- Report JSON: `{run_dir / 'report.json'}`",
                f"- Home page puckData: `{run_dir / 'home-page-puck-data.json'}`",
            ]
        )
        (run_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        return ReviewResult(
            template_id=str(template.id),
            site_id=site_id,
            page_id=str(home_page.id),
            preview_url=preview_url,
            editor_url=editor_url,
            report_dir=run_dir,
            section_summary=section_summary,
            translation_mode="llm_source_section_translation",
        )
    except Exception:
        session.rollback()
        raise
    finally:
        settings.SITE_IMPORT_LLM_SOURCE_SECTION_TRANSLATION_ENABLED = original_flag
        session.close()


def main() -> None:
    result = run_review()
    print(json.dumps(
        {
            "translationMode": result.translation_mode,
            "templateId": result.template_id,
            "siteId": result.site_id,
            "pageId": result.page_id,
            "previewUrl": result.preview_url,
            "editorUrl": result.editor_url,
            "reportDir": str(result.report_dir),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
