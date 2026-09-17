from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.deploy_errors import DeployError
from app.services.html_deploy_validation.constants import (
    FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
    HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM,
)
from app.services.html_deploy_validation.urls import (
    append_url_query_params,
    validate_html_deploy_candidate_release_id,
)


def html_deploy_lighthouse_enabled(*, validation_plan: dict[str, Any]) -> bool:
    if validation_plan.get("render_mode") != FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        return False
    if not bool(settings.DEPLOY_HTML_DEPLOY_LIGHTHOUSE_ENABLED):
        return False
    return bool(str(validation_plan.get("candidate_release_id") or "").strip())


def html_deploy_lighthouse_threshold(*, profile: str) -> float:
    normalized_profile = str(profile or "").strip().lower()
    if normalized_profile == "desktop":
        return float(settings.DEPLOY_HTML_DEPLOY_LIGHTHOUSE_DESKTOP_MIN_SCORE)
    if normalized_profile == "mobile":
        return float(settings.DEPLOY_HTML_DEPLOY_LIGHTHOUSE_MOBILE_MIN_SCORE)
    raise DeployError(f"Unsupported Lighthouse validation profile '{profile}'.")


def normalize_lighthouse_score(score: Any) -> float:
    try:
        value = float(score)
    except (TypeError, ValueError) as exc:
        raise DeployError(
            "HTML deploy Lighthouse validation failed: missing performance score."
        ) from exc
    if value <= 1.0:
        return value * 100.0
    return value


def html_deploy_lighthouse_urls(*, validation_plan: dict[str, Any]) -> list[str]:
    candidate_release_id = str(validation_plan.get("candidate_release_id") or "").strip()
    query_params: dict[str, str] = {}
    if candidate_release_id:
        query_params[HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM] = (
            validate_html_deploy_candidate_release_id(candidate_release_id)
        )

    urls: list[str] = []
    seen: set[str] = set()
    for page in validation_plan.get("pages_to_validate", []):
        if not isinstance(page, dict):
            continue
        page_url = str(page.get("url") or "").strip()
        if not page_url:
            continue
        audit_url = append_url_query_params(page_url, query_params) if query_params else page_url
        if audit_url in seen:
            continue
        seen.add(audit_url)
        urls.append(audit_url)
    return urls


def extract_lighthouse_audit_summary(*, report: dict[str, Any]) -> dict[str, Any]:
    audits = report.get("audits") if isinstance(report.get("audits"), dict) else {}
    summary: dict[str, Any] = {}
    for audit_id in (
        "first-contentful-paint",
        "largest-contentful-paint",
        "speed-index",
        "total-blocking-time",
        "cumulative-layout-shift",
    ):
        audit = audits.get(audit_id) if isinstance(audits, dict) else None
        if not isinstance(audit, dict):
            continue
        summary[audit_id] = {
            "score": audit.get("score"),
            "numericValue": audit.get("numericValue"),
            "displayValue": audit.get("displayValue"),
        }
    return summary


def run_single_html_deploy_lighthouse_audit(*, url: str, profile: str) -> dict[str, Any]:
    command = shlex.split(str(settings.DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND or "").strip())
    if not command:
        raise DeployError(
            "HTML deploy Lighthouse validation requires DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND."
        )
    normalized_profile = str(profile or "").strip().lower()
    if normalized_profile not in {"mobile", "desktop"}:
        raise DeployError(f"Unsupported Lighthouse validation profile '{profile}'.")

    threshold = html_deploy_lighthouse_threshold(profile=normalized_profile)
    timeout_seconds = max(1.0, float(settings.DEPLOY_HTML_DEPLOY_LIGHTHOUSE_TIMEOUT_SECONDS))
    with tempfile.TemporaryDirectory(prefix="mos-html-deploy-lighthouse-") as tmp_dir:
        report_path = Path(tmp_dir) / f"{normalized_profile}.json"
        args = [
            *command,
            url,
            "--quiet",
            "--output=json",
            f"--output-path={report_path}",
            "--only-categories=performance",
            "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage",
        ]
        if normalized_profile == "desktop":
            args.append("--preset=desktop")
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DeployError(
                "HTML deploy Lighthouse validation failed: command "
                f"'{command[0]}' was not found. Install Lighthouse or set "
                "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_COMMAND to the exact executable."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DeployError(
                "HTML deploy Lighthouse validation failed: command timed out after "
                f"{timeout_seconds:.1f}s for {normalized_profile} audit of '{url}'."
            ) from exc
        if completed.returncode != 0:
            output = "\n".join(
                part.strip()
                for part in (completed.stdout, completed.stderr)
                if str(part or "").strip()
            )
            raise DeployError(
                "HTML deploy Lighthouse validation failed for "
                f"{normalized_profile} audit of '{url}' with exit code {completed.returncode}: "
                f"{output[-2000:]}"
            )
        if not report_path.is_file():
            raise DeployError(
                "HTML deploy Lighthouse validation failed: Lighthouse did not write a JSON report "
                f"for {normalized_profile} audit of '{url}'."
            )
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeployError(
                "HTML deploy Lighthouse validation failed: Lighthouse wrote invalid JSON "
                f"for {normalized_profile} audit of '{url}'."
            ) from exc

    categories = report.get("categories") if isinstance(report, dict) else {}
    performance = (
        categories.get("performance")
        if isinstance(categories, dict) and isinstance(categories.get("performance"), dict)
        else {}
    )
    score = normalize_lighthouse_score(performance.get("score"))
    result = {
        "url": url,
        "profile": normalized_profile,
        "performanceScore": round(score, 2),
        "minimumScore": threshold,
        "audits": extract_lighthouse_audit_summary(report=report),
    }
    if score < threshold:
        raise DeployError(
            "HTML deploy Lighthouse validation failed for "
            f"{normalized_profile} audit of '{url}': performance score "
            f"{score:.2f} is below required {threshold:.2f}."
        )
    return result


def run_html_deploy_lighthouse_validation_sync(
    *,
    validation_plan: dict[str, Any],
) -> dict[str, Any] | None:
    if validation_plan.get("render_mode") != FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML:
        return None
    if not html_deploy_lighthouse_enabled(validation_plan=validation_plan):
        return {
            "status": "not_applicable",
            "candidateReleaseId": validation_plan.get("candidate_release_id"),
            "reason": (
                "HTML deploy Lighthouse validation is not applicable without "
                "DEPLOY_HTML_DEPLOY_LIGHTHOUSE_ENABLED and a candidate release id."
            ),
            "audits": [],
        }
    urls = html_deploy_lighthouse_urls(validation_plan=validation_plan)
    if not urls:
        raise DeployError("HTML deploy Lighthouse validation requires at least one page URL.")

    audits: list[dict[str, Any]] = []
    for url in urls:
        for profile in ("mobile", "desktop"):
            audits.append(run_single_html_deploy_lighthouse_audit(url=url, profile=profile))
    return {
        "status": "passed",
        "candidateReleaseId": validation_plan.get("candidate_release_id"),
        "thresholds": {
            "mobile": html_deploy_lighthouse_threshold(profile="mobile"),
            "desktop": html_deploy_lighthouse_threshold(profile="desktop"),
        },
        "audits": audits,
    }
