from __future__ import annotations

from typing import Any, Dict, List

from temporalio import activity
from sqlalchemy import select

from app.db.repositories.assets import AssetsRepository
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum, AssetSourceEnum
from app.db.models import Funnel


def _repo(session) -> AssetsRepository:
    return AssetsRepository(session)


@activity.defn
def generate_assets_for_brief_activity(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Placeholder assets
    assets = [
        {
            "channel_id": "meta",
            "format": "video_30s",
            "content": {"script": "Placeholder"},
            "source_type": AssetSourceEnum.generated.value,
        }
    ]
    return assets


@activity.defn
def persist_assets_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    assets = params.get("assets", [])
    asset_brief_id = params.get("asset_brief_id")
    if not asset_brief_id:
        raise ValueError("asset_brief_id is required to persist assets")
    if not assets:
        raise ValueError("assets are required to persist assets")

    brief = None
    brief_artifact_id = None
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        briefs_artifacts = artifacts_repo.list(
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            limit=200,
        )
        for art in briefs_artifacts:
            payload = art.data if isinstance(art.data, dict) else {}
            for entry in payload.get("asset_briefs") or []:
                if isinstance(entry, dict) and str(entry.get("id")) == str(asset_brief_id):
                    brief = entry
                    brief_artifact_id = art.id
                    break
            if brief:
                break

        if not brief:
            raise ValueError(f"Asset brief not found: {asset_brief_id}")

        funnel_id = brief.get("funnelId")
        if campaign_id and not funnel_id:
            raise ValueError("Asset brief is missing funnelId; assign a funnel before generating assets.")
        if funnel_id:
            funnel = session.scalars(
                select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)
            ).first()
            if not funnel:
                raise ValueError(f"Funnel not found for asset brief {asset_brief_id}")
            if str(funnel.client_id) != str(client_id):
                raise ValueError("Funnel must belong to the same client as the asset brief")
            if campaign_id and str(funnel.campaign_id) != str(campaign_id):
                raise ValueError("Funnel must belong to the same campaign as the asset brief")
            experiment_id = brief.get("experimentId")
            if experiment_id and funnel.experiment_spec_id and funnel.experiment_spec_id != experiment_id:
                raise ValueError("Funnel experiment does not match asset brief experiment")

        repo = _repo(session)
        created = []
        for asset in assets:
            created_asset = repo.create(
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                channel_id=asset["channel_id"],
                format=asset["format"],
                content=asset["content"],
                source_type=asset.get("source_type", AssetSourceEnum.generated),
                asset_brief_artifact_id=brief_artifact_id,
                funnel_id=funnel_id,
            )
            created.append(str(created_asset.id))
        return {"assets": created}
