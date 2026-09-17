from __future__ import annotations

import re

HTML_DEPLOY_SCHEMA_VERSION = "html-deploy-v1"
FUNNEL_ARTIFACT_RENDER_MODE_HTML_DEPLOY = "html_deploy"
FUNNEL_ARTIFACT_RENDER_MODE_STANDALONE_IMPORTED_HTML = FUNNEL_ARTIFACT_RENDER_MODE_HTML_DEPLOY

HTML_DEPLOY_CANDIDATE_RELEASE_QUERY_PARAM = "mos_deploy_candidate_release"
HTML_DEPLOY_VALIDATION_CACHE_BUST_QUERY_PARAM = "mos_deploy_validation_cache_bust"
HTML_DEPLOY_CDN_CACHE_BUST_QUERY_PARAM = "cachebust"
HTML_DEPLOY_CANDIDATE_ACTIVATION_MODE = "candidate_only"
HTML_DEPLOY_CANDIDATE_RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

HTML_DEPLOY_BROWSER_RESOURCE_TYPES = {
    "font",
    "image",
    "imageset",
    "manifest",
    "media",
    "script",
    "stylesheet",
}
