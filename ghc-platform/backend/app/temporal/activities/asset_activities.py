from __future__ import annotations

from typing import Any, Dict, List

from temporalio import activity

from app.db.repositories.assets import AssetsRepository
from app.db.base import session_scope
from app.db.enums import AssetStatusEnum, AssetSourceEnum


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
    created = []
    with session_scope() as session:
        repo = _repo(session)
        for asset in assets:
            created_asset = repo.create(
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                channel_id=asset["channel_id"],
                format=asset["format"],
                content=asset["content"],
                source_type=asset.get("source_type", AssetSourceEnum.generated),
            )
            created.append(str(created_asset.id))
    return {"assets": created}
