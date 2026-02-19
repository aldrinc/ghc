from __future__ import annotations

import pytest
from pydantic import ValidationError

from cloudhand.models import ApplicationSourceType, ApplicationSpec


def _base_app_payload() -> dict:
    return {
        "name": "sample-app",
        "runtime": "nodejs",
        "build_config": {
            "install_command": "npm ci",
            "build_command": "npm run build",
            "system_packages": [],
        },
        "service_config": {
            "command": "npm run start",
            "environment": {},
            "ports": [3000],
            "server_names": ["example.com"],
            "https": True,
        },
        "destination_path": "/opt/apps",
    }


def test_git_source_requires_repo_url():
    payload = _base_app_payload()
    with pytest.raises(ValidationError, match="repo_url is required when source_type='git'"):
        ApplicationSpec.model_validate(payload)


def test_git_source_allows_default_source_type_when_repo_url_present():
    payload = _base_app_payload()
    payload["repo_url"] = "https://github.com/example/repo"
    app = ApplicationSpec.model_validate(payload)
    assert app.source_type == ApplicationSourceType.GIT
    assert app.repo_url == "https://github.com/example/repo"


def test_funnel_publication_source_requires_source_ref_and_forbids_repo_url():
    payload = _base_app_payload()
    payload["source_type"] = "funnel_publication"
    payload["repo_url"] = "https://github.com/example/repo"
    with pytest.raises(ValidationError, match="repo_url is not allowed when source_type='funnel_publication'"):
        ApplicationSpec.model_validate(payload)


def test_funnel_publication_source_validates_required_fields():
    payload = _base_app_payload()
    payload["source_type"] = "funnel_publication"
    payload["service_config"]["command"] = None
    payload["service_config"]["ports"] = []
    payload["source_ref"] = {
        "public_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        "upstream_base_url": "https://moshq.app/",
        "upstream_api_base_url": "https://moshq.app/api/",
    }
    app = ApplicationSpec.model_validate(payload)
    assert app.source_type == ApplicationSourceType.FUNNEL_PUBLICATION
    assert app.source_ref is not None
    assert app.source_ref.upstream_base_url == "https://moshq.app"
    assert app.source_ref.upstream_api_base_url == "https://moshq.app/api"


def test_funnel_artifact_source_validates_required_fields():
    payload = _base_app_payload()
    payload["source_type"] = "funnel_artifact"
    payload["service_config"]["command"] = None
    payload["service_config"]["ports"] = []
    payload["source_ref"] = {
        "client_id": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
        "upstream_api_base_root": "https://moshq.app/api/",
        "runtime_dist_path": "mos/frontend/dist",
        "artifact": {
            "meta": {
                "clientId": "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95",
            },
            "products": {
                "example-product": {
                    "meta": {
                        "productId": "p1",
                        "productSlug": "example-product",
                    },
                    "funnels": {
                        "example-funnel": {
                            "meta": {
                                "funnelSlug": "example-funnel",
                                "funnelId": "f1",
                                "publicationId": "pub1",
                                "entrySlug": "presales",
                                "pages": [{"pageId": "p1", "slug": "presales"}],
                            },
                            "pages": {
                                "presales": {
                                    "funnelId": "f1",
                                    "publicationId": "pub1",
                                    "pageId": "p1",
                                    "slug": "presales",
                                    "puckData": {"root": {"props": {}}, "content": [], "zones": {}},
                                    "pageMap": {"p1": "presales"},
                                }
                            },
                        }
                    }
                }
            },
        },
    }
    app = ApplicationSpec.model_validate(payload)
    assert app.source_type == ApplicationSourceType.FUNNEL_ARTIFACT
    assert app.source_ref is not None
    assert app.source_ref.client_id == "f4f7f3e0-00c9-4c17-9a8f-4f3d72095f95"
    assert app.source_ref.upstream_api_base_root == "https://moshq.app/api"


def test_funnel_artifact_source_legacy_shape_is_rejected():
    payload = _base_app_payload()
    payload["source_type"] = "funnel_artifact"
    payload["service_config"]["command"] = None
    payload["service_config"]["ports"] = []
    payload["source_ref"] = {
        "upstream_api_base_url": "https://moshq.app/api/",
        "artifact": {
            "meta": {
                "productId": None,
                "offers": [],
            },
            "funnels": {
                "legacy-funnel": {
                    "meta": {},
                    "pages": {},
                }
            },
        },
    }

    with pytest.raises(ValidationError):
        ApplicationSpec.model_validate(payload)
