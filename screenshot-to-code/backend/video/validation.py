from config import (
    MAX_ACCEPTED_VIDEO_DURATION_SECONDS,
    MAX_ACCEPTED_VIDEO_SIZE_BYTES,
)
from video.cost_estimation import get_video_duration_from_bytes
from video.utils import get_video_bytes_and_mime_type


def validate_video_data_url_limits(video_data_url: str) -> tuple[bytes, str, float]:
    video_bytes, mime_type = get_video_bytes_and_mime_type(video_data_url)
    _validate_video_bytes(video_bytes)

    duration_seconds = get_video_duration_from_bytes(video_bytes)
    if duration_seconds is None:
        raise RuntimeError(
            "Could not determine the uploaded video duration. "
            "Please use an MP4, MOV, or WebM video with readable metadata."
        )

    if duration_seconds > MAX_ACCEPTED_VIDEO_DURATION_SECONDS:
        raise RuntimeError(
            "Uploaded video exceeds the 60-second limit "
            f"({duration_seconds:.2f}s detected)."
        )

    return video_bytes, mime_type, duration_seconds


def _validate_video_bytes(video_bytes: bytes) -> None:
    video_size_bytes = len(video_bytes)
    if video_size_bytes > MAX_ACCEPTED_VIDEO_SIZE_BYTES:
        video_size_mb = video_size_bytes / (1024 * 1024)
        raise RuntimeError(
            "Uploaded video exceeds the 100MB limit "
            f"({video_size_mb:.2f}MB detected)."
        )
