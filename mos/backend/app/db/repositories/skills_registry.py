from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    RuntimeBundleExport,
    RuntimeProfile,
    SkillPackage,
    SkillPackageRelease,
    SkillPackageReleaseAsset,
    WorkspaceSkillBinding,
)


class SkillPackagesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_key(self, *, org_id: str, key: str) -> SkillPackage | None:
        stmt = select(SkillPackage).where(
            SkillPackage.org_id == org_id,
            SkillPackage.key == key,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        key: str,
        name: str,
        description: str | None,
        source_repo: str | None,
        source_root: str | None,
        metadata_json: dict | None = None,
    ) -> SkillPackage:
        skill_package = self.get_by_key(org_id=org_id, key=key)
        now = datetime.now(timezone.utc)
        if skill_package is None:
            skill_package = SkillPackage(
                org_id=org_id,
                key=key,
                name=name,
                description=description,
                source_repo=source_repo,
                source_root=source_root,
                metadata_json=metadata_json or {},
                created_at=now,
                updated_at=now,
            )
            self.session.add(skill_package)
            self.session.flush()
            self.session.refresh(skill_package)
            return skill_package

        skill_package.name = name
        skill_package.description = description
        skill_package.source_repo = source_repo
        skill_package.source_root = source_root
        skill_package.metadata_json = metadata_json or {}
        skill_package.updated_at = now
        self.session.add(skill_package)
        self.session.flush()
        self.session.refresh(skill_package)
        return skill_package


class SkillPackageReleasesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_version(
        self,
        *,
        skill_package_id: str,
        version: str,
    ) -> SkillPackageRelease | None:
        stmt = select(SkillPackageRelease).where(
            SkillPackageRelease.skill_package_id == skill_package_id,
            SkillPackageRelease.version == version,
        )
        return self.session.scalars(stmt).first()

    def latest_for_package(
        self,
        *,
        org_id: str,
        skill_package_id: str,
        status: str | None = None,
    ) -> SkillPackageRelease | None:
        stmt = (
            select(SkillPackageRelease)
            .where(
                SkillPackageRelease.org_id == org_id,
                SkillPackageRelease.skill_package_id == skill_package_id,
            )
            .order_by(desc(SkillPackageRelease.created_at))
        )
        if status:
            stmt = stmt.where(SkillPackageRelease.status == status)
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        skill_package_id: str,
        version: str,
        status: str,
        manifest_json: dict,
        source_revision: str | None,
        source_ref: str | None,
        created_by_user: str | None,
    ) -> SkillPackageRelease:
        now = datetime.now(timezone.utc)
        release = SkillPackageRelease(
            org_id=org_id,
            skill_package_id=skill_package_id,
            version=version,
            status=status,
            manifest_json=manifest_json,
            source_revision=source_revision,
            source_ref=source_ref,
            created_by_user=created_by_user,
            created_at=now,
            updated_at=now,
        )
        self.session.add(release)
        self.session.flush()
        self.session.refresh(release)
        return release

    def list_assets(self, *, release_id: str) -> list[SkillPackageReleaseAsset]:
        stmt = (
            select(SkillPackageReleaseAsset)
            .where(SkillPackageReleaseAsset.skill_package_release_id == release_id)
            .order_by(SkillPackageReleaseAsset.relative_path.asc())
        )
        return list(self.session.scalars(stmt).all())

    def replace_assets(
        self,
        *,
        org_id: str,
        release_id: str,
        assets: list[dict],
    ) -> list[SkillPackageReleaseAsset]:
        self.session.query(SkillPackageReleaseAsset).filter(
            SkillPackageReleaseAsset.skill_package_release_id == release_id
        ).delete(synchronize_session=False)
        created: list[SkillPackageReleaseAsset] = []
        for item in assets:
            asset = SkillPackageReleaseAsset(
                org_id=org_id,
                skill_package_release_id=release_id,
                asset_kind=item["asset_kind"],
                role=item.get("role"),
                relative_path=item["relative_path"],
                sha256=item["sha256"],
                content=item["content"],
                metadata_json=item.get("metadata_json") or {},
            )
            self.session.add(asset)
            created.append(asset)
        self.session.flush()
        return created


class RuntimeProfilesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self,
        *,
        release_id: str,
        key: str,
    ) -> RuntimeProfile | None:
        stmt = select(RuntimeProfile).where(
            RuntimeProfile.skill_package_release_id == release_id,
            RuntimeProfile.key == key,
        )
        return self.session.scalars(stmt).first()

    def list_for_release(self, *, release_id: str) -> list[RuntimeProfile]:
        stmt = (
            select(RuntimeProfile)
            .where(RuntimeProfile.skill_package_release_id == release_id)
            .order_by(RuntimeProfile.key.asc())
        )
        return list(self.session.scalars(stmt).all())

    def replace_for_release(
        self,
        *,
        org_id: str,
        release_id: str,
        profiles: list[dict],
    ) -> list[RuntimeProfile]:
        self.session.query(RuntimeProfile).filter(
            RuntimeProfile.skill_package_release_id == release_id
        ).delete(synchronize_session=False)
        now = datetime.now(timezone.utc)
        created: list[RuntimeProfile] = []
        for item in profiles:
            profile = RuntimeProfile(
                org_id=org_id,
                skill_package_release_id=release_id,
                key=item["key"],
                name=item["name"],
                description=item.get("description"),
                profile_json=item.get("profile_json") or {},
                created_at=now,
                updated_at=now,
            )
            self.session.add(profile)
            created.append(profile)
        self.session.flush()
        return created


class WorkspaceSkillBindingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_key: str,
    ) -> WorkspaceSkillBinding | None:
        stmt = select(WorkspaceSkillBinding).where(
            WorkspaceSkillBinding.org_id == org_id,
            WorkspaceSkillBinding.client_id == client_id,
            WorkspaceSkillBinding.product_id == product_id,
            WorkspaceSkillBinding.bundle_key == bundle_key,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        skill_package_release_id: str,
        bundle_key: str,
        bundle_family: str,
        status: str,
        metadata_json: dict | None = None,
    ) -> WorkspaceSkillBinding:
        binding = self.get(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            bundle_key=bundle_key,
        )
        now = datetime.now(timezone.utc)
        if binding is None:
            binding = WorkspaceSkillBinding(
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                skill_package_release_id=skill_package_release_id,
                bundle_key=bundle_key,
                bundle_family=bundle_family,
                status=status,
                metadata_json=metadata_json or {},
                created_at=now,
                updated_at=now,
            )
            self.session.add(binding)
            self.session.flush()
            self.session.refresh(binding)
            return binding

        binding.skill_package_release_id = skill_package_release_id
        binding.bundle_family = bundle_family
        binding.status = status
        binding.metadata_json = metadata_json or {}
        binding.updated_at = now
        self.session.add(binding)
        self.session.flush()
        self.session.refresh(binding)
        return binding


class RuntimeBundleExportsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_for_scope(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        bundle_key: str,
        runtime_profile_key: str,
        strategy_bundle_id: str | None,
    ) -> RuntimeBundleExport | None:
        stmt = (
            select(RuntimeBundleExport)
            .where(
                RuntimeBundleExport.org_id == org_id,
                RuntimeBundleExport.client_id == client_id,
                RuntimeBundleExport.product_id == product_id,
                RuntimeBundleExport.bundle_key == bundle_key,
                RuntimeBundleExport.runtime_profile_key == runtime_profile_key,
            )
            .order_by(desc(RuntimeBundleExport.created_at))
        )
        if strategy_bundle_id:
            stmt = stmt.where(RuntimeBundleExport.project_doc_bundle_id == strategy_bundle_id)
        else:
            stmt = stmt.where(RuntimeBundleExport.project_doc_bundle_id.is_(None))
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        product_id: str,
        workspace_skill_binding_id: str,
        project_doc_bundle_id: str | None,
        bundle_key: str,
        runtime_profile_key: str,
        export_root: str,
        export_hash: str,
        status: str,
        manifest_json: dict,
    ) -> RuntimeBundleExport:
        now = datetime.now(timezone.utc)
        export = RuntimeBundleExport(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            workspace_skill_binding_id=workspace_skill_binding_id,
            project_doc_bundle_id=project_doc_bundle_id,
            bundle_key=bundle_key,
            runtime_profile_key=runtime_profile_key,
            export_root=export_root,
            export_hash=export_hash,
            status=status,
            manifest_json=manifest_json,
            created_at=now,
            updated_at=now,
        )
        self.session.add(export)
        self.session.flush()
        self.session.refresh(export)
        return export

    def update(self, *, export: RuntimeBundleExport) -> RuntimeBundleExport:
        export.updated_at = datetime.now(timezone.utc)
        self.session.add(export)
        self.session.flush()
        self.session.refresh(export)
        return export
