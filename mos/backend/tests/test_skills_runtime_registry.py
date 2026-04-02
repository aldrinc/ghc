from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.skills_runtime_registry import SkillsRuntimeRegistryService


def _service() -> SkillsRuntimeRegistryService:
    return SkillsRuntimeRegistryService(
        session=MagicMock(),
        org_id="org-1",
        client_id="client-1",
        product_id="product-1",
        created_by_user=None,
    )


def test_export_identity_hash_is_stable_for_same_inputs():
    service = _service()
    release = SimpleNamespace(id="release-1", version="2026-04-01")
    runtime_profile = {"skillChain": ["strategy"], "runtimeRules": ["rule-1"]}
    release_assets = [
        SimpleNamespace(
            relative_path="methodology/EMBER.md",
            sha256="asset-sha",
            role="ember_workflow",
            asset_kind="methodology",
        )
    ]
    strategy_documents = [
        {"role": "signal_report", "extension": ".md", "content": "# Signal Report\n\nBody"}
    ]

    first = service._export_identity_hash(
        bundle_key="ember_skills_v1",
        runtime_profile_key="strategy",
        release=release,
        runtime_profile=runtime_profile,
        release_assets=release_assets,
        strategy_documents=strategy_documents,
        strategy_bundle_id="bundle-1",
    )
    second = service._export_identity_hash(
        bundle_key="ember_skills_v1",
        runtime_profile_key="strategy",
        release=release,
        runtime_profile=runtime_profile,
        release_assets=release_assets,
        strategy_documents=strategy_documents,
        strategy_bundle_id="bundle-1",
    )

    assert first == second


def test_export_identity_hash_changes_when_strategy_documents_change():
    service = _service()
    release = SimpleNamespace(id="release-1", version="2026-04-01")
    runtime_profile = {"skillChain": ["strategy"], "runtimeRules": ["rule-1"]}
    release_assets = [
        SimpleNamespace(
            relative_path="methodology/EMBER.md",
            sha256="asset-sha",
            role="ember_workflow",
            asset_kind="methodology",
        )
    ]

    first = service._export_identity_hash(
        bundle_key="ember_skills_v1",
        runtime_profile_key="strategy",
        release=release,
        runtime_profile=runtime_profile,
        release_assets=release_assets,
        strategy_documents=[{"role": "signal_report", "extension": ".md", "content": "# One"}],
        strategy_bundle_id="bundle-1",
    )
    second = service._export_identity_hash(
        bundle_key="ember_skills_v1",
        runtime_profile_key="strategy",
        release=release,
        runtime_profile=runtime_profile,
        release_assets=release_assets,
        strategy_documents=[{"role": "signal_report", "extension": ".md", "content": "# Two"}],
        strategy_bundle_id="bundle-1",
    )

    assert first != second


def test_manifest_paths_are_ready_requires_referenced_files(tmp_path):
    export_root = tmp_path / "export"
    skill_root = export_root / "system" / "skills" / "skill-a"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Skill A", encoding="utf-8")

    doc_path = export_root / "strategy" / "signal_report.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text("# Signal Report", encoding="utf-8")

    manifest = {
        "files": {"signal_report": str(doc_path)},
        "supportingDocs": {},
        "skills": [{"name": "skill-a", "path": str(skill_root), "role": "Test skill"}],
        "availableSkills": [{"name": "skill-a", "path": str(skill_root), "role": "Test skill"}],
    }

    assert SkillsRuntimeRegistryService._manifest_paths_are_ready(manifest=manifest) is True

    doc_path.unlink()

    assert SkillsRuntimeRegistryService._manifest_paths_are_ready(manifest=manifest) is False
