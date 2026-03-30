import base64
import mimetypes
import subprocess
import tempfile
from pathlib import Path

from video.cost_estimation import get_video_duration_from_bytes
from video.utils import get_video_bytes_and_mime_type


def extract_representative_video_frames(
    video_data_url: str, *, max_frames: int = 4
) -> list[tuple[float, str]]:
    video_bytes, mime_type = get_video_bytes_and_mime_type(video_data_url)
    duration_seconds = get_video_duration_from_bytes(video_bytes)
    if duration_seconds is None or duration_seconds <= 0:
        return []

    input_suffix = mimetypes.guess_extension(mime_type) or ".mp4"
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        input_path = temp_dir / f"input{input_suffix}"
        input_path.write_bytes(video_bytes)

        extracted_frames: list[tuple[float, str]] = []
        for frame_index, timestamp_seconds in enumerate(
            _sample_video_timestamps(duration_seconds, max_frames),
            start=1,
        ):
            output_path = temp_dir / f"frame-{frame_index}.png"
            _run_ffmpeg_extract_frame(input_path, output_path, timestamp_seconds)
            if not output_path.exists():
                continue
            extracted_frames.append(
                (timestamp_seconds, _image_file_to_data_url(output_path))
            )

        return extracted_frames


def _sample_video_timestamps(duration_seconds: float, max_frames: int) -> list[float]:
    if max_frames <= 0:
        return []
    if duration_seconds <= 0.6:
        return [0.0]

    sample_count = min(max_frames, 4)
    fractions = {
        1: [0.15],
        2: [0.15, 0.75],
        3: [0.1, 0.45, 0.8],
        4: [0.08, 0.32, 0.6, 0.88],
    }[sample_count]

    max_timestamp = max(duration_seconds - 0.05, 0.0)
    timestamps = [round(min(duration_seconds * fraction, max_timestamp), 3) for fraction in fractions]

    deduped: list[float] = []
    for timestamp in timestamps:
        if timestamp not in deduped:
            deduped.append(timestamp)
    return deduped


def _run_ffmpeg_extract_frame(
    input_path: Path, output_path: Path, timestamp_seconds: float
) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp_seconds:.3f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _image_file_to_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
