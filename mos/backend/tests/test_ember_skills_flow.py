import pytest

from app.services.ember_skills_flow import EmberSkillsFlowError, EmberSkillsFlowService
from app.services.product_strategy_bundles import ProductStrategyBundlesService
from app.db.models import Client, Product
from tests.conftest import TEST_ORG_ID


def test_validate_stage_requirements_rejects_missing_prior_roles():
    bundle_payload = {
        "items": [
            {"role": "foundational:v2-02.foundation.01"},
            {"role": "signal_report"},
        ]
    }
    spec = {
        "required_roles": ("signal_report", "angle_selection"),
    }

    with pytest.raises(
        EmberSkillsFlowError,
        match="Stage 'knowledge_base' requires prior approved roles: angle_selection.",
    ):
        EmberSkillsFlowService._validate_stage_requirements(
            bundle_payload=bundle_payload,
            spec=spec,
            stage_key="knowledge_base",
        )


def test_validate_stage_requirements_requires_foundational_prefix():
    bundle_payload = {"items": [{"role": "signal_report"}]}
    spec = {
        "required_role_prefixes": ("foundational:",),
    }

    with pytest.raises(
        EmberSkillsFlowError,
        match="Stage 'signal_report' requires at least one approved role with prefix 'foundational:'.",
    ):
        EmberSkillsFlowService._validate_stage_requirements(
            bundle_payload=bundle_payload,
            spec=spec,
            stage_key="signal_report",
        )


def test_validate_stage_requirements_accepts_complete_bundle():
    bundle_payload = {
        "items": [
            {"role": "foundational:v2-02.foundation.01"},
            {"role": "signal_report"},
            {"role": "angle_selection"},
            {"role": "knowledge_base"},
        ]
    }
    spec = {
        "required_roles": ("signal_report", "angle_selection"),
        "required_role_prefixes": ("foundational:",),
    }

    EmberSkillsFlowService._validate_stage_requirements(
        bundle_payload=bundle_payload,
        spec=spec,
        stage_key="knowledge_base",
    )


def test_validate_stage_requirements_blocks_missing_required_foundational_doc_keys():
    bundle_payload = {
        "items": [
            {"role": "foundational:v2-02.foundation.01"},
            {"role": "signal_report"},
        ],
        "metadata": {
            "missingFoundationalDocKeys": ["v2-02.foundation.02"],
        },
    }
    spec = {
        "required_roles": ("signal_report",),
        "required_foundational_doc_keys": ("v2-02.foundation.02",),
    }

    with pytest.raises(
        EmberSkillsFlowError,
        match="Stage 'signal_report' is blocked by missing foundational source items: v2-02.foundation.02.",
    ):
        EmberSkillsFlowService._validate_stage_requirements(
            bundle_payload=bundle_payload,
            spec=spec,
            stage_key="signal_report",
        )


def test_run_stage_rejects_automatic_promotion():
    service = EmberSkillsFlowService(
        session=None,  # type: ignore[arg-type]
        org_id="org-1",
        client_id="client-1",
        product_id="product-1",
        created_by_user=None,
    )

    with pytest.raises(
        EmberSkillsFlowError,
        match="Automatic promotion is disabled for EMBER skills stages.",
    ):
        service.run_stage(stage_key="signal_report", promote_to_active_bundle=True)


def test_import_foundational_bundle_records_missing_required_docs(db_session, tmp_path):
    client = Client(org_id=TEST_ORG_ID, name="Ember Client")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)

    product = Product(org_id=TEST_ORG_ID, client_id=client.id, title="Ember Product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    (tmp_path / "v2-02.foundation.01.md").write_text("# Research\n", encoding="utf-8")
    (tmp_path / "v2-02.foundation.03.md").write_text("# Offer\n", encoding="utf-8")

    service = ProductStrategyBundlesService(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        client_id=str(client.id),
        product_id=str(product.id),
        created_by_user=None,
    )
    bundle = service.import_foundational_bundle(
        source_dir=tmp_path,
        title="Foundational",
        required_doc_keys=("v2-02.foundation.01", "v2-02.foundation.02", "v2-02.foundation.03"),
    )

    assert bundle["bundleType"] == "foundational_docs"
    assert bundle["status"] == "incomplete"
    assert bundle["metadata"]["presentDocKeys"] == ["v2-02.foundation.01", "v2-02.foundation.03"]
    assert bundle["metadata"]["missingDocKeys"] == ["v2-02.foundation.02"]
    assert bundle["metadata"]["isComplete"] is False


def test_seed_working_bundle_requires_explicit_allow_incomplete(api_client, db_session, tmp_path):
    client_resp = api_client.post("/clients", json={"name": "Ember Client 2", "industry": "SaaS"})
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    product_resp = api_client.post(
        "/products",
        json={"clientId": client_id, "title": "Ember Product 2"},
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    (tmp_path / "v2-02.foundation.01.md").write_text("# Research\n", encoding="utf-8")

    bundle_service = ProductStrategyBundlesService(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        client_id=client_id,
        product_id=product_id,
        created_by_user=None,
    )
    bundle_service.import_foundational_bundle(
        source_dir=tmp_path,
        title="Foundational",
        required_doc_keys=("v2-02.foundation.01", "v2-02.foundation.02"),
    )

    flow = EmberSkillsFlowService(
        session=db_session,
        org_id=str(TEST_ORG_ID),
        client_id=client_id,
        product_id=product_id,
        created_by_user=None,
    )

    with pytest.raises(
        EmberSkillsFlowError,
        match="Foundational bundle is incomplete and cannot seed strategy bundles yet.",
    ):
        flow.seed_working_bundle_from_foundation()


def test_stage_thread_id_is_stable_for_same_export_hash():
    thread_id = EmberSkillsFlowService._stage_thread_id(
        stage_key="knowledge_base",
        runtime_profile_key="strategy",
        exported_bundle={"exportHash": "abc123def4567890feedbeef"},
    )

    assert thread_id == "strategy-stage-strategy-knowledge_base-abc123def4567890"
