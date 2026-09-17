"""Deterministic html-deploy-v1 candidate release validators.

`deploy.py` owns publish orchestration; this package owns the validator internals it
runs against an inactive candidate release before activation.
"""

from __future__ import annotations

from app.services.html_deploy_validation.constants import (
    FUNNEL_ARTIFACT_RENDER_MODE_HTML_DEPLOY,
    FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML,
    HTML_DEPLOY_BROWSER_RESOURCE_TYPES,
    HTML_DEPLOY_CANDIDATE_ACTIVATION_MODE,
    HTML_DEPLOY_CANDIDATE_RELEASE_ID_RE,
    HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM,
    HTML_DEPLOY_CDN_CACHE_BUST_QUERY_PARAM,
    HTML_DEPLOY_SCHEMA_VERSION,
    HTML_DEPLOY_VALIDATION_CACHE_BUST_QUERY_PARAM,
)
from app.services.html_deploy_validation.lighthouse import (
    extract_lighthouse_audit_summary,
    html_deploy_lighthouse_enabled,
    html_deploy_lighthouse_threshold,
    html_deploy_lighthouse_urls,
    normalize_lighthouse_score,
    run_html_deploy_lighthouse_validation_sync,
    run_single_html_deploy_lighthouse_audit,
)
from app.services.html_deploy_validation.optimization import (
    assert_html_deploy_image_urls_resolve,
    assert_html_deploy_optimization_markers,
    assert_html_deploy_resource_urls_resolve,
    run_html_deploy_optimization_validation_sync,
)
from app.services.html_deploy_validation.page_parser import (
    HtmlDeployOptimizationParser,
    html_deploy_image_reference_urls,
    html_deploy_resource_reference_urls,
)
from app.services.html_deploy_validation.targets import (
    expected_presales_source_page_type,
    html_deploy_validation_targets,
)
from app.services.html_deploy_validation.urls import (
    append_url_query_params,
    html_deploy_browser_resource_failure_message,
    html_deploy_is_data_or_empty_url,
    html_deploy_is_raster_image_url,
    html_deploy_is_svg_url,
    html_deploy_no_trailing_slash_url,
    html_deploy_page_fetch_url,
    html_deploy_route_asset_prefix_for_page_url,
    html_deploy_route_asset_prefixes_for_path_plan,
    html_deploy_should_validate_resource_url,
    html_deploy_srcset_urls,
    validate_html_deploy_candidate_release_id,
)

__all__ = [
    "FUNNEL_ARTIFACT_RENDER_MODE_HTML_DEPLOY",
    "FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML",
    "HTML_DEPLOY_BROWSER_RESOURCE_TYPES",
    "HTML_DEPLOY_CANDIDATE_ACTIVATION_MODE",
    "HTML_DEPLOY_CANDIDATE_RELEASE_ID_RE",
    "HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM",
    "HTML_DEPLOY_CDN_CACHE_BUST_QUERY_PARAM",
    "HTML_DEPLOY_SCHEMA_VERSION",
    "HTML_DEPLOY_VALIDATION_CACHE_BUST_QUERY_PARAM",
    "HtmlDeployOptimizationParser",
    "append_url_query_params",
    "assert_html_deploy_image_urls_resolve",
    "assert_html_deploy_optimization_markers",
    "assert_html_deploy_resource_urls_resolve",
    "expected_presales_source_page_type",
    "extract_lighthouse_audit_summary",
    "html_deploy_browser_resource_failure_message",
    "html_deploy_image_reference_urls",
    "html_deploy_is_data_or_empty_url",
    "html_deploy_is_raster_image_url",
    "html_deploy_is_svg_url",
    "html_deploy_lighthouse_enabled",
    "html_deploy_lighthouse_threshold",
    "html_deploy_lighthouse_urls",
    "html_deploy_no_trailing_slash_url",
    "html_deploy_page_fetch_url",
    "html_deploy_resource_reference_urls",
    "html_deploy_route_asset_prefix_for_page_url",
    "html_deploy_route_asset_prefixes_for_path_plan",
    "html_deploy_should_validate_resource_url",
    "html_deploy_srcset_urls",
    "html_deploy_validation_targets",
    "normalize_lighthouse_score",
    "run_html_deploy_lighthouse_validation_sync",
    "run_html_deploy_optimization_validation_sync",
    "run_single_html_deploy_lighthouse_audit",
    "validate_html_deploy_candidate_release_id",
]
