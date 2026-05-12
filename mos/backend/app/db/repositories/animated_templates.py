from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnimatedTemplateArtifact,
    AnimatedTemplateManifest,
    AnimatedTemplateManifestEvent,
    AnimatedTemplateRun,
)


class AnimatedTemplatesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_manifest(self, *, org_id: str, manifest_id: str) -> AnimatedTemplateManifest | None:
        stmt = select(AnimatedTemplateManifest).where(
            AnimatedTemplateManifest.org_id == org_id,
            AnimatedTemplateManifest.id == manifest_id,
        )
        return self.session.scalars(stmt).first()

    def get_manifest_by_idempotency_key(
        self,
        *,
        org_id: str,
        idempotency_key: str,
    ) -> AnimatedTemplateManifest | None:
        stmt = select(AnimatedTemplateManifest).where(
            AnimatedTemplateManifest.org_id == org_id,
            AnimatedTemplateManifest.idempotency_key == idempotency_key,
        )
        return self.session.scalars(stmt).first()

    def list_manifests(
        self,
        *,
        org_id: str,
        campaign_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AnimatedTemplateManifest]:
        stmt = select(AnimatedTemplateManifest).where(AnimatedTemplateManifest.org_id == org_id)
        if campaign_id:
            stmt = stmt.where(AnimatedTemplateManifest.campaign_id == campaign_id)
        if status:
            stmt = stmt.where(AnimatedTemplateManifest.status == status)
        stmt = stmt.order_by(AnimatedTemplateManifest.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def create_manifest(self, **fields: Any) -> AnimatedTemplateManifest:
        manifest = AnimatedTemplateManifest(**fields)
        self.session.add(manifest)
        self.session.flush()
        return manifest

    def approve_manifest(
        self,
        *,
        manifest: AnimatedTemplateManifest,
        actor_user_id: str,
        validation: dict[str, Any],
        approval_notes: str | None = None,
    ) -> AnimatedTemplateManifest:
        manifest.status = "approved"
        manifest.validation = validation
        manifest.approved_by_user_id = actor_user_id
        manifest.approved_at = datetime.now(timezone.utc)
        manifest.rejected_by_user_id = None
        manifest.rejected_at = None
        manifest.rejection_reason = None
        manifest.updated_at = datetime.now(timezone.utc)
        if manifest.supersedes_manifest_id:
            superseded = self.get_manifest(
                org_id=str(manifest.org_id),
                manifest_id=str(manifest.supersedes_manifest_id),
            )
            if superseded is not None and superseded.status == "approved":
                superseded.status = "superseded"
                superseded.updated_at = datetime.now(timezone.utc)
                self.create_event(
                    org_id=str(superseded.org_id),
                    manifest_id=str(superseded.id),
                    event_type="manifest.superseded",
                    actor_user_id=actor_user_id,
                    payload={"supersededByManifestId": str(manifest.id)},
                )
        self.create_event(
            org_id=str(manifest.org_id),
            manifest_id=str(manifest.id),
            event_type="manifest.approved",
            actor_user_id=actor_user_id,
            payload={"approvalNotes": approval_notes, "validation": validation},
        )
        self.session.flush()
        return manifest

    def update_manifest_document(
        self,
        *,
        manifest: AnimatedTemplateManifest,
        manifest_payload: dict[str, Any],
        manifest_sha256: str,
        manifest_schema_version: int,
        validation: dict[str, Any],
        summary: dict[str, Any],
        actor_user_id: str,
        update_notes: str | None = None,
    ) -> AnimatedTemplateManifest:
        manifest.manifest = manifest_payload
        manifest.manifest_sha256 = manifest_sha256
        manifest.manifest_schema_version = manifest_schema_version
        manifest.validation = validation
        manifest.summary = summary
        manifest.status = "needs_review"
        manifest.approved_by_user_id = None
        manifest.approved_at = None
        manifest.rejected_by_user_id = None
        manifest.rejected_at = None
        manifest.rejection_reason = None
        manifest.updated_at = datetime.now(timezone.utc)
        self.create_event(
            org_id=str(manifest.org_id),
            manifest_id=str(manifest.id),
            event_type="manifest.updated",
            actor_user_id=actor_user_id,
            payload={
                "updateNotes": update_notes,
                "manifestSha256": manifest_sha256,
                "validation": validation,
                "summary": summary,
            },
        )
        self.session.flush()
        return manifest

    def reject_manifest(
        self,
        *,
        manifest: AnimatedTemplateManifest,
        actor_user_id: str,
        reason: str,
    ) -> AnimatedTemplateManifest:
        manifest.status = "rejected"
        manifest.rejected_by_user_id = actor_user_id
        manifest.rejected_at = datetime.now(timezone.utc)
        manifest.rejection_reason = reason
        manifest.updated_at = datetime.now(timezone.utc)
        self.create_event(
            org_id=str(manifest.org_id),
            manifest_id=str(manifest.id),
            event_type="manifest.rejected",
            actor_user_id=actor_user_id,
            payload={"reason": reason},
        )
        self.session.flush()
        return manifest

    def create_event(
        self,
        *,
        org_id: str,
        manifest_id: str,
        event_type: str,
        actor_user_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AnimatedTemplateManifestEvent:
        event = AnimatedTemplateManifestEvent(
            org_id=org_id,
            manifest_id=manifest_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            payload=payload or {},
        )
        self.session.add(event)
        self.session.flush()
        return event

    def create_run(self, **fields: Any) -> AnimatedTemplateRun:
        run = AnimatedTemplateRun(**fields)
        self.session.add(run)
        self.session.flush()
        return run

    def get_run(self, *, org_id: str, run_id: str) -> AnimatedTemplateRun | None:
        stmt = select(AnimatedTemplateRun).where(
            AnimatedTemplateRun.org_id == org_id,
            AnimatedTemplateRun.id == run_id,
        )
        return self.session.scalars(stmt).first()

    def get_run_by_idempotency_key(
        self,
        *,
        org_id: str,
        idempotency_key: str,
    ) -> AnimatedTemplateRun | None:
        stmt = select(AnimatedTemplateRun).where(
            AnimatedTemplateRun.org_id == org_id,
            AnimatedTemplateRun.idempotency_key == idempotency_key,
        )
        return self.session.scalars(stmt).first()

    def list_runs(
        self,
        *,
        org_id: str,
        manifest_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AnimatedTemplateRun]:
        stmt = select(AnimatedTemplateRun).where(AnimatedTemplateRun.org_id == org_id)
        if manifest_id:
            stmt = stmt.where(AnimatedTemplateRun.manifest_id == manifest_id)
        if status:
            stmt = stmt.where(AnimatedTemplateRun.status == status)
        stmt = stmt.order_by(AnimatedTemplateRun.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def mark_run_running(self, *, run: AnimatedTemplateRun) -> AnimatedTemplateRun:
        now = datetime.now(timezone.utc)
        run.status = "running"
        run.started_at = run.started_at or now
        run.updated_at = now
        self.session.flush()
        return run

    def mark_run_failed(
        self,
        *,
        run: AnimatedTemplateRun,
        error_code: str,
        error_message: str,
    ) -> AnimatedTemplateRun:
        now = datetime.now(timezone.utc)
        run.status = "failed"
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = now
        run.updated_at = now
        self.session.flush()
        return run

    def mark_run_succeeded(
        self,
        *,
        run: AnimatedTemplateRun,
        output_artifact_ids: list[str],
        cost_actual: dict[str, Any] | None = None,
        qa_report: dict[str, Any] | None = None,
    ) -> AnimatedTemplateRun:
        now = datetime.now(timezone.utc)
        run.status = "succeeded"
        run.output_artifact_ids = output_artifact_ids
        if cost_actual is not None:
            run.cost_actual = cost_actual
        if qa_report is not None:
            run.qa_report = qa_report
        run.error_code = None
        run.error_message = None
        run.completed_at = now
        run.updated_at = now
        self.session.flush()
        return run

    def create_artifact(self, **fields: Any) -> AnimatedTemplateArtifact:
        artifact = AnimatedTemplateArtifact(**fields)
        self.session.add(artifact)
        self.session.flush()
        return artifact
