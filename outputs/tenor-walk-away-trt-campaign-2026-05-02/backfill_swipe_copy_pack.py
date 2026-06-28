#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.db.base import SessionLocal
from app.db.enums import ArtifactTypeEnum
from app.db.models import Asset, Campaign, CampaignDeliveryConfig
from app.db.repositories.artifacts import ArtifactsRepository
from app.schemas.creative_generation import SwipeCopyInputs, SwipeCopySourceSwipeProvenance
from app.temporal.activities.asset_activities import _get_or_create_ad_copy_pack_artifact
from app.temporal.activities.swipe_image_ad_activities import (
    _download_bytes,
    _generate_rendered_asset_swipe_copy_pack,
    _resolve_linked_ad_copy_pack_context,
    _resolve_swipe_copy_asset_type,
    _resolve_swipe_stage1_gemini_file_search_context,
)


def _load_manifest_asset_ids(path: Path) -> list[str]:
    payload = json.loads(path.read_text())
    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise RuntimeError(f"Manifest has no outputs array: {path}")
    asset_ids: list[str] = []
    for index, item in enumerate(outputs, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Manifest output #{index} is not an object.")
        result = item.get("result")
        asset_id = result.get("assetId") if isinstance(result, dict) else None
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise RuntimeError(f"Manifest output #{index} is missing result.assetId.")
        asset_ids.append(asset_id.strip())
    if len(set(asset_ids)) != len(asset_ids):
        raise RuntimeError("Manifest contains duplicate asset IDs.")
    return asset_ids


def _select_brief(asset_brief_payload: dict[str, Any], asset_brief_id: str) -> dict[str, Any]:
    briefs = asset_brief_payload.get("asset_briefs")
    if not isinstance(briefs, list):
        briefs = asset_brief_payload.get("assetBriefs")
    if not isinstance(briefs, list):
        raise RuntimeError("Asset brief artifact data is missing asset_briefs.")
    for brief in briefs:
        if isinstance(brief, dict) and brief.get("id") == asset_brief_id:
            return brief
    raise RuntimeError(f"Asset brief {asset_brief_id!r} was not found in the artifact payload.")


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Missing required string: {label}.")
    return value.strip()


def _copy_prompt_model(metadata: dict[str, Any]) -> str:
    return _required_string(metadata.get("swipePromptModel"), "ai_metadata.swipePromptModel")


def _rendered_image_url(asset: Asset, public_asset_base: str) -> str:
    public_id = str(asset.public_id).strip() if asset.public_id is not None else ""
    if not public_id:
        raise RuntimeError("Missing required string: asset.public_id.")
    return f"{public_asset_base.rstrip('/')}/{public_id}"


def _source_swipe(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "companySwipeId": metadata.get("swipeCompanyId"),
        "sourceLabel": metadata.get("swipeSourceFilename"),
        "sourceUrl": metadata.get("swipeSourceUrl"),
        "mimeType": metadata.get("swipePromptImageMimeType"),
    }


def _find_asset_by_id(assets: list[Asset], asset_id: str) -> Asset:
    for asset in assets:
        if str(asset.id) == asset_id:
            return asset
    raise RuntimeError(f"Manifest asset {asset_id} was not found in production.")


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_asset_ids = _load_manifest_asset_ids(Path(args.manifest))
    run_id = f"swipe-copy-backfill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    session = SessionLocal()
    try:
        campaign = session.execute(
            select(Campaign).where(Campaign.id == args.campaign_id)
        ).scalar_one_or_none()
        if campaign is None:
            raise RuntimeError(f"Campaign not found: {args.campaign_id}")
        if str(campaign.client_id) != args.client_id:
            raise RuntimeError(
                f"Campaign client mismatch: expected {args.client_id}, found {campaign.client_id}"
            )
        if str(campaign.product_id) != args.product_id:
            raise RuntimeError(
                f"Campaign product mismatch: expected {args.product_id}, found {campaign.product_id}"
            )

        delivery_config = session.execute(
            select(CampaignDeliveryConfig).where(CampaignDeliveryConfig.campaign_id == args.campaign_id)
        ).scalar_one_or_none()
        if delivery_config is None:
            raise RuntimeError(f"Campaign delivery config not found: {args.campaign_id}")

        artifacts_repo = ArtifactsRepository(session)
        asset_brief_artifact = artifacts_repo.get(
            org_id=str(campaign.org_id),
            artifact_id=args.asset_brief_artifact_id,
        )
        if asset_brief_artifact is None:
            raise RuntimeError(f"Asset brief artifact not found: {args.asset_brief_artifact_id}")
        if asset_brief_artifact.type != ArtifactTypeEnum.asset_brief:
            raise RuntimeError(
                f"Artifact {args.asset_brief_artifact_id} is not an asset_brief; found {asset_brief_artifact.type}"
            )
        if str(asset_brief_artifact.campaign_id) != args.campaign_id:
            raise RuntimeError(
                f"Asset brief artifact campaign mismatch: expected {args.campaign_id}, "
                f"found {asset_brief_artifact.campaign_id}"
            )
        brief = _select_brief(asset_brief_artifact.data, args.asset_brief_id)
        requirements = brief.get("requirements")
        if not isinstance(requirements, list) or not requirements:
            raise RuntimeError(f"Asset brief {args.asset_brief_id} has no requirements.")

        assets = list(
            session.execute(select(Asset).where(Asset.campaign_id == args.campaign_id)).scalars().all()
        )
        selected_assets = [_find_asset_by_id(assets, asset_id) for asset_id in manifest_asset_ids]
        for asset in selected_assets:
            if str(asset.client_id) != args.client_id:
                raise RuntimeError(f"Asset {asset.id} client mismatch.")
            if str(asset.product_id) != args.product_id:
                raise RuntimeError(f"Asset {asset.id} product mismatch.")
            metadata = asset.ai_metadata if isinstance(asset.ai_metadata, dict) else {}
            if metadata.get("creativeGenerationBatchId") != args.batch_id:
                raise RuntimeError(
                    f"Asset {asset.id} is not in batch {args.batch_id}; "
                    f"found {metadata.get('creativeGenerationBatchId')!r}."
                )
            if metadata.get("assetBriefId") != args.asset_brief_id:
                raise RuntimeError(
                    f"Asset {asset.id} assetBriefId mismatch: {metadata.get('assetBriefId')!r}"
                )

        ad_copy_artifact = _get_or_create_ad_copy_pack_artifact(
            session=session,
            org_id=str(campaign.org_id),
            client_id=args.client_id,
            product_id=args.product_id,
            campaign_id=args.campaign_id,
            asset_brief_id=args.asset_brief_id,
            brief_artifact_id=args.asset_brief_artifact_id,
            brief=brief,
            campaign_delivery_config=delivery_config,
        )
        session.commit()

        gemini_store_names: list[str] = []
        gemini_rag_doc_keys: list[str] = []
        gemini_rag_bundle_doc_keys: list[str] = []
        gemini_rag_document_names: list[str] = []
        stage1_file_search_mode = "not_requested"
        if args.use_stage1_file_search:
            (
                gemini_store_names,
                gemini_rag_doc_keys,
                gemini_rag_bundle_doc_keys,
                gemini_rag_document_names,
            ) = _resolve_swipe_stage1_gemini_file_search_context(
                session=session,
                org_id=str(campaign.org_id),
                idea_workspace_id=args.campaign_id,
                client_id=args.client_id,
                product_id=args.product_id,
                campaign_id=args.campaign_id,
                funnel_id=None,
                asset_brief_artifact_id=args.asset_brief_artifact_id,
            )
            if not gemini_store_names:
                raise RuntimeError("No Gemini File Search stores resolved for swipe copy backfill.")
            stage1_file_search_mode = "attached"

        linked_context_by_requirement: dict[int, dict[str, Any]] = {}
        updated: list[dict[str, Any]] = []
        skipped: list[str] = []
        for ordinal, asset in enumerate(selected_assets, start=1):
            metadata = dict(asset.ai_metadata or {})
            if isinstance(metadata.get("swipeCopyPack"), dict) and not args.force:
                skipped.append(str(asset.id))
                print(json.dumps({"event": "skip_existing_copy", "assetId": str(asset.id)}), flush=True)
                continue

            requirement_index = metadata.get("requirementIndex")
            if not isinstance(requirement_index, int):
                raise RuntimeError(f"Asset {asset.id} is missing integer ai_metadata.requirementIndex.")
            if requirement_index < 0 or requirement_index >= len(requirements):
                raise RuntimeError(
                    f"Asset {asset.id} requirementIndex {requirement_index} is out of range."
                )
            requirement = requirements[requirement_index]
            if not isinstance(requirement, dict):
                raise RuntimeError(
                    f"Asset brief requirement {requirement_index} must be an object."
                )

            linked_context = linked_context_by_requirement.get(requirement_index)
            if linked_context is None:
                linked_context = _resolve_linked_ad_copy_pack_context(
                    session=session,
                    org_id=str(campaign.org_id),
                    client_id=args.client_id,
                    product_id=args.product_id,
                    campaign_id=args.campaign_id,
                    asset_brief_id=args.asset_brief_id,
                    requirement_index=requirement_index,
                    ad_copy_pack_artifact_id=str(ad_copy_artifact.id),
                    ad_copy_pack_id=None,
                )
                linked_context_by_requirement[requirement_index] = linked_context

            rendered_url = _rendered_image_url(asset, args.public_asset_base)
            rendered_bytes, rendered_mime_type = _download_bytes(
                rendered_url,
                max_bytes=int(os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))),
                timeout_seconds=float(os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")),
            )
            rendered_label = metadata.get("renderedAdImageSourceLabel")
            if not isinstance(rendered_label, str) or not rendered_label.strip():
                rendered_label = None

            swipe_copy_pack, swipe_copy_response, swipe_copy_model, swipe_copy_prompt_text = (
                _generate_rendered_asset_swipe_copy_pack(
                    session=session,
                    brief=brief,
                    requirement_index=requirement_index,
                    requirement=requirement,
                    copy_model=_copy_prompt_model(metadata),
                    gemini_store_names=gemini_store_names,
                    rendered_ad_bytes=rendered_bytes,
                    rendered_ad_mime_type=rendered_mime_type,
                    rendered_ad_source_url=rendered_url,
                    rendered_ad_source_label=rendered_label,
                    linked_ad_copy_pack=linked_context["copyPack"],
                    product_prompt_image_bytes=None,
                    product_prompt_image_mime_type=None,
                )
            )
            swipe_copy_pack_payload = swipe_copy_pack.model_dump(mode="json", by_alias=True)
            source_swipe = SwipeCopySourceSwipeProvenance(
                **{
                    key: value
                    for key, value in _source_swipe(metadata).items()
                    if value is not None
                }
            ).model_dump(mode="json", by_alias=True, exclude_none=True)
            swipe_copy_inputs = SwipeCopyInputs(
                platform=swipe_copy_pack.platform,
                adImageOrVideo={
                    "sourceKind": "rendered_output",
                    "assetType": _resolve_swipe_copy_asset_type(mime_type=rendered_mime_type),
                    "sourceLabel": rendered_label,
                    "sourceUrl": rendered_url,
                    "mimeType": rendered_mime_type,
                    "storageKey": asset.storage_key,
                    "remoteAssetId": metadata.get("remoteAssetId"),
                },
                angleUsed=str(requirement.get("angle") or ""),
                destinationPage=swipe_copy_pack.destination_type,
                adCopyPackId=linked_context["copyPackId"],
                adCopyPackArtifactId=linked_context["artifactId"],
                sourceSwipe=source_swipe,
            ).model_dump(mode="json", by_alias=True, exclude_none=True)

            metadata.update(
                {
                    "swipeCopyPipelineVersion": 2,
                    "swipeCopyPack": swipe_copy_pack_payload,
                    "swipeCopyModel": swipe_copy_model,
                    "swipeCopyRequestId": (
                        swipe_copy_response.get("request_id")
                        if isinstance(swipe_copy_response, dict)
                        else None
                    ),
                    "swipeCopyStopReason": (
                        swipe_copy_response.get("stop_reason")
                        if isinstance(swipe_copy_response, dict)
                        else None
                    ),
                    "swipeCopyOutputTokens": (
                        swipe_copy_response.get("output_tokens")
                        if isinstance(swipe_copy_response, dict)
                        else None
                    ),
                    "swipeCopyPromptText": swipe_copy_prompt_text,
                    "swipeCopyPromptSha256": hashlib.sha256(
                        swipe_copy_prompt_text.encode("utf-8")
                    ).hexdigest(),
                    "swipeCopyInputs": swipe_copy_inputs,
                    "swipeCopyGeminiStoreNames": gemini_store_names,
                    "renderedAdImagePublicAssetUrl": rendered_url,
                    "adCopyPackArtifactId": linked_context["artifactId"],
                    "adCopyPackId": linked_context["copyPackId"],
                    "swipeCopyGenerationSkipped": False,
                    "swipeCopyBackfillContextMode": "linked_ad_copy_pack",
                    "swipeCopyBackfillStage1FileSearchMode": stage1_file_search_mode,
                    "swipeCopyBackfillRunId": run_id,
                    "swipeCopyBackfilledAt": datetime.now(timezone.utc).isoformat(),
                }
            )
            metadata.pop("swipeCopyGenerationReason", None)

            asset.ai_metadata = metadata
            flag_modified(asset, "ai_metadata")
            session.add(asset)
            session.commit()

            progress = {
                "event": "updated_asset_copy",
                "ordinal": ordinal,
                "total": len(selected_assets),
                "assetId": str(asset.id),
                "headline": swipe_copy_pack.meta_headline,
                "cta": swipe_copy_pack.meta_cta,
            }
            updated.append(progress)
            print(json.dumps(progress), flush=True)

        summary = {
            "runId": run_id,
            "campaignId": args.campaign_id,
            "assetBriefId": args.asset_brief_id,
            "assetBriefArtifactId": args.asset_brief_artifact_id,
            "batchId": args.batch_id,
            "manifestAssetCount": len(manifest_asset_ids),
            "updatedCount": len(updated),
            "skippedCount": len(skipped),
            "adCopyPackArtifactId": str(ad_copy_artifact.id),
            "stage1FileSearchMode": stage1_file_search_mode,
            "geminiStoreNames": gemini_store_names,
            "geminiRagDocKeys": gemini_rag_doc_keys,
            "geminiRagBundleDocKeys": gemini_rag_bundle_doc_keys,
            "geminiRagDocumentNames": gemini_rag_document_names,
            "updated": updated,
            "skipped": skipped,
        }
        if args.summary:
            Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({"event": "complete", **summary}), flush=True)
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--asset-brief-id", required=True)
    parser.add_argument("--asset-brief-artifact-id", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--public-asset-base", default="https://api.moshq.app/public/assets")
    parser.add_argument("--use-stage1-file-search", action="store_true")
    parser.add_argument("--force", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
