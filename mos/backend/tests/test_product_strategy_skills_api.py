from __future__ import annotations

from app.services.product_strategy_bundles import ProductStrategyBundlesError
from app.services.skills_runtime_registry import DEFAULT_SKILL_BUNDLE_KEY


def _create_product(api_client, *, suffix: str) -> tuple[str, str]:
    client_resp = api_client.post("/clients", json={"name": f"Client {suffix}", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": f"Product {suffix}"},
    )
    assert product_resp.status_code == 201
    return client_id, product_resp.json()["id"]


def test_strategy_skills_status_endpoint_returns_binding_and_bundles(api_client, monkeypatch) -> None:
    client_id, product_id = _create_product(api_client, suffix="skills-status")

    monkeypatch.setattr(
        "app.routers.product_strategy_skills.SkillsRuntimeRegistryService.get_workspace_binding",
        lambda self, bundle_key=DEFAULT_SKILL_BUNDLE_KEY: {
            "id": "binding-1",
            "bundleKey": bundle_key,
            "bundleFamily": "ember",
            "releaseId": "release-1",
            "status": "active",
            "metadata": {},
        },
    )

    def _fake_get_active_bundle(self, *, bundle_type: str):
        if bundle_type == "foundational_docs":
            return {
                "id": "foundation-1",
                "bundleType": bundle_type,
                "items": [],
                "metadata": {
                    "isComplete": False,
                    "expectedDocKeys": ["v2-02.foundation.01", "v2-02.foundation.02"],
                    "presentDocKeys": ["v2-02.foundation.01"],
                    "missingDocKeys": ["v2-02.foundation.02"],
                },
            }
        if bundle_type == "skills_working":
            return {"id": "working-1", "bundleType": bundle_type, "items": []}
        if bundle_type == "skills_handoff":
            return {
                "id": "handoff-1",
                "bundleType": bundle_type,
                "items": [],
                "isActive": True,
                "createdAt": "2026-04-02T00:00:00+00:00",
            }
        raise ProductStrategyBundlesError("missing")

    monkeypatch.setattr(
        "app.routers.product_strategy_skills.ProductStrategyBundlesService.get_active_bundle",
        _fake_get_active_bundle,
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.ProductStrategyBundlesService.list_bundles",
        lambda self, bundle_type=None: [
            {
                "id": "handoff-pending-1",
                "bundleType": "skills_handoff",
                "isActive": False,
                "createdAt": "2026-04-02T00:00:01+00:00",
            },
            {
                "id": "handoff-history-1",
                "bundleType": "skills_handoff",
                "isActive": False,
                "createdAt": "2026-04-01T23:59:58+00:00",
            },
            {
                "id": "handoff-active-1",
                "bundleType": "skills_handoff",
                "isActive": True,
                "createdAt": "2026-04-02T00:00:00+00:00",
            },
        ]
        if bundle_type == "skills_handoff"
        else [],
    )

    response = api_client.get(f"/products/{product_id}/strategy-skills/status")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["clientId"] == client_id
    assert payload["productId"] == product_id
    assert payload["skillsBinding"]["id"] == "binding-1"
    assert payload["activeFoundationalBundle"]["id"] == "foundation-1"
    assert payload["activeWorkingBundle"]["id"] == "working-1"
    assert payload["activeHandoffBundle"]["id"] == "handoff-1"
    assert payload["pendingHandoffBundles"][0]["id"] == "handoff-pending-1"
    assert payload["historicalHandoffBundles"][0]["id"] == "handoff-history-1"
    assert payload["foundationalCompleteness"]["missingDocKeys"] == ["v2-02.foundation.02"]


def test_strategy_skills_bootstrap_endpoint_calls_services(api_client, monkeypatch) -> None:
    client_id, product_id = _create_product(api_client, suffix="skills-bootstrap")

    monkeypatch.setattr(
        "app.routers.product_strategy_skills.SkillsRuntimeRegistryService.sync_ember_skills_release",
        lambda self, **_kwargs: {
            "packageId": "package-1",
            "releaseId": "release-1",
            "version": "2026-04-01",
            "assetCount": 10,
            "runtimeProfiles": ["strategy", "offer", "copy", "page-copy"],
        },
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.SkillsRuntimeRegistryService.ensure_workspace_binding",
        lambda self, **_kwargs: {
            "id": "binding-1",
            "bundleKey": DEFAULT_SKILL_BUNDLE_KEY,
            "bundleFamily": "ember",
            "releaseId": "release-1",
            "status": "active",
        },
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.ProductStrategyBundlesService.import_foundational_bundle",
        lambda self, **_kwargs: {
            "id": "foundation-1",
            "bundleType": "foundational_docs",
            "items": [],
        },
    )
    response = api_client.post(
        f"/products/{product_id}/strategy-skills/bootstrap",
        json={
            "releaseVersion": "2026-04-01",
            "strategyRoot": "/tmp/strategy-root",
            "foundationalRoot": "/tmp/foundational-root",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["clientId"] == client_id
    assert payload["productId"] == product_id
    assert payload["release"]["releaseId"] == "release-1"
    assert payload["binding"]["id"] == "binding-1"
    assert payload["foundationalBundle"]["id"] == "foundation-1"
    assert payload["workingBundle"] is None
    assert payload["handoffBundle"] is None


def test_strategy_skills_stage_and_selection_endpoints_delegate_to_flow(api_client, monkeypatch) -> None:
    _, product_id = _create_product(api_client, suffix="skills-stage")

    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.run_stage",
        lambda self, **_kwargs: {"stageKey": "signal_report", "artifactId": "artifact-1"},
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.select_angle",
        lambda self, **_kwargs: {"artifactId": "angle-selection-1"},
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.select_headline",
        lambda self, **_kwargs: {"artifactId": "headline-selection-1"},
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.approve_working_role",
        lambda self, **_kwargs: {"pendingHandoffBundle": {"id": "handoff-pending-1"}},
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.activate_handoff_bundle",
        lambda self, **_kwargs: {"activeHandoffBundle": {"id": "handoff-active-1"}},
    )
    monkeypatch.setattr(
        "app.routers.product_strategy_skills.EmberSkillsFlowService.seed_working_bundle_from_foundation",
        lambda self, **_kwargs: {
            "workingBundle": {"id": "working-1"},
            "handoffBundle": {"id": "handoff-1"},
        },
    )

    approval_response = api_client.post(
        f"/products/{product_id}/strategy-skills/foundational/approve",
        json={"allowIncomplete": True},
    )
    assert approval_response.status_code == 200, approval_response.text
    assert approval_response.json()["result"]["workingBundle"]["id"] == "working-1"

    stage_response = api_client.post(
        f"/products/{product_id}/strategy-skills/stages/signal_report",
        json={"bundleKey": DEFAULT_SKILL_BUNDLE_KEY, "promoteToActiveBundle": False},
    )
    assert stage_response.status_code == 200, stage_response.text
    assert stage_response.json()["result"]["artifactId"] == "artifact-1"

    angle_response = api_client.post(
        f"/products/{product_id}/strategy-skills/select-angle",
        json={"selectedId": "angle-1", "rationale": "Approved angle"},
    )
    assert angle_response.status_code == 200, angle_response.text
    assert angle_response.json()["result"]["artifactId"] == "angle-selection-1"

    headline_response = api_client.post(
        f"/products/{product_id}/strategy-skills/select-headline",
        json={"selectedId": "headline-1", "rationale": "Approved headline"},
    )
    assert headline_response.status_code == 200, headline_response.text
    assert headline_response.json()["result"]["artifactId"] == "headline-selection-1"

    approve_response = api_client.post(
        f"/products/{product_id}/strategy-skills/approve-role",
        json={"role": "signal_report"},
    )
    assert approve_response.status_code == 200, approve_response.text
    assert approve_response.json()["result"]["pendingHandoffBundle"]["id"] == "handoff-pending-1"

    activate_response = api_client.post(
        f"/products/{product_id}/strategy-skills/handoff/activate",
        json={"bundleId": "handoff-pending-1"},
    )
    assert activate_response.status_code == 200, activate_response.text
    assert activate_response.json()["result"]["activeHandoffBundle"]["id"] == "handoff-active-1"
