import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from video import normalize_video_data_url_for_llm

router = APIRouter()


class PrepareVideoRequest(BaseModel):
    videoDataUrl: str


class PrepareVideoResponse(BaseModel):
    videoDataUrl: str


@router.post("/prepare-video", response_model=PrepareVideoResponse)
async def prepare_video(request: PrepareVideoRequest) -> PrepareVideoResponse:
    try:
        normalized_video_data_url = await asyncio.to_thread(
            normalize_video_data_url_for_llm,
            request.videoDataUrl,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Video preprocessing failed: {exc}",
        ) from exc

    return PrepareVideoResponse(videoDataUrl=normalized_video_data_url)
