"""Connected social agent API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Client
from app.db.repositories.connected_social import (
    AgentActionProposalsRepository,
    SocialProviderAssetsRepository,
    SocialProviderSnapshotsRepository,
)
from app.schemas.connected_social import (
    AgentActionProposalApproveRequest,
    AgentActionProposalCreateRequest,
    AgentActionProposalResponse,
    SocialProviderAssetResponse,
    SocialProviderAssetUpsertRequest,
    SocialProviderSnapshotCreateRequest,
    SocialProviderSnapshotResponse,
)


router = APIRouter(prefix="/clients/{client_id}/connected-social", tags=["connected-social"])


def _require_client(session: Session, *, org_id: str, client_id: str) -> Client:
    client = session.scalars(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    ).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return client


def _serialize_asset(asset) -> SocialProviderAssetResponse:
    return SocialProviderAssetResponse.model_validate(
        {
            "id": str(asset.id),
            "connectionId": str(asset.connection_id) if asset.connection_id else None,
            "provider": asset.provider,
            "providerAssetId": asset.provider_asset_id,
            "assetType": asset.asset_type,
            "displayName": asset.display_name,
            "parentProviderAssetId": asset.parent_provider_asset_id,
            "capabilityFlags": list(asset.capability_flags_json or []),
            "status": asset.status,
            "metadata": asset.metadata_json or {},
            "lastSyncedAt": asset.last_synced_at,
            "createdAt": asset.created_at,
            "updatedAt": asset.updated_at,
        }
    )


def _serialize_snapshot(snapshot) -> SocialProviderSnapshotResponse:
    return SocialProviderSnapshotResponse.model_validate(
        {
            "id": str(snapshot.id),
            "providerAssetId": str(snapshot.provider_asset_id) if snapshot.provider_asset_id else None,
            "provider": snapshot.provider,
            "snapshotType": snapshot.snapshot_type,
            "timeFrom": snapshot.time_from,
            "timeTo": snapshot.time_to,
            "metrics": snapshot.metrics_json or {},
            "provenance": snapshot.provenance,
            "createdAt": snapshot.created_at,
        }
    )


def _serialize_proposal(proposal) -> AgentActionProposalResponse:
    return AgentActionProposalResponse.model_validate(
        {
            "id": str(proposal.id),
            "campaignId": str(proposal.campaign_id) if proposal.campaign_id else None,
            "sourceAgentRunId": str(proposal.source_agent_run_id) if proposal.source_agent_run_id else None,
            "actionType": proposal.action_type,
            "targetProvider": proposal.target_provider,
            "targetAssetId": proposal.target_asset_id,
            "targetAssetType": proposal.target_asset_type,
            "beforeSnapshot": proposal.before_snapshot_json or {},
            "proposedAfter": proposal.proposed_after_json or {},
            "rationale": proposal.rationale,
            "riskLabel": proposal.risk_label,
            "requiredCapability": proposal.required_capability,
            "status": proposal.status,
            "approvedByUserId": proposal.approved_by_user_id,
            "approvedAt": proposal.approved_at,
            "executedAt": proposal.executed_at,
            "providerResponse": proposal.provider_response_json,
            "rollbackHint": proposal.rollback_hint_json or {},
            "metadata": proposal.metadata_json or {},
            "createdAt": proposal.created_at,
            "updatedAt": proposal.updated_at,
        }
    )


@router.get("/provider-assets")
def list_provider_assets(
    client_id: str,
    provider: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = SocialProviderAssetsRepository(session)
    assets = repo.list(org_id=auth.org_id, client_id=client_id, provider=provider)
    return jsonable_encoder([_serialize_asset(asset) for asset in assets])


@router.post("/provider-assets", status_code=status.HTTP_201_CREATED)
def upsert_provider_asset(
    client_id: str,
    payload: SocialProviderAssetUpsertRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = SocialProviderAssetsRepository(session)
    asset = repo.upsert(
        org_id=auth.org_id,
        client_id=client_id,
        connection_id=payload.connection_id,
        provider=payload.provider,
        provider_asset_id=payload.provider_asset_id,
        asset_type=payload.asset_type,
        display_name=payload.display_name,
        parent_provider_asset_id=payload.parent_provider_asset_id,
        capability_flags_json=payload.capability_flags,
        status=payload.status,
        raw_payload_json=payload.raw_payload,
        metadata_json=payload.metadata,
    )
    session.commit()
    return jsonable_encoder(_serialize_asset(asset))


@router.get("/snapshots")
def list_snapshots(
    client_id: str,
    provider_asset_id: str | None = Query(default=None, alias="providerAssetId"),
    limit: int = 50,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = SocialProviderSnapshotsRepository(session)
    snapshots = repo.list(
        org_id=auth.org_id,
        client_id=client_id,
        provider_asset_id=provider_asset_id,
        limit=max(1, min(limit, 200)),
    )
    return jsonable_encoder([_serialize_snapshot(snapshot) for snapshot in snapshots])


@router.post("/snapshots", status_code=status.HTTP_201_CREATED)
def create_snapshot(
    client_id: str,
    payload: SocialProviderSnapshotCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = SocialProviderSnapshotsRepository(session)
    snapshot = repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        provider_asset_id=payload.provider_asset_id,
        provider=payload.provider,
        snapshot_type=payload.snapshot_type,
        time_from=payload.time_from,
        time_to=payload.time_to,
        metrics_json=payload.metrics,
        raw_payload_json=payload.raw_payload,
        provenance=payload.provenance,
    )
    session.commit()
    return jsonable_encoder(_serialize_snapshot(snapshot))


@router.get("/action-proposals")
def list_action_proposals(
    client_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = AgentActionProposalsRepository(session)
    proposals = repo.list(
        org_id=auth.org_id,
        client_id=client_id,
        status=status_filter,
        limit=max(1, min(limit, 200)),
    )
    return jsonable_encoder([_serialize_proposal(proposal) for proposal in proposals])


@router.post("/action-proposals", status_code=status.HTTP_201_CREATED)
def create_action_proposal(
    client_id: str,
    payload: AgentActionProposalCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = AgentActionProposalsRepository(session)
    proposal = repo.create(
        org_id=auth.org_id,
        client_id=client_id,
        campaign_id=payload.campaign_id,
        source_agent_run_id=payload.source_agent_run_id,
        action_type=payload.action_type,
        target_provider=payload.target_provider,
        target_asset_id=payload.target_asset_id,
        target_asset_type=payload.target_asset_type,
        before_snapshot_json=payload.before_snapshot,
        proposed_after_json=payload.proposed_after,
        rationale=payload.rationale,
        risk_label=payload.risk_label,
        required_capability=payload.required_capability,
        rollback_hint_json=payload.rollback_hint,
        metadata_json=payload.metadata,
    )
    session.commit()
    return jsonable_encoder(_serialize_proposal(proposal))


@router.post("/action-proposals/{proposal_id}/approve")
def approve_action_proposal(
    client_id: str,
    proposal_id: str,
    payload: AgentActionProposalApproveRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _require_client(session, org_id=auth.org_id, client_id=client_id)
    repo = AgentActionProposalsRepository(session)
    proposal = repo.get(org_id=auth.org_id, proposal_id=proposal_id)
    if proposal is None or str(proposal.client_id) != str(client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action proposal not found.")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending action proposals can be approved.",
        )
    approved = repo.approve(
        org_id=auth.org_id,
        proposal_id=proposal_id,
        approved_by_user_id=auth.user_id,
        notes=payload.notes if payload else None,
    )
    session.commit()
    return jsonable_encoder(_serialize_proposal(approved))
