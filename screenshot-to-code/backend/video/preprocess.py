import base64
import mimetypes
import subprocess
import tempfile
from pathlib import Path

from video.utils import get_video_bytes_and_mime_type

NORMALIZED_VIDEO_MIME_TYPE = "video/mp4"
NORMALIZED_VIDEO_SUFFIX = ".mp4"
NORMALIZED_VIDEO_WIDTH = 640
NORMALIZED_VIDEO_FPS = 6
NORMALIZED_VIDEO_CRF = 32


def normalize_video_data_urls_for_llm(video_data_urls: list[str]) -> list[str]:
    return [normalize_video_data_url_for_llm(video_data_url) for video_data_url in video_data_urls]


def normalize_video_data_url_for_llm(video_data_url: str) -> str:
    video_bytes, mime_type = get_video_bytes_and_mime_type(video_data_url)
    input_suffix = mimetypes.guess_extension(mime_type) or ".bin"

    with tempfile.TemporaryDirectory(prefix="s2c-video-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        input_path = temp_dir / f"input{input_suffix}"
        output_path = temp_dir / f"normalized{NORMALIZED_VIDEO_SUFFIX}"

        input_path.write_bytes(video_bytes)
        _run_ffmpeg(input_path, output_path)

        normalized_bytes = output_path.read_bytes()
        normalized_base64 = base64.b64encode(normalized_bytes).decode("utf-8")
        return f"data:{NORMALIZED_VIDEO_MIME_TYPE};base64,{normalized_base64}"


def _run_ffmpeg(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"fps={NORMALIZED_VIDEO_FPS},scale={NORMALIZED_VIDEO_WIDTH}:-2",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(NORMALIZED_VIDEO_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed while normalizing video for Gemini: "
            + completed.stderr.strip()
        )
