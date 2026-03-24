from __future__ import annotations

import hashlib
import io
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.models import Campaign, SwipeCollectionItem, WorkflowRun
from app.db.repositories.swipes import (
    WRITABLE_SWIPE_COLLECTION_KINDS,
    CompanySwipesRepository,
    ClientSwipesRepository,
    SwipeCollectionsRepository,
)
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.swipe_assets import (
    ClientSwipeAssetModel,
    CompanySwipeAssetModel,
    CompanySwipeMediaModel,
    SwipeAssetUpdateRequest,
    SwipeCollectionCloneRequest,
    SwipeCollectionCreateRequest,
    SwipeCollectionDetailModel,
    SwipeCollectionItemsRequest,
    SwipeCollectionModel,
    SwipeCollectionUploadResponse,
)
from app.schemas.swipe_image_ads import (
    SwipeImageAdGenerateRequest,
    SwipeTemplateTestimonialsGenerateRequest,
    SwipeTemplateTestimonialsGenerateResponse,
)
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage, MediaStorageConfigurationError
from app.services.funnels import create_funnel_upload_asset
from app.services.meta_review import clean_optional_text, load_campaign_asset_brief_map
from app.temporal.client import get_temporal_client
from app.temporal.workflows.swipe_image_ad import SwipeImageAdInput, SwipeImageAdWorkflow
from app.temporal.workflows.swipe_taxonomy import SwipeTaxonomyInput, SwipeTaxonomyWorkflow

router = APIRouter(prefix="/swipes", tags=["swipes"])
_TEMPLATE_IMAGES_DIR = Path(__file__).resolve().parents[4] / "template-images"
_IMAGE_REQUIREMENT_FORMATS = {"image", "image_ad", "image-ad"}
_SWIPE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class _StoredSwipeUpload:
    storage_key: str
    mime_type: str
    size_bytes: int
    width: int
    height: int


def _resolve_swipe_upload_content_type_or_400(file: UploadFile) -> str:
    content_type = str(file.content_type or "").strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported swipe upload content type: {file.content_type or '[missing]'}. Images only.",
        )
    return content_type


def _infer_swipe_ad_unit_format(content_type: str) -> str:
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    return "carousel"


def _infer_swipe_placement_shape(width: int, height: int) -> str | None:
    if width <= 0 or height <= 0:
        return None
    ratio = width / height
    candidates = {
        "square_1_1": 1.0,
        "portrait_4_5": 4 / 5,
        "story_9_16": 9 / 16,
        "landscape_16_9": 16 / 9,
    }
    best_key = min(candidates, key=lambda key: abs(candidates[key] - ratio))
    if abs(candidates[best_key] - ratio) > 0.25:
        return None
    return best_key


def _store_swipe_upload_media(*, content_bytes: bytes, filename: str | None, content_type: str) -> _StoredSwipeUpload:
    try:
        storage = MediaStorage()
    except MediaStorageConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    sha256 = hashlib.sha256(content_bytes).hexdigest()
    ext = mimetypes.guess_extension(content_type) or Path(filename or "upload.bin").suffix or ".bin"
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=content_bytes,
            content_type=content_type,
            cache_control=IMMUTABLE_CACHE_CONTROL,
        )
    try:
        with Image.open(io.BytesIO(content_bytes)) as image:
            width, height = image.size
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded swipe image is invalid.") from exc
    return _StoredSwipeUpload(
        storage_key=key,
        mime_type=content_type,
        size_bytes=len(content_bytes),
        width=width,
        height=height,
    )


def _build_media_access_url(media) -> str | None:
    for candidate in (
        getattr(media, "download_url", None),
        getattr(media, "url", None),
        getattr(media, "thumbnail_url", None),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    path_value = str(getattr(media, "path", "") or "").strip()
    if not path_value:
        return None
    if path_value.startswith("http://") or path_value.startswith("https://"):
        return path_value
    storage = MediaStorage()
    return storage.presign_get(bucket=storage.bucket, key=path_value)


def _serialize_media(media) -> CompanySwipeMediaModel:
    access_url = _build_media_access_url(media)
    payload = {
        "id": str(media.id),
        "org_id": str(media.org_id),
        "swipe_asset_id": str(media.swipe_asset_id),
        "external_media_id": media.external_media_id,
        "path": media.path,
        "url": access_url,
        "thumbnail_path": media.thumbnail_path,
        "thumbnail_url": media.thumbnail_url or access_url,
        "disk": media.disk,
        "type": media.type,
        "mime_type": media.mime_type,
        "size_bytes": media.size_bytes,
        "video_length": media.video_length,
        "download_url": access_url,
    }
    return CompanySwipeMediaModel.model_validate(payload)


def _serialize_asset(asset, media_map: dict[str, list]) -> CompanySwipeAssetModel:
    payload = {
        "id": str(asset.id),
        "org_id": str(asset.org_id),
        "source_kind": asset.source_kind,
        "origin_system": asset.origin_system,
        "external_ad_id": asset.external_ad_id,
        "external_platform_ad_id": asset.external_platform_ad_id,
        "brand_id": str(asset.brand_id) if getattr(asset, "brand_id", None) else None,
        "title": asset.title,
        "body": asset.body,
        "platforms": asset.platforms,
        "cta_type": asset.cta_type,
        "cta_text": asset.cta_text,
        "display_format": asset.display_format,
        "landing_page": asset.landing_page,
        "link_description": asset.link_description,
        "ad_source_link": asset.ad_source_link,
        "analysis_status": asset.analysis_status,
        "analysis_error": asset.analysis_error,
        "analysis_model": asset.analysis_model,
        "analysis_updated_at": asset.analysis_updated_at,
        "ad_unit_format": asset.ad_unit_format,
        "placement_shape": asset.placement_shape,
        "channel": asset.channel,
        "destination_type": asset.destination_type,
        "funnel_stage": asset.funnel_stage,
        "angle_family": asset.angle_family,
        "hook_type": asset.hook_type,
        "visual_archetype": asset.visual_archetype,
        "product_presence": asset.product_presence,
        "proof_type": asset.proof_type,
        "claim_risk": asset.claim_risk,
        "product_image_policy": asset.product_image_policy,
        "media": [_serialize_media(item) for item in media_map.get(str(asset.id), [])],
    }
    return CompanySwipeAssetModel.model_validate(payload)


def _serialize_collection(*, collection, item_count: int, analysis_counts: dict[str, int]) -> SwipeCollectionModel:
    payload = {
        "id": str(collection.id),
        "org_id": str(collection.org_id),
        "name": collection.name,
        "kind": collection.kind,
        "cloned_from_collection_id": (
            str(collection.cloned_from_collection_id) if collection.cloned_from_collection_id else None
        ),
        "created_by_user_id": collection.created_by_user_id,
        "created_at": collection.created_at,
        "writable": collection.kind in WRITABLE_SWIPE_COLLECTION_KINDS,
        "item_count": item_count,
        "analysis_counts": analysis_counts,
    }
    return SwipeCollectionModel.model_validate(payload)


async def _start_swipe_taxonomy_analysis(
    *,
    swipe_asset_id: str,
    auth: AuthContext,
    temporal=None,
) -> str:
    temporal_client = temporal or await get_temporal_client()
    temporal_workflow_id = f"swipe-taxonomy-{auth.org_id}-{swipe_asset_id}-{uuid4()}"
    handle = await temporal_client.start_workflow(
        SwipeTaxonomyWorkflow.run,
        SwipeTaxonomyInput(
            org_id=auth.org_id,
            swipe_asset_id=swipe_asset_id,
        ),
        id=temporal_workflow_id,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )
    return handle.id


def _normalize_requirement_format(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _require_public_asset_base_url() -> str:
    base_url = str(settings.PUBLIC_ASSET_BASE_URL or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PUBLIC_ASSET_BASE_URL is required for swipe template testimonial generation.",
        )
    return base_url.rstrip("/")


def _collect_template_image_paths() -> list[Path]:
    if not _TEMPLATE_IMAGES_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image directory does not exist: {_TEMPLATE_IMAGES_DIR}",
        )
    if not _TEMPLATE_IMAGES_DIR.is_dir():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image path must be a directory: {_TEMPLATE_IMAGES_DIR}",
        )

    files: list[Path] = []
    for path in sorted(_TEMPLATE_IMAGES_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        content_type = mimetypes.guess_type(path.name)[0] or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image file has unsupported content type: {path.name}",
            )
        files.append(path)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Swipe template image directory is empty: {_TEMPLATE_IMAGES_DIR}",
        )
    return files


def _resolve_single_image_requirement_index(brief: dict) -> int:
    requirements = brief.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset brief has no requirements.",
        )

    image_indexes: list[int] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Asset brief requirement at index {index} must be an object.",
            )
        normalized_format = _normalize_requirement_format(str(requirement.get("format") or ""))
        if normalized_format in _IMAGE_REQUIREMENT_FORMATS:
            image_indexes.append(index)

    if not image_indexes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset brief has no image requirement for swipe template testimonial generation.",
        )
    if len(image_indexes) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Asset brief must contain exactly one image requirement for swipe template testimonial generation. "
                f"Found indexes: {image_indexes}."
            ),
        )
    return image_indexes[0]


async def _start_swipe_image_ad_run(
    *,
    payload: SwipeImageAdGenerateRequest,
    auth: AuthContext,
    session: Session,
    temporal=None,
) -> dict[str, str]:
    temporal_client = temporal or await get_temporal_client()
    temporal_workflow_id = f"swipe-image-ad-{auth.org_id}-{payload.campaign_id}-{uuid4()}"

    run = WorkflowRun(
        org_id=auth.org_id,
        client_id=payload.client_id,
        product_id=payload.product_id,
        campaign_id=payload.campaign_id,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind="swipe_image_ad",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        handle = await temporal_client.start_workflow(
            SwipeImageAdWorkflow.run,
            SwipeImageAdInput(
                org_id=auth.org_id,
                client_id=payload.client_id,
                product_id=payload.product_id,
                campaign_id=payload.campaign_id,
                asset_brief_id=payload.asset_brief_id,
                requirement_index=payload.requirement_index,
                company_swipe_id=payload.company_swipe_id,
                swipe_image_url=payload.swipe_image_url,
                swipe_requires_product_image=payload.swipe_requires_product_image,
                model=payload.model,
                render_model_id=payload.render_model_id,
                max_output_tokens=payload.max_output_tokens,
                aspect_ratio=payload.aspect_ratio,
                count=payload.count,
                workflow_run_id=str(run.id),
            ),
            id=temporal_workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:  # noqa: BLE001
        session.delete(run)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to start swipe image ad workflow.",
        ) from exc

    run.temporal_run_id = handle.first_execution_run_id
    session.commit()

    WorkflowsRepository(session).log_activity(
        workflow_run_id=str(run.id),
        step="swipe_image_ad",
        status="started",
        payload_in=payload.model_dump(mode="json"),
    )

    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}


@router.get("/company")
def list_company_swipes(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    repo = CompanySwipesRepository(session)
    assets = repo.list_assets(org_id=auth.org_id, limit=500, offset=0)
    media_map = repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=[str(asset.id) for asset in assets])
    return jsonable_encoder([_serialize_asset(asset, media_map) for asset in assets])


@router.get("/client/{client_id}")
def list_client_swipes(
    client_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    repo = ClientSwipesRepository(session)
    return jsonable_encoder(repo.list(org_id=auth.org_id, client_id=client_id))


@router.get("/collections")
def list_swipe_collections(
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    repo = SwipeCollectionsRepository(session)
    collections = repo.list(org_id=auth.org_id)
    item_counts = repo.item_counts(org_id=auth.org_id)
    return jsonable_encoder(
        [
            _serialize_collection(
                collection=collection,
                item_count=item_counts.get(str(collection.id), 0),
                analysis_counts=repo.analysis_counts(org_id=auth.org_id, collection_id=str(collection.id)),
            )
            for collection in collections
        ]
    )


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_swipe_collection(
    payload: SwipeCollectionCreateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    repo = SwipeCollectionsRepository(session)
    collection = repo.create(
        org_id=auth.org_id,
        name=payload.name,
        kind=payload.kind,
        created_by_user_id=auth.user_id,
    )
    return jsonable_encoder(
        _serialize_collection(collection=collection, item_count=0, analysis_counts={})
    )


@router.get("/collections/{collection_id}")
def get_swipe_collection(
    collection_id: str,
    limit: int = 200,
    offset: int = 0,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    collections_repo = SwipeCollectionsRepository(session)
    collection = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe collection not found")
    company_repo = CompanySwipesRepository(session)
    assets = company_repo.list_assets(
        org_id=auth.org_id,
        limit=limit,
        offset=offset,
        collection_id=collection_id,
    )
    media_map = company_repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=[str(asset.id) for asset in assets])
    detail = SwipeCollectionDetailModel.model_validate(
        {
            **_serialize_collection(
                collection=collection,
                item_count=collections_repo.item_count(org_id=auth.org_id, collection_id=collection_id),
                analysis_counts=collections_repo.analysis_counts(org_id=auth.org_id, collection_id=collection_id),
            ).model_dump(mode="json"),
            "swipes": [_serialize_asset(asset, media_map).model_dump(mode="json") for asset in assets],
        }
    )
    return jsonable_encoder(detail)


@router.post("/collections/{collection_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_swipe_collection(
    collection_id: str,
    payload: SwipeCollectionCloneRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    repo = SwipeCollectionsRepository(session)
    try:
        collection = repo.clone(
            org_id=auth.org_id,
            source_collection_id=collection_id,
            name=payload.name,
            created_by_user_id=auth.user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return jsonable_encoder(
        _serialize_collection(
            collection=collection,
            item_count=repo.item_count(org_id=auth.org_id, collection_id=str(collection.id)),
            analysis_counts=repo.analysis_counts(org_id=auth.org_id, collection_id=str(collection.id)),
        )
    )


@router.post("/collections/{collection_id}/items", status_code=status.HTTP_201_CREATED)
def add_swipes_to_collection(
    collection_id: str,
    payload: SwipeCollectionItemsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    collections_repo = SwipeCollectionsRepository(session)
    collection = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe collection not found")
    if collection.kind not in WRITABLE_SWIPE_COLLECTION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Default swipe collection is read-only. Clone it before modifying it.",
        )
    company_repo = CompanySwipesRepository(session)
    missing_ids = [
        swipe_asset_id
        for swipe_asset_id in payload.swipe_asset_ids
        if company_repo.get_asset(org_id=auth.org_id, swipe_id=swipe_asset_id) is None
    ]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Some swipe assets were not found.", "missingSwipeAssetIds": missing_ids},
        )
    collections_repo.add_items(
        org_id=auth.org_id,
        collection_id=collection_id,
        swipe_asset_ids=payload.swipe_asset_ids,
    )
    refreshed = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    return jsonable_encoder(
        _serialize_collection(
            collection=refreshed,
            item_count=collections_repo.item_count(org_id=auth.org_id, collection_id=collection_id),
            analysis_counts=collections_repo.analysis_counts(org_id=auth.org_id, collection_id=collection_id),
        )
    )


@router.delete("/collections/{collection_id}/items/{swipe_asset_id}")
def remove_swipe_from_collection(
    collection_id: str,
    swipe_asset_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    collections_repo = SwipeCollectionsRepository(session)
    collection = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe collection not found")
    if collection.kind not in WRITABLE_SWIPE_COLLECTION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Default swipe collection is read-only. Clone it before modifying it.",
        )
    removed = collections_repo.remove_item(
        org_id=auth.org_id,
        collection_id=collection_id,
        swipe_asset_id=swipe_asset_id,
    )
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe asset is not in this collection")
    refreshed = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    return jsonable_encoder(
        _serialize_collection(
            collection=refreshed,
            item_count=collections_repo.item_count(org_id=auth.org_id, collection_id=collection_id),
            analysis_counts=collections_repo.analysis_counts(org_id=auth.org_id, collection_id=collection_id),
        )
    )


@router.post("/collections/{collection_id}/uploads", status_code=status.HTTP_201_CREATED)
async def upload_swipes_to_collection(
    collection_id: str,
    files: list[UploadFile] = File(...),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one file is required.")
    if not str(settings.SWIPE_TAXONOMY_MODEL or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SWIPE_TAXONOMY_MODEL must be configured before uploading swipe assets.",
        )

    collections_repo = SwipeCollectionsRepository(session)
    collection = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe collection not found")
    if collection.kind not in WRITABLE_SWIPE_COLLECTION_KINDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Default swipe collection is read-only. Clone it before uploading into it.",
        )

    uploads: list[tuple[UploadFile, bytes, str]] = []
    for file in files:
        content_type = _resolve_swipe_upload_content_type_or_400(file)
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename or 'upload'} is empty.",
            )
        if len(content) > _SWIPE_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File {file.filename or 'upload'} exceeds {_SWIPE_UPLOAD_MAX_BYTES} bytes.",
            )
        uploads.append((file, content, content_type))

    company_repo = CompanySwipesRepository(session)
    created_asset_ids: list[str] = []
    for file, content, content_type in uploads:
        stored = _store_swipe_upload_media(
            content_bytes=content,
            filename=file.filename,
            content_type=content_type,
        )
        asset = company_repo.create_asset(
            org_id=auth.org_id,
            source_kind="upload",
            origin_system="manual_upload",
            title=(file.filename or "Upload").strip() or "Upload",
            analysis_status="queued",
            analysis_model=str(settings.SWIPE_TAXONOMY_MODEL or "").strip() or None,
            analysis_updated_at=datetime.now(timezone.utc),
            ad_unit_format=_infer_swipe_ad_unit_format(content_type),
            placement_shape=_infer_swipe_placement_shape(stored.width, stored.height),
        )
        company_repo.create_media(
            org_id=auth.org_id,
            swipe_asset_id=str(asset.id),
            path=stored.storage_key,
            type="image",
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
        )
        session.add(
            SwipeCollectionItem(
                org_id=auth.org_id,
                collection_id=collection.id,
                swipe_asset_id=asset.id,
            )
        )
        created_asset_ids.append(str(asset.id))

    session.commit()

    temporal = await get_temporal_client()
    failed_to_start: list[str] = []
    for swipe_asset_id in created_asset_ids:
        try:
            await _start_swipe_taxonomy_analysis(
                swipe_asset_id=swipe_asset_id,
                auth=auth,
                temporal=temporal,
            )
        except Exception as exc:  # noqa: BLE001
            failed_to_start.append(swipe_asset_id)
            company_repo.update_asset(
                org_id=auth.org_id,
                swipe_id=swipe_asset_id,
                analysis_status="failed",
                analysis_error=f"Failed to start swipe taxonomy workflow: {exc}",
                analysis_updated_at=datetime.now(timezone.utc),
            )
            session.commit()

    assets = [company_repo.get_asset(org_id=auth.org_id, swipe_id=swipe_asset_id) for swipe_asset_id in created_asset_ids]
    serialized_assets = []
    media_map = company_repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=created_asset_ids)
    for asset in assets:
        if asset is None:
            continue
        serialized_assets.append(_serialize_asset(asset, media_map))

    response = SwipeCollectionUploadResponse(
        collection_id=collection_id,
        created_swipes=serialized_assets,
    )
    return jsonable_encoder(response)


@router.get("")
def list_swipes(
    collection_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    collections_repo = SwipeCollectionsRepository(session)
    if collection_id:
        collection = collections_repo.get(org_id=auth.org_id, collection_id=collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe collection not found")
    company_repo = CompanySwipesRepository(session)
    assets = company_repo.list_assets(
        org_id=auth.org_id,
        limit=limit,
        offset=offset,
        collection_id=collection_id,
    )
    media_map = company_repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=[str(asset.id) for asset in assets])
    return jsonable_encoder([_serialize_asset(asset, media_map) for asset in assets])


@router.post("/generate-image-ad")
async def generate_image_ad_from_swipe(
    payload: SwipeImageAdGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Start a Temporal workflow that:
      - Generates a generation-ready image prompt from a competitor swipe image
        (Gemini vision + Gemini File Search workspace context)
      - Renders the final image(s) via the MOS-embedded Freestyle renderer
      - Persists generated assets attached to the provided asset brief
    """
    return await _start_swipe_image_ad_run(payload=payload, auth=auth, session=session)


@router.post(
    "/generate-template-testimonials",
    response_model=SwipeTemplateTestimonialsGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_template_testimonials(
    payload: SwipeTemplateTestimonialsGenerateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    campaign = session.scalars(
        select(Campaign).where(
            Campaign.org_id == auth.org_id,
            Campaign.id == payload.campaign_id,
        )
    ).first()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign must have a product before generating swipe template testimonials.",
        )

    brief_map = load_campaign_asset_brief_map(
        org_id=auth.org_id,
        client_id=str(campaign.client_id),
        campaign_id=payload.campaign_id,
        session=session,
    )
    brief = brief_map.get(payload.asset_brief_id)
    if not isinstance(brief, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset brief not found")

    requirement_index = _resolve_single_image_requirement_index(brief)
    template_paths = _collect_template_image_paths()
    public_asset_base_url = _require_public_asset_base_url()
    temporal = await get_temporal_client()
    brief_funnel_id = clean_optional_text(brief.get("funnelId"))

    template_runs: list[dict[str, str]] = []
    for template_path in template_paths:
        content_bytes = template_path.read_bytes()
        if not content_bytes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image is empty: {template_path.name}",
            )
        content_type = mimetypes.guess_type(template_path.name)[0] or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Swipe template image has unsupported content type: {template_path.name}",
            )

        staged_asset = create_funnel_upload_asset(
            session=session,
            org_id=auth.org_id,
            client_id=str(campaign.client_id),
            content_bytes=content_bytes,
            filename=template_path.name,
            content_type=content_type,
            usage_context={
                "kind": "swipe_template_source",
                "campaignId": payload.campaign_id,
                "assetBriefId": payload.asset_brief_id,
                "templateFile": template_path.relative_to(_TEMPLATE_IMAGES_DIR).as_posix(),
            },
            funnel_id=brief_funnel_id,
            product_id=str(campaign.product_id),
            tags=["swipe", "swipe_template_source"],
        )
        staged_public_id = str(staged_asset.public_id)
        staged_public_url = f"{public_asset_base_url}/public/assets/{staged_public_id}"

        workflow_payload = SwipeImageAdGenerateRequest(
            clientId=str(campaign.client_id),
            productId=str(campaign.product_id),
            campaignId=payload.campaign_id,
            assetBriefId=payload.asset_brief_id,
            requirementIndex=requirement_index,
            swipeImageUrl=staged_public_url,
            aspectRatio=payload.aspect_ratio,
            count=1,
            model=payload.model,
            renderModelId=payload.render_model_id,
            maxOutputTokens=payload.max_output_tokens,
        )
        started = await _start_swipe_image_ad_run(
            payload=workflow_payload,
            auth=auth,
            session=session,
            temporal=temporal,
        )
        template_runs.append(
            {
                "templateFile": template_path.relative_to(_TEMPLATE_IMAGES_DIR).as_posix(),
                "templateLabel": template_path.stem,
                "stagedAssetId": str(staged_asset.id),
                "stagedPublicId": staged_public_id,
                "stagedPublicUrl": staged_public_url,
                "workflowRunId": started["workflow_run_id"],
                "temporalWorkflowId": started["temporal_workflow_id"],
            }
        )

    return {
        "campaignId": payload.campaign_id,
        "assetBriefId": payload.asset_brief_id,
        "clientId": str(campaign.client_id),
        "productId": str(campaign.product_id),
        "requirementIndex": requirement_index,
        "templateRuns": template_runs,
    }


@router.get("/{swipe_id}")
def get_swipe(
    swipe_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    repo = CompanySwipesRepository(session)
    asset = repo.get_asset(org_id=auth.org_id, swipe_id=swipe_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe asset not found")
    media_map = repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=[swipe_id])
    return jsonable_encoder(_serialize_asset(asset, media_map))


@router.patch("/{swipe_id}")
def update_swipe(
    swipe_id: str,
    payload: SwipeAssetUpdateRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    repo = CompanySwipesRepository(session)
    fields = payload.model_dump(exclude_unset=True)
    asset = repo.update_asset(org_id=auth.org_id, swipe_id=swipe_id, **fields)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swipe asset not found")
    asset.analysis_updated_at = datetime.now(timezone.utc)
    session.commit()
    media_map = repo.list_media_for_assets(org_id=auth.org_id, swipe_asset_ids=[swipe_id])
    return jsonable_encoder(_serialize_asset(asset, media_map))
