"""Repositories for connected social agent primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    AgentActionProposal,
    SocialProviderAsset,
    SocialProviderSnapshot,
)


class SocialProviderAssetsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, org_id: str, client_id: str, provider: str | None = None) -> list[SocialProviderAsset]:
        stmt = select(SocialProviderAsset).where(
            SocialProviderAsset.org_id == org_id,
            SocialProviderAsset.client_id == client_id,
        )
        if provider:
            stmt = stmt.where(SocialProviderAsset.provider == provider)
        stmt = stmt.order_by(SocialProviderAsset.provider, SocialProviderAsset.asset_type, SocialProviderAsset.display_name)
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, asset_id: str) -> SocialProviderAsset | None:
        stmt = select(SocialProviderAsset).where(
            SocialProviderAsset.id == asset_id,
            SocialProviderAsset.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        provider: str,
        provider_asset_id: str,
        asset_type: str,
        display_name: str,
        connection_id: str | None = None,
        parent_provider_asset_id: str | None = None,
        capability_flags_json: list[str] | None = None,
        status: str = "active",
        raw_payload_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> SocialProviderAsset:
        now = datetime.now(timezone.utc)
        stmt = (
            insert(SocialProviderAsset)
            .values(
                org_id=org_id,
                client_id=client_id,
                connection_id=connection_id,
                provider=provider,
                provider_asset_id=provider_asset_id,
                asset_type=asset_type,
                display_name=display_name,
                parent_provider_asset_id=parent_provider_asset_id,
                capability_flags_json=capability_flags_json or [],
                status=status,
                raw_payload_json=raw_payload_json or {},
                metadata_json=metadata_json or {},
                last_synced_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_social_provider_assets_provider_asset_type",
                set_={
                    "connection_id": connection_id,
                    "display_name": display_name,
                    "parent_provider_asset_id": parent_provider_asset_id,
                    "capability_flags_json": capability_flags_json or [],
                    "status": status,
                    "raw_payload_json": raw_payload_json or {},
                    "metadata_json": metadata_json or {},
                    "last_synced_at": now,
                    "updated_at": now,
                },
            )
            .returning(SocialProviderAsset)
        )
        asset = self.session.execute(stmt).scalar_one()
        self.session.flush()
        self.session.refresh(asset)
        return asset


class SocialProviderSnapshotsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        provider: str,
        snapshot_type: str,
        provider_asset_id: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        metrics_json: dict[str, Any] | None = None,
        raw_payload_json: dict[str, Any] | None = None,
        provenance: str = "concrete",
    ) -> SocialProviderSnapshot:
        snapshot = SocialProviderSnapshot(
            org_id=org_id,
            client_id=client_id,
            provider_asset_id=provider_asset_id,
            provider=provider,
            snapshot_type=snapshot_type,
            time_from=time_from,
            time_to=time_to,
            metrics_json=metrics_json or {},
            raw_payload_json=raw_payload_json or {},
            provenance=provenance,
        )
        self.session.add(snapshot)
        self.session.flush()
        self.session.refresh(snapshot)
        return snapshot

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
        provider_asset_id: str | None = None,
        limit: int = 50,
    ) -> list[SocialProviderSnapshot]:
        stmt = select(SocialProviderSnapshot).where(
            SocialProviderSnapshot.org_id == org_id,
            SocialProviderSnapshot.client_id == client_id,
        )
        if provider_asset_id:
            stmt = stmt.where(SocialProviderSnapshot.provider_asset_id == provider_asset_id)
        stmt = stmt.order_by(SocialProviderSnapshot.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())


class AgentActionProposalsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        org_id: str,
        client_id: str,
        action_type: str,
        target_provider: str,
        campaign_id: str | None = None,
        source_agent_run_id: str | None = None,
        target_asset_id: str | None = None,
        target_asset_type: str | None = None,
        before_snapshot_json: dict[str, Any] | None = None,
        proposed_after_json: dict[str, Any] | None = None,
        rationale: str | None = None,
        risk_label: str = "medium",
        required_capability: str | None = None,
        rollback_hint_json: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> AgentActionProposal:
        proposal = AgentActionProposal(
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            source_agent_run_id=source_agent_run_id,
            action_type=action_type,
            target_provider=target_provider,
            target_asset_id=target_asset_id,
            target_asset_type=target_asset_type,
            before_snapshot_json=before_snapshot_json or {},
            proposed_after_json=proposed_after_json or {},
            rationale=rationale,
            risk_label=risk_label,
            required_capability=required_capability,
            rollback_hint_json=rollback_hint_json or {},
            metadata_json=metadata_json or {},
        )
        self.session.add(proposal)
        self.session.flush()
        self.session.refresh(proposal)
        return proposal

    def list(
        self,
        *,
        org_id: str,
        client_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AgentActionProposal]:
        stmt = select(AgentActionProposal).where(
            AgentActionProposal.org_id == org_id,
            AgentActionProposal.client_id == client_id,
        )
        if status:
            stmt = stmt.where(AgentActionProposal.status == status)
        stmt = stmt.order_by(AgentActionProposal.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def get(self, *, org_id: str, proposal_id: str) -> AgentActionProposal | None:
        stmt = select(AgentActionProposal).where(
            AgentActionProposal.id == proposal_id,
            AgentActionProposal.org_id == org_id,
        )
        return self.session.scalars(stmt).first()

    def approve(
        self,
        *,
        org_id: str,
        proposal_id: str,
        approved_by_user_id: str,
        notes: str | None = None,
    ) -> AgentActionProposal | None:
        proposal = self.get(org_id=org_id, proposal_id=proposal_id)
        if proposal is None:
            return None
        proposal.status = "approved"
        proposal.approved_by_user_id = approved_by_user_id
        proposal.approved_at = datetime.now(timezone.utc)
        proposal.updated_at = datetime.now(timezone.utc)
        if notes:
            proposal.metadata_json = {**(proposal.metadata_json or {}), "approvalNotes": notes}
        self.session.flush()
        self.session.refresh(proposal)
        return proposal
