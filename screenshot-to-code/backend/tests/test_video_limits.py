import pytest

from video.preprocess import NORMALIZED_VIDEO_MIME_TYPE, normalize_video_data_url_for_llm
from video.validation import validate_video_data_url_limits


def test_validate_video_data_url_limits_rejects_large_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "video.validation.get_video_bytes_and_mime_type",
        lambda _video_data_url: (b"0" * (100 * 1024 * 1024 + 1), "video/mp4"),
    )

    with pytest.raises(RuntimeError, match="100MB limit"):
        validate_video_data_url_limits("data:video/mp4;base64,abc")


def test_validate_video_data_url_limits_rejects_long_videos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "video.validation.get_video_bytes_and_mime_type",
        lambda _video_data_url: (b"1234", "video/mp4"),
    )
    monkeypatch.setattr(
        "video.validation.get_video_duration_from_bytes",
        lambda _video_bytes: 61.0,
    )

    with pytest.raises(RuntimeError, match="60-second limit"):
        validate_video_data_url_limits("data:video/mp4;base64,abc")


def test_validate_video_data_url_limits_rejects_unknown_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "video.validation.get_video_bytes_and_mime_type",
        lambda _video_data_url: (b"1234", "video/mp4"),
    )
    monkeypatch.setattr(
        "video.validation.get_video_duration_from_bytes",
        lambda _video_bytes: None,
    )

    with pytest.raises(RuntimeError, match="Could not determine"):
        validate_video_data_url_limits("data:video/mp4;base64,abc")


def test_normalize_video_data_url_for_llm_accepts_valid_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "video.preprocess.validate_video_data_url_limits",
        lambda _video_data_url: (b"input-video", "video/mp4", 12.5),
    )

    def fake_run_ffmpeg(_input_path, output_path) -> None:
        output_path.write_bytes(b"normalized-video")

    monkeypatch.setattr("video.preprocess._run_ffmpeg", fake_run_ffmpeg)

    normalized_video = normalize_video_data_url_for_llm("data:video/mp4;base64,abc")

    assert normalized_video.startswith(f"data:{NORMALIZED_VIDEO_MIME_TYPE};base64,")
