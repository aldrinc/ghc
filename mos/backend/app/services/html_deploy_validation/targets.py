from __future__ import annotations

from typing import Any

from app.services.html_deploy_validation.urls import (
    append_url_query_params,
    html_deploy_page_fetch_url,
)


def expected_presales_source_page_type(*, path_plan: dict[str, Any]) -> str:
    start_page = path_plan.get("start_page") if isinstance(path_plan, dict) else {}
    artifact_kind = (
        str(start_page.get("html_artifact_kind") or "").strip().lower()
        if isinstance(start_page, dict)
        else ""
    )
    artifact_kind = artifact_kind.replace("-", "_")
    if artifact_kind in {"quiz", "quiz_funnel"}:
        return "quiz_presell"
    if artifact_kind in {"listicle", "listical", "listicle_hybrid"}:
        return "listical_presell"
    return ""


def html_deploy_validation_targets(*, validation_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_release_id = str(validation_plan.get("candidate_release_id") or "").strip()
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_target(*, page: dict[str, Any], url: str, context: str) -> None:
        if not isinstance(page, dict):
            return
        normalized_url = str(url or "").strip()
        if not normalized_url or normalized_url in seen:
            return
        seen.add(normalized_url)
        targets.append({"page": page, "url": normalized_url, "context": context})

    for page in validation_plan.get("pages_to_validate", []):
        if not isinstance(page, dict):
            continue
        page_url = str(page.get("url") or "").strip()
        if not page_url:
            continue
        add_target(
            page=page,
            url=html_deploy_page_fetch_url(
                page_url=page_url,
                candidate_release_id=candidate_release_id,
            ),
            context="canonical_page",
        )

    for index, path_plan in enumerate(validation_plan.get("path_plans", []) or []):
        if not isinstance(path_plan, dict) or not path_plan.get("pre_sales_click_selectors"):
            continue
        sales_page = path_plan.get("sales_page")
        if not isinstance(sales_page, dict):
            continue
        sales_url = str(sales_page.get("url") or "").strip()
        if not sales_url:
            continue
        source_page_type = expected_presales_source_page_type(path_plan=path_plan)
        handoff_url = append_url_query_params(
            sales_url,
            {
                "src": "presale",
                "from": "quiz" if source_page_type == "quiz_presell" else "listicle",
                "source_page_type": source_page_type or "pre_sales",
                "from_stage": "pre_sales",
                "to_stage": "sales",
                "session_id": f"deploy-validation-session-{index + 1}",
                "visitor_id": f"deploy-validation-visitor-{index + 1}",
                "click_id": f"deploy-validation-click-{index + 1}",
                "campaign_id": f"deploy-validation-campaign-{index + 1}",
                "ad_id": f"deploy-validation-ad-{index + 1}",
            },
        )
        add_target(
            page=sales_page,
            url=html_deploy_page_fetch_url(
                page_url=handoff_url,
                candidate_release_id=candidate_release_id,
            ),
            context="tracked_sales_handoff",
        )

    return targets
