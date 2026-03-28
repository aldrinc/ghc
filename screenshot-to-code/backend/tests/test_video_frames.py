from pathlib import Path

from video.frames import extract_representative_video_frames


def test_extract_representative_video_frames_returns_timestamped_images(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "video.frames.get_video_bytes_and_mime_type",
        lambda _video_data_url: (b"video-bytes", "video/mp4"),
    )
    monkeypatch.setattr(
        "video.frames.get_video_duration_from_bytes",
        lambda _video_bytes: 20.0,
    )

    def fake_run_ffmpeg_extract_frame(input_path: Path, output_path: Path, timestamp_seconds: float) -> None:
        assert input_path.exists()
        output_path.write_bytes(f"frame-{timestamp_seconds}".encode("utf-8"))

    monkeypatch.setattr(
        "video.frames._run_ffmpeg_extract_frame",
        fake_run_ffmpeg_extract_frame,
    )

    frames = extract_representative_video_frames("data:video/mp4;base64,abc", max_frames=3)

    assert len(frames) == 3
    assert frames[0][0] == 2.0
    assert frames[0][1].startswith("data:image/png;base64,")


def test_extract_representative_video_frames_returns_empty_when_duration_unknown(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "video.frames.get_video_bytes_and_mime_type",
        lambda _video_data_url: (b"video-bytes", "video/mp4"),
    )
    monkeypatch.setattr(
        "video.frames.get_video_duration_from_bytes",
        lambda _video_bytes: None,
    )

    frames = extract_representative_video_frames("data:video/mp4;base64,abc")

    assert frames == []
