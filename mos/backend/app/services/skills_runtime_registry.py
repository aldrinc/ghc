from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.project_doc_bundles import ProjectDocBundlesRepository
from app.db.repositories.skills_registry import (
    RuntimeBundleExportsRepository,
    RuntimeProfilesRepository,
    SkillPackageReleasesRepository,
    SkillPackagesRepository,
    WorkspaceSkillBindingsRepository,
)
from app.db.models import SkillPackageRelease
from app.services.product_strategy_bundles import ProductStrategyBundlesError, ProductStrategyBundlesService


class SkillsRuntimeRegistryError(ValueError):
    """Raised when the skills registry or runtime export is invalid."""


DEFAULT_SKILL_PACKAGE_KEY = "mos_strategy_v3_ember"
DEFAULT_SKILL_PACKAGE_NAME = "MOS Strategy V3 EMBER Runtime"
DEFAULT_SKILL_BUNDLE_KEY = "ember_skills_v1"
DEFAULT_SKILL_BUNDLE_FAMILY = "ember"


class SkillsRuntimeRegistryService:
    def __init__(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        product_id: str,
        created_by_user: str | None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.client_id = client_id
        self.product_id = product_id
        self.created_by_user = self._maybe_uuid(created_by_user)
        self.repo_root = Path(__file__).resolve().parents[3]
        self.programming_root = self.repo_root.parent
        self.exports_root = self.repo_root / ".local" / "hermes" / "exports"
        self.artifacts_repo = ArtifactsRepository(session)
        self.bundles_repo = ProjectDocBundlesRepository(session)
        self.skill_packages_repo = SkillPackagesRepository(session)
        self.skill_releases_repo = SkillPackageReleasesRepository(session)
        self.runtime_profiles_repo = RuntimeProfilesRepository(session)
        self.workspace_bindings_repo = WorkspaceSkillBindingsRepository(session)
        self.runtime_exports_repo = RuntimeBundleExportsRepository(session)

    def sync_ember_skills_release(
        self,
        *,
        strategy_root: Path,
        version: str,
        source_revision: str | None = None,
        source_ref: str | None = None,
    ) -> dict[str, Any]:
        strategy_root = strategy_root.expanduser().resolve()
        if not strategy_root.exists():
            raise SkillsRuntimeRegistryError(f"Strategy root does not exist: {strategy_root}")

        package = self.skill_packages_repo.upsert(
            org_id=self.org_id,
            key=DEFAULT_SKILL_PACKAGE_KEY,
            name=DEFAULT_SKILL_PACKAGE_NAME,
            description="MOS-owned copy of the EMBER skills repo and methodology assets for Hermes runtime.",
            source_repo="mos_strategy_v3",
            source_root=str(strategy_root),
            metadata_json={
                "strategyRoot": str(strategy_root),
            },
        )
        release = self.skill_releases_repo.get_by_version(
            skill_package_id=str(package.id),
            version=version,
        )
        if release is None:
            release = self.skill_releases_repo.create(
                org_id=self.org_id,
                skill_package_id=str(package.id),
                version=version,
                status="active",
                manifest_json={},
                source_revision=source_revision,
                source_ref=source_ref,
                created_by_user=self.created_by_user,
            )

        assets = self._collect_release_assets(strategy_root=strategy_root)
        self.skill_releases_repo.replace_assets(
            org_id=self.org_id,
            release_id=str(release.id),
            assets=assets,
        )
        runtime_profiles = self._default_runtime_profiles()
        self.runtime_profiles_repo.replace_for_release(
            org_id=self.org_id,
            release_id=str(release.id),
            profiles=runtime_profiles,
        )
        release.manifest_json = {
            "assetCount": len(assets),
            "runtimeProfiles": [profile["key"] for profile in runtime_profiles],
            "sourceRevision": source_revision,
            "sourceRef": source_ref,
        }
        self.session.add(release)
        self.session.flush()
        self.session.refresh(release)
        self.session.commit()
        return {
            "packageId": str(package.id),
            "releaseId": str(release.id),
            "version": release.version,
            "assetCount": len(assets),
            "runtimeProfiles": [profile["key"] for profile in runtime_profiles],
        }

    def ensure_workspace_binding(
        self,
        *,
        release_id: str,
        bundle_key: str = DEFAULT_SKILL_BUNDLE_KEY,
        bundle_family: str = DEFAULT_SKILL_BUNDLE_FAMILY,
    ) -> dict[str, Any]:
        release = self._require_release(release_id=release_id)
        binding = self.workspace_bindings_repo.upsert(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            skill_package_release_id=str(release.id),
            bundle_key=bundle_key,
            bundle_family=bundle_family,
            status="active",
            metadata_json={
                "skillPackageId": str(release.skill_package_id),
                "releaseVersion": release.version,
            },
        )
        self.session.commit()
        return {
            "id": str(binding.id),
            "bundleKey": binding.bundle_key,
            "bundleFamily": binding.bundle_family,
            "releaseId": str(binding.skill_package_release_id),
            "status": binding.status,
        }

    def get_workspace_binding(
        self,
        *,
        bundle_key: str = DEFAULT_SKILL_BUNDLE_KEY,
    ) -> dict[str, Any] | None:
        binding = self.workspace_bindings_repo.get(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_key=bundle_key,
        )
        if binding is None:
            return None
        return {
            "id": str(binding.id),
            "bundleKey": binding.bundle_key,
            "bundleFamily": binding.bundle_family,
            "releaseId": str(binding.skill_package_release_id),
            "status": binding.status,
            "metadata": binding.metadata_json or {},
        }

    def export_runtime_bundle(
        self,
        *,
        bundle_key: str,
        runtime_profile_key: str,
        project_doc_bundle_id: str | None,
    ) -> dict[str, Any]:
        binding = self.workspace_bindings_repo.get(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_key=bundle_key,
        )
        if binding is None:
            raise SkillsRuntimeRegistryError(
                f"No workspace skill binding exists for bundle key '{bundle_key}'."
            )
        release = self._require_release(release_id=str(binding.skill_package_release_id))
        runtime_profile = self.runtime_profiles_repo.get(
            release_id=str(release.id),
            key=runtime_profile_key,
        )
        if runtime_profile is None:
            raise SkillsRuntimeRegistryError(
                f"Runtime profile '{runtime_profile_key}' is not installed on release {release.version}."
            )

        release_assets = self.skill_releases_repo.list_assets(release_id=str(release.id))
        if not release_assets:
            raise SkillsRuntimeRegistryError(f"Release {release.version} has no imported assets.")

        bundle = None
        bundle_items: list[dict[str, Any]] = []
        if project_doc_bundle_id:
            bundle = self.bundles_repo.get(bundle_id=project_doc_bundle_id, org_id=self.org_id)
            if bundle is None:
                raise SkillsRuntimeRegistryError(
                    f"Product strategy bundle not found: {project_doc_bundle_id}"
                )
            bundle_items = self._serialize_bundle_items(bundle_id=project_doc_bundle_id)

        strategy_documents = self._strategy_documents(bundle_items=bundle_items)
        export_hash = self._export_identity_hash(
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            release=release,
            runtime_profile=runtime_profile.profile_json or {},
            release_assets=release_assets,
            strategy_documents=strategy_documents,
            strategy_bundle_id=str(bundle.id) if bundle is not None else None,
        )
        cached_export = self.runtime_exports_repo.latest_for_scope(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            strategy_bundle_id=project_doc_bundle_id,
        )
        if cached_export is not None and cached_export.export_hash == export_hash:
            cached_payload = self._cached_export_payload(export=cached_export)
            if cached_payload is not None:
                return cached_payload

        export_root = self.exports_root / export_hash
        ready_manifest = self._wait_for_export_manifest(export_root=export_root)
        if ready_manifest is not None:
            export = self._upsert_runtime_export_record(
                cached_export=cached_export,
                binding_id=str(binding.id),
                project_doc_bundle_id=project_doc_bundle_id,
                bundle_key=bundle_key,
                runtime_profile_key=runtime_profile_key,
                export_root=export_root,
                export_hash=export_hash,
                manifest=ready_manifest,
            )
            self.session.commit()
            return self._runtime_export_payload(export=export, manifest=ready_manifest)

        if export_root.exists():
            shutil.rmtree(export_root, ignore_errors=True)

        staging_root = self.exports_root / f"{export_hash}.tmp-{uuid4().hex}"
        if staging_root.exists():
            shutil.rmtree(staging_root)
        (staging_root / "system").mkdir(parents=True, exist_ok=True)
        (staging_root / "strategy").mkdir(parents=True, exist_ok=True)

        for asset in release_assets:
            target = staging_root / "system" / asset.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(asset.content, encoding="utf-8")

        strategy_files: dict[str, str] = {}
        for document in strategy_documents:
            target = staging_root / "strategy" / f"{document['role']}{document['extension']}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(document["content"], encoding="utf-8")
            strategy_files[document["role"]] = str(
                export_root / "strategy" / f"{document['role']}{document['extension']}"
            )

        available_skills = self._available_skills_manifest(
            export_root=staging_root,
            path_root=export_root,
        )
        skill_chain = self._resolve_skill_chain(
            export_root=staging_root,
            available_skills=available_skills,
            runtime_profile=runtime_profile.profile_json or {},
        )
        supporting_docs = self._supporting_docs_manifest(
            export_root=export_root,
            runtime_profile=runtime_profile.profile_json or {},
            release_assets=release_assets,
        )
        manifest = {
            "bundleKey": bundle_key,
            "bundleFamily": binding.bundle_family,
            "runtimeProfileKey": runtime_profile_key,
            "files": strategy_files,
            "skills": skill_chain,
            "availableSkills": available_skills,
            "supportingDocs": supporting_docs,
            "runtimeRules": (runtime_profile.profile_json or {}).get("runtimeRules") or [],
            "strategyBundleId": str(bundle.id) if bundle is not None else None,
            "releaseId": str(release.id),
            "releaseVersion": release.version,
            "exportHash": export_hash,
        }
        manifest_path = staging_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        try:
            staging_root.rename(export_root)
        except FileExistsError:
            shutil.rmtree(staging_root, ignore_errors=True)
            ready_manifest = self._wait_for_export_manifest(export_root=export_root)
            if ready_manifest is None:
                raise SkillsRuntimeRegistryError(
                    f"Runtime export {export_hash} already exists but its manifest is not ready."
                )
            export = self._upsert_runtime_export_record(
                cached_export=cached_export,
                binding_id=str(binding.id),
                project_doc_bundle_id=project_doc_bundle_id,
                bundle_key=bundle_key,
                runtime_profile_key=runtime_profile_key,
                export_root=export_root,
                export_hash=export_hash,
                manifest=ready_manifest,
            )
            self.session.commit()
            return self._runtime_export_payload(export=export, manifest=ready_manifest)

        export = self._upsert_runtime_export_record(
            cached_export=cached_export,
            binding_id=str(binding.id),
            project_doc_bundle_id=project_doc_bundle_id,
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            export_root=export_root,
            export_hash=export_hash,
            manifest=manifest,
        )
        self.session.commit()
        return self._runtime_export_payload(export=export, manifest=manifest)

    @staticmethod
    def _strategy_documents(*, bundle_items: list[dict[str, Any]]) -> list[dict[str, str]]:
        documents: list[dict[str, str]] = []
        for item in bundle_items:
            extension, content = ProductStrategyBundlesService.artifact_document_text(
                artifact_data=item["artifactData"]
            )
            documents.append(
                {
                    "role": item["role"],
                    "extension": extension,
                    "content": content,
                }
            )
        documents.sort(key=lambda document: document["role"])
        return documents

    def _export_identity_hash(
        self,
        *,
        bundle_key: str,
        runtime_profile_key: str,
        release: SkillPackageRelease,
        runtime_profile: dict[str, Any],
        release_assets: list[Any],
        strategy_documents: list[dict[str, str]],
        strategy_bundle_id: str | None,
    ) -> str:
        payload = {
            "orgId": self.org_id,
            "clientId": self.client_id,
            "productId": self.product_id,
            "bundleKey": bundle_key,
            "runtimeProfileKey": runtime_profile_key,
            "releaseId": str(release.id),
            "releaseVersion": release.version,
            "strategyBundleId": strategy_bundle_id,
            "runtimeProfile": runtime_profile,
            "releaseAssets": [
                {
                    "relativePath": asset.relative_path,
                    "sha256": asset.sha256,
                    "role": asset.role,
                    "assetKind": asset.asset_kind,
                }
                for asset in release_assets
            ],
            "strategyDocuments": strategy_documents,
        }
        return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _cached_export_payload(self, *, export) -> dict[str, Any] | None:
        export_root = Path(export.export_root)
        manifest = self._wait_for_export_manifest(export_root=export_root, timeout_seconds=0.1)
        if manifest is None:
            return None
        return self._runtime_export_payload(export=export, manifest=manifest)

    def _upsert_runtime_export_record(
        self,
        *,
        cached_export,
        binding_id: str,
        project_doc_bundle_id: str | None,
        bundle_key: str,
        runtime_profile_key: str,
        export_root: Path,
        export_hash: str,
        manifest: dict[str, Any],
    ):
        if cached_export is not None and cached_export.export_hash == export_hash:
            cached_export.workspace_skill_binding_id = UUID(binding_id)
            cached_export.project_doc_bundle_id = (
                UUID(project_doc_bundle_id) if project_doc_bundle_id else None
            )
            cached_export.export_root = str(export_root)
            cached_export.status = "ready"
            cached_export.manifest_json = manifest
            return self.runtime_exports_repo.update(export=cached_export)
        return self.runtime_exports_repo.create(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            workspace_skill_binding_id=binding_id,
            project_doc_bundle_id=project_doc_bundle_id,
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            export_root=str(export_root),
            export_hash=export_hash,
            status="ready",
            manifest_json=manifest,
        )

    @staticmethod
    def _runtime_export_payload(*, export, manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(export.id),
            "bundleKey": export.bundle_key,
            "runtimeProfileKey": export.runtime_profile_key,
            "exportRoot": export.export_root,
            "exportHash": export.export_hash,
            "manifest": manifest,
        }

    @staticmethod
    def _wait_for_export_manifest(
        *,
        export_root: Path,
        timeout_seconds: float = 5.0,
    ) -> dict[str, Any] | None:
        manifest_path = export_root / "manifest.json"
        deadline = time.time() + timeout_seconds
        while time.time() <= deadline:
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    manifest = None
                if isinstance(manifest, dict) and SkillsRuntimeRegistryService._manifest_paths_are_ready(
                    manifest=manifest
                ):
                    return manifest
            if not export_root.exists():
                return None
            time.sleep(0.1)
        return None

    @staticmethod
    def _manifest_paths_are_ready(*, manifest: dict[str, Any]) -> bool:
        file_paths = list((manifest.get("files") or {}).values())
        file_paths.extend((manifest.get("supportingDocs") or {}).values())
        for path_str in file_paths:
            if not Path(path_str).is_file():
                return False

        for collection_key in ("skills", "availableSkills"):
            for entry in manifest.get(collection_key) or []:
                skill_path = Path(str(entry.get("path") or ""))
                if not skill_path.is_dir():
                    return False
                if not (skill_path / "SKILL.md").is_file():
                    return False

        return True

    def _require_release(self, *, release_id: str):
        release = self.session.get(SkillPackageRelease, release_id)
        if release is None:
            raise SkillsRuntimeRegistryError(f"Skill package release not found: {release_id}")
        return release

    def _collect_release_assets(self, *, strategy_root: Path) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for relative_path in self._iter_files(strategy_root / "skills"):
            source = strategy_root / "skills" / relative_path
            content = source.read_text(encoding="utf-8")
            assets.append(
                self._asset_record(
                    source=source,
                    relative_path=Path("skills") / relative_path,
                    content=content,
                    asset_kind="skill",
                    role=None,
                )
            )

        file_specs = (
            (
                strategy_root / "CLAUDE.md",
                Path("methodology") / "CLAUDE.md",
                "supporting_doc",
                "v3_claude",
            ),
            (
                strategy_root / "ONBOARDING.md",
                Path("methodology") / "ONBOARDING.md",
                "supporting_doc",
                "v3_onboarding",
            ),
            (
                strategy_root / "AGENTS.md",
                Path("methodology") / "AGENTS.md",
                "supporting_doc",
                "v3_agents",
            ),
            (
                strategy_root / "settings.json",
                Path("methodology") / "settings.json",
                "supporting_doc",
                "v3_settings",
            ),
            (
                strategy_root / "commands" / "offer-engine" / "SKILL.md",
                Path("methodology") / "offer-engine" / "SKILL.md",
                "supporting_doc",
                "v3_offer_engine_command",
            ),
            (
                strategy_root / "FutrGroup-Hookd-Project" / "EMBER" / "claude-projects" / "WORKFLOW.md",
                Path("methodology") / "ember" / "WORKFLOW.md",
                "methodology",
                "ember_workflow",
            ),
            (
                strategy_root / "FutrGroup-Hookd-Project" / "EMBER" / "claude-projects" / "CHAT-PROMPTS.md",
                Path("methodology") / "ember" / "CHAT-PROMPTS.md",
                "methodology",
                "ember_chat_prompts",
            ),
        )
        for source, relative_path, asset_kind, role in file_specs:
            if not source.exists():
                raise SkillsRuntimeRegistryError(f"Expected source file is missing: {source}")
            assets.append(
                self._asset_record(
                    source=source,
                    relative_path=relative_path,
                    content=source.read_text(encoding="utf-8"),
                    asset_kind=asset_kind,
                    role=role,
                )
            )

        dir_specs = (
            (
                strategy_root / "memory",
                Path("methodology") / "memory",
                "supporting_doc",
                "v3_memory",
            ),
            (
                strategy_root / "FutrGroup-Hookd-Project" / "06-memory",
                Path("methodology") / "hookd-memory",
                "supporting_doc",
                "v3_hookd_memory",
            ),
        )
        for source_dir, target_prefix, asset_kind, role in dir_specs:
            if not source_dir.exists():
                continue
            for relative_path in self._iter_files(source_dir):
                source = source_dir / relative_path
                assets.append(
                    self._asset_record(
                        source=source,
                        relative_path=target_prefix / relative_path,
                        content=source.read_text(encoding="utf-8"),
                        asset_kind=asset_kind,
                        role=role,
                    )
                )
        return assets

    @staticmethod
    def _default_runtime_profiles() -> list[dict[str, Any]]:
        return [
            {
                "key": "strategy",
                "name": "Strategy",
                "description": "Generate product-scoped strategy artifacts from foundational inputs only.",
                "profile_json": {
                    "skillChain": [
                        {"name": "FutrGroup_pipeline-orchestrator", "role": "Workflow sequencing"},
                        {"name": "FutrGroup_signal-hunter", "role": "VOC and language synthesis"},
                        {"name": "FutrGroup_opportunity-engine", "role": "Angle and CSO strategy"},
                        {"name": "FutrGroup_offer-architect", "role": "Offer construction"},
                        {"name": "FutrGroup_halbert-headlines", "role": "Headline generation"},
                        {"name": "FutrGroup_copy-forge", "role": "Copy drafting"},
                        {"name": "FutrGroup_frankie-pages", "role": "Long-form page assembly"},
                    ],
                    "supportingDocRoles": [
                        "v3_claude",
                        "v3_onboarding",
                        "v3_agents",
                        "v3_settings",
                        "v3_offer_engine_command",
                        "ember_workflow",
                        "ember_chat_prompts",
                        "v3_memory",
                        "v3_hookd_memory",
                    ],
                    "runtimeRules": [
                        "Treat foundational docs and generated strategy artifacts as the only business inputs.",
                        "Do not use historical EMBER offer, headline, or page outputs as source material.",
                        "If a required strategy artifact is missing, stop with a clear missing-role error.",
                    ],
                },
            },
            {
                "key": "offer",
                "name": "Offer",
                "description": "Focused offer and headline generation against approved strategy inputs.",
                "profile_json": {
                    "skillChain": [
                        {"name": "FutrGroup_pipeline-orchestrator", "role": "Workflow sequencing"},
                        {"name": "FutrGroup_offer-architect", "role": "Offer construction"},
                        {"name": "FutrGroup_halbert-headlines", "role": "Headline generation"},
                    ],
                    "supportingDocRoles": [
                        "v3_claude",
                        "v3_onboarding",
                        "ember_workflow",
                        "ember_chat_prompts",
                    ],
                    "runtimeRules": [
                        "Generate offer and headline outputs from the active approved strategy bundle only.",
                        "Do not silently fill missing approval gates.",
                    ],
                },
            },
            {
                "key": "copy",
                "name": "Copy",
                "description": "Long-form copy drafting against approved strategy inputs.",
                "profile_json": {
                    "skillChain": [
                        {"name": "FutrGroup_pipeline-orchestrator", "role": "Workflow sequencing"},
                        {"name": "FutrGroup_copy-forge", "role": "Copy drafting"},
                        {"name": "FutrGroup_frankie-pages", "role": "Long-form page assembly"},
                    ],
                    "supportingDocRoles": [
                        "v3_claude",
                        "v3_onboarding",
                        "ember_workflow",
                        "ember_chat_prompts",
                    ],
                    "runtimeRules": [
                        "Use only approved strategy artifacts and current page context as inputs.",
                        "Do not invent missing claims, prices, testimonials, or guarantees.",
                    ],
                },
            },
            {
                "key": "page-copy",
                "name": "Page Copy",
                "description": "Template-bound page copy rewriting for existing site pages.",
                "profile_json": {
                    "skillChain": [
                        {"name": "FutrGroup_pipeline-orchestrator", "role": "Workflow sequencing"},
                        {"name": "FutrGroup_copy-forge", "role": "Copy drafting"},
                        {"name": "FutrGroup_frankie-pages", "role": "Long-form page assembly"},
                        {"name": "FutrGroup_halbert-headlines", "role": "Headline refinement"},
                    ],
                    "supportingDocRoles": [
                        "v3_claude",
                        "v3_onboarding",
                        "ember_workflow",
                        "ember_chat_prompts",
                    ],
                    "runtimeRules": [
                        "Use the approved strategy bundle and page binding as the source of truth.",
                        "Preserve the imported template structure and rewrite slots only.",
                        "Do not invent missing claims, prices, testimonials, or guarantees.",
                    ],
                },
            },
        ]

    @staticmethod
    def _asset_record(
        *,
        source: Path,
        relative_path: Path,
        content: str,
        asset_kind: str,
        role: str | None,
    ) -> dict[str, Any]:
        return {
            "asset_kind": asset_kind,
            "role": role,
            "relative_path": str(relative_path),
            "content": content,
            "sha256": sha256(content.encode("utf-8")).hexdigest(),
            "metadata_json": {
                "sourcePath": str(source),
            },
        }

    @staticmethod
    def _maybe_uuid(value: str | None) -> str | None:
        candidate = (value or "").strip()
        if not candidate:
            return None
        try:
            return str(UUID(candidate))
        except ValueError:
            return None

    @staticmethod
    def _iter_files(root: Path) -> list[Path]:
        if not root.exists():
            raise SkillsRuntimeRegistryError(f"Expected source directory is missing: {root}")
        return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

    def _serialize_bundle_items(self, *, bundle_id: str) -> list[dict[str, Any]]:
        items = self.bundles_repo.list_items(bundle_id=bundle_id)
        serialized: list[dict[str, Any]] = []
        for item in items:
            artifact = self.artifacts_repo.get(org_id=self.org_id, artifact_id=str(item.artifact_id))
            if artifact is None:
                raise ProductStrategyBundlesError(
                    f"Bundle {bundle_id} references missing artifact {item.artifact_id}."
                )
            serialized.append(
                {
                    "id": str(item.id),
                    "role": item.role,
                    "artifactId": str(artifact.id),
                    "artifactData": artifact.data,
                }
            )
        return serialized

    @staticmethod
    def _available_skills_manifest(
        *,
        export_root: Path,
        path_root: Path | None = None,
    ) -> list[dict[str, Any]]:
        skills_root = export_root / "system" / "skills"
        resolved_path_root = path_root or export_root
        manifests: list[dict[str, Any]] = []
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            if not (skill_dir / "SKILL.md").exists():
                continue
            manifests.append(
                {
                    "name": skill_dir.name,
                    "role": "Projected V3 skill",
                    "path": str(resolved_path_root / "system" / "skills" / skill_dir.name),
                }
            )
        if not manifests:
            raise SkillsRuntimeRegistryError("No skill directories were exported for the runtime release.")
        return manifests

    @staticmethod
    def _resolve_skill_chain(
        *,
        export_root: Path,
        available_skills: list[dict[str, Any]],
        runtime_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        available_paths = {skill["name"]: skill["path"] for skill in available_skills}
        skill_chain: list[dict[str, Any]] = []
        for item in runtime_profile.get("skillChain") or []:
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "").strip()
            if not name or not role:
                raise SkillsRuntimeRegistryError("Runtime profile skillChain entries must define name and role.")
            if name not in available_paths:
                raise SkillsRuntimeRegistryError(
                    f"Runtime profile references missing skill '{name}' in export {export_root}."
                )
            skill_chain.append(
                {
                    "name": name,
                    "role": role,
                    "path": available_paths[name],
                }
            )
        if not skill_chain:
            raise SkillsRuntimeRegistryError("Runtime profile skillChain is empty.")
        return skill_chain

    def _supporting_docs_manifest(
        self,
        *,
        export_root: Path,
        runtime_profile: dict[str, Any],
        release_assets: list[Any],
    ) -> dict[str, str]:
        supporting_doc_roles = set(runtime_profile.get("supportingDocRoles") or [])
        manifest: dict[str, str] = {}
        for asset in release_assets:
            if asset.asset_kind == "skill":
                continue
            if supporting_doc_roles and asset.role not in supporting_doc_roles:
                continue
            manifest_key = asset.role or asset.relative_path.replace("/", "_")
            manifest[manifest_key] = str(export_root / "system" / asset.relative_path)
        return manifest
