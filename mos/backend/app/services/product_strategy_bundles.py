from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.project_doc_bundles import ProjectDocBundlesRepository


class ProductStrategyBundlesError(ValueError):
    """Raised when a product-scoped strategy bundle request is invalid."""


FOUNDATIONAL_BUNDLE_TYPE = "foundational_docs"
SKILLS_WORKING_BUNDLE_TYPE = "skills_working"
SKILLS_HANDOFF_BUNDLE_TYPE = "skills_handoff"

# The current EMBER prod snapshot confirms this expected foundational set.
DEFAULT_EMBER_FOUNDATIONAL_DOC_KEYS: tuple[str, ...] = (
    "v2-02.foundation.01",
    "v2-02.foundation.02",
    "v2-02.foundation.03",
    "v2-02.foundation.04",
    "v2-02.foundation.06",
)


class ProductStrategyBundlesService:
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
        self.artifacts_repo = ArtifactsRepository(session)
        self.bundles_repo = ProjectDocBundlesRepository(session)

    def import_foundational_bundle(
        self,
        *,
        source_dir: Path,
        title: str,
        doc_key_prefix: str = "foundational",
        required_doc_keys: tuple[str, ...] | list[str] | None = DEFAULT_EMBER_FOUNDATIONAL_DOC_KEYS,
        strict_missing_required: bool = False,
    ) -> dict[str, Any]:
        source_root = source_dir.expanduser().resolve()
        if not source_root.exists() or not source_root.is_dir():
            raise ProductStrategyBundlesError(f"Foundational source directory does not exist: {source_root}")

        markdown_files = sorted(
            path
            for path in source_root.iterdir()
            if path.is_file() and path.suffix.lower() == ".md"
        )
        if not markdown_files:
            raise ProductStrategyBundlesError(f"No foundational files found under {source_root}.")

        required_keys = tuple(str(key).strip() for key in (required_doc_keys or ()) if str(key).strip())
        discovered_by_stem = {path.stem: path for path in markdown_files}
        missing_required_keys = [key for key in required_keys if key not in discovered_by_stem]
        if strict_missing_required and missing_required_keys:
            missing_text = ", ".join(missing_required_keys)
            raise ProductStrategyBundlesError(
                f"Foundational bundle is missing required source items: {missing_text}."
            )

        created_artifacts: list[tuple[str, str]] = []
        for index, path in enumerate(markdown_files):
            doc_key = f"{doc_key_prefix}:{path.stem}"
            markdown = path.read_text(encoding="utf-8").strip()
            if not markdown:
                raise ProductStrategyBundlesError(f"Foundational file is empty: {path}")
            artifact = self.create_document_artifact(
                artifact_type=ArtifactTypeEnum.skill_foundational_input,
                title=path.stem,
                role=doc_key,
                document_format="markdown",
                markdown=markdown,
                json_payload=None,
                metadata_json={
                    "sourcePath": str(path),
                    "sourceFilename": path.name,
                    "importedAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            created_artifacts.append((doc_key, str(artifact.id)))

        bundle = self.create_bundle(
            bundle_type=FOUNDATIONAL_BUNDLE_TYPE,
            title=title,
            status="approved" if not missing_required_keys else "incomplete",
            is_active=True,
            artifact_roles={role: artifact_id for role, artifact_id in created_artifacts},
            metadata_json={
                "sourceDir": str(source_root),
                "fileCount": len(created_artifacts),
                "expectedDocKeys": list(required_keys),
                "presentDocKeys": [path.stem for path in markdown_files],
                "missingDocKeys": missing_required_keys,
                "isComplete": not missing_required_keys,
            },
            approved_by_user=self.created_by_user if not missing_required_keys else None,
        )
        self.session.commit()
        return bundle

    def create_bundle(
        self,
        *,
        bundle_type: str,
        title: str,
        status: str,
        is_active: bool,
        artifact_roles: dict[str, str],
        metadata_json: dict[str, Any] | None = None,
        approved_by_user: str | None = None,
    ) -> dict[str, Any]:
        if not artifact_roles:
            raise ProductStrategyBundlesError("artifact_roles must contain at least one item.")

        if is_active:
            self.bundles_repo.deactivate_scope(
                org_id=self.org_id,
                client_id=self.client_id,
                product_id=self.product_id,
                bundle_type=bundle_type,
            )

        bundle = self.bundles_repo.create(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_type=bundle_type,
            title=title,
            status=status,
            is_active=is_active,
            metadata_json=metadata_json or {},
            created_by_user=self.created_by_user,
            approved_by_user=self._maybe_uuid(approved_by_user),
        )
        self.bundles_repo.replace_items(
            bundle_id=str(bundle.id),
            items=[
                {
                    "artifact_id": artifact_id,
                    "role": role,
                    "item_order": index,
                }
                for index, (role, artifact_id) in enumerate(artifact_roles.items())
            ],
        )
        self.session.flush()
        self.session.refresh(bundle)
        return self.serialize_bundle(bundle_id=str(bundle.id))

    def get_active_bundle(self, *, bundle_type: str) -> dict[str, Any]:
        bundle = self.bundles_repo.get_active(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_type=bundle_type,
        )
        if bundle is None:
            raise ProductStrategyBundlesError(
                f"No active product strategy bundle exists for bundle type '{bundle_type}'."
            )
        return self.serialize_bundle(bundle_id=str(bundle.id))

    def get_active_bundle_or_none(self, *, bundle_type: str) -> dict[str, Any] | None:
        bundle = self.bundles_repo.get_active(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_type=bundle_type,
        )
        if bundle is None:
            return None
        return self.serialize_bundle(bundle_id=str(bundle.id))

    def list_bundles(self, *, bundle_type: str | None = None) -> list[dict[str, Any]]:
        bundles = self.bundles_repo.list_for_scope(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_type=bundle_type,
        )
        return [self.serialize_bundle(bundle_id=str(bundle.id)) for bundle in bundles]

    def activate_bundle(self, *, bundle_id: str, bundle_type: str) -> dict[str, Any]:
        bundle = self.bundles_repo.get(bundle_id=bundle_id, org_id=self.org_id)
        if bundle is None:
            raise ProductStrategyBundlesError(f"Product strategy bundle not found: {bundle_id}")
        if str(bundle.client_id) != self.client_id or str(bundle.product_id) != self.product_id:
            raise ProductStrategyBundlesError(
                f"Product strategy bundle {bundle_id} does not belong to the current scope."
            )
        if bundle.bundle_type != bundle_type:
            raise ProductStrategyBundlesError(
                f"Bundle {bundle_id} is type '{bundle.bundle_type}', expected '{bundle_type}'."
            )
        self.bundles_repo.deactivate_scope(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            bundle_type=bundle_type,
        )
        bundle.is_active = True
        self.bundles_repo.update(bundle=bundle)
        self.session.commit()
        return self.serialize_bundle(bundle_id=bundle_id)

    def serialize_bundle(self, *, bundle_id: str) -> dict[str, Any]:
        bundle = self.bundles_repo.get(bundle_id=bundle_id, org_id=self.org_id)
        if bundle is None:
            raise ProductStrategyBundlesError(f"Product strategy bundle not found: {bundle_id}")
        items = self.bundles_repo.list_items(bundle_id=bundle_id)
        serialized_items: list[dict[str, Any]] = []
        for item in items:
            artifact = self.artifacts_repo.get(org_id=self.org_id, artifact_id=str(item.artifact_id))
            if artifact is None:
                raise ProductStrategyBundlesError(
                    f"Bundle {bundle_id} references missing artifact {item.artifact_id}."
                )
            serialized_items.append(
                {
                    "id": str(item.id),
                    "role": item.role,
                    "itemOrder": item.item_order,
                    "artifactId": str(artifact.id),
                    "artifactType": artifact.type.value,
                    "artifactData": artifact.data,
                    "createdAt": item.created_at.isoformat(),
                }
            )
        return {
            "id": str(bundle.id),
            "bundleType": bundle.bundle_type,
            "title": bundle.title,
            "status": bundle.status,
            "isActive": bundle.is_active,
            "metadata": bundle.metadata_json or {},
            "approvedByUser": str(bundle.approved_by_user) if bundle.approved_by_user else None,
            "approvedAt": bundle.approved_at.isoformat() if bundle.approved_at else None,
            "createdAt": bundle.created_at.isoformat(),
            "updatedAt": bundle.updated_at.isoformat(),
            "items": serialized_items,
        }

    def create_document_artifact(
        self,
        *,
        artifact_type: ArtifactTypeEnum,
        title: str,
        role: str,
        document_format: str,
        markdown: str | None,
        json_payload: dict[str, Any] | list[Any] | None,
        metadata_json: dict[str, Any] | None = None,
    ):
        normalized_format = document_format.strip().lower()
        if normalized_format not in {"markdown", "json", "text"}:
            raise ProductStrategyBundlesError(
                f"Unsupported document_format '{document_format}'."
            )
        data: dict[str, Any] = {
            "schemaVersion": 1,
            "title": title,
            "role": role,
            "documentFormat": normalized_format,
            "metadata": metadata_json or {},
        }
        if normalized_format == "markdown":
            content = (markdown or "").strip()
            if not content:
                raise ProductStrategyBundlesError(
                    f"Markdown artifact '{title}' for role '{role}' is empty."
                )
            data["markdown"] = content
        elif normalized_format == "text":
            content = (markdown or "").strip()
            if not content:
                raise ProductStrategyBundlesError(
                    f"Text artifact '{title}' for role '{role}' is empty."
                )
            data["text"] = content
        else:
            if json_payload is None:
                raise ProductStrategyBundlesError(
                    f"JSON artifact '{title}' for role '{role}' is missing a payload."
                )
            data["json"] = json_payload

        artifact = self.artifacts_repo.insert(
            org_id=self.org_id,
            client_id=self.client_id,
            product_id=self.product_id,
            artifact_type=artifact_type,
            data=data,
            created_by_user=self.created_by_user,
        )
        return artifact

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
    def artifact_document_text(*, artifact_data: dict[str, Any]) -> tuple[str, str]:
        document_format = str(artifact_data.get("documentFormat") or "").strip().lower()
        if document_format == "markdown":
            content = str(artifact_data.get("markdown") or "").strip()
            if not content:
                raise ProductStrategyBundlesError("Markdown artifact payload is empty.")
            return ".md", content + "\n"
        if document_format == "text":
            content = str(artifact_data.get("text") or "").strip()
            if not content:
                raise ProductStrategyBundlesError("Text artifact payload is empty.")
            return ".txt", content + "\n"
        if document_format == "json":
            if "json" not in artifact_data:
                raise ProductStrategyBundlesError("JSON artifact payload is missing.")
            return ".json", json.dumps(artifact_data["json"], indent=2, ensure_ascii=False) + "\n"
        raise ProductStrategyBundlesError(
            f"Unsupported artifact documentFormat '{artifact_data.get('documentFormat')}'."
        )
