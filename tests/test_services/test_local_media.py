"""Tests for local input discovery, validation, and title inference."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.models.video import VideoFile, VideoMetadata
from src.services.local_media import (
    LocalMediaError,
    LocalTitleInferrer,
    build_local_video_files,
    expand_local_inputs,
    load_local_media,
)


def _video(path: Path, checksum: str = "a" * 64) -> VideoFile:
    path.write_bytes(b"media")
    return VideoFile(
        metadata=VideoMetadata(checksum, path.stem, 60, path.resolve().as_uri()),
        file_path=path.resolve(),
        file_size=5,
        checksum=checksum,
        format=path.suffix.lstrip("."),
    )


def _probe_result(duration: str = "60.25") -> Mock:
    result = Mock(returncode=0, stderr="")
    result.stdout = json.dumps(
        {
            "format": {"duration": duration, "format_name": "mov,mp4"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    return result


def test_expand_inputs_in_place_natural_case_insensitive_and_deduplicated(
    tmp_path, caplog
):
    directory = tmp_path / "series"
    directory.mkdir()
    for name in ["Episode10.MP4", "episode2.mp4", "episode1.Mkv", "ignore.txt"]:
        (directory / name).write_bytes(b"x")
    leading = tmp_path / "leading.mov"
    trailing = tmp_path / "trailing.avi"
    leading.write_bytes(b"x")
    trailing.write_bytes(b"x")

    result = expand_local_inputs(
        [leading, directory, directory / "episode2.mp4", trailing]
    )

    assert [path.name for path in result] == [
        "leading.mov",
        "episode1.Mkv",
        "episode2.mp4",
        "Episode10.MP4",
        "trailing.avi",
    ]
    assert "duplicate local input" in caplog.text.lower()


@pytest.mark.parametrize("name", ["missing.mp4", "empty"])
def test_expand_inputs_rejects_missing_and_empty_directory(tmp_path, name):
    path = tmp_path / name
    if name == "empty":
        path.mkdir()
    with pytest.raises(LocalMediaError):
        expand_local_inputs([path])


def test_explicit_unknown_extension_is_retained_for_probe(tmp_path):
    media = tmp_path / "video.custom"
    media.write_bytes(b"x")
    assert expand_local_inputs([media]) == [media.resolve()]


@patch("src.services.local_media.subprocess.run", return_value=_probe_result())
def test_build_local_video_metadata_uses_content_identity(mock_run, tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"same bytes")
    tools = Mock()
    tools.get_tool_command.return_value = ["/opt/bin/ffmpeg"]

    video = build_local_video_files([media.resolve()], tools)[0]

    assert video.metadata.video_id == video.checksum
    assert len(video.checksum) == 64
    assert video.metadata.duration == 60
    assert video.metadata.url == media.resolve().as_uri()
    assert video.stream_details["streams"][0]["codec_type"] == "video"
    assert mock_run.call_args.args[0][0] == "/opt/bin/ffprobe"


@pytest.mark.parametrize(
    "streams,error",
    [
        ([{"codec_type": "audio"}], "no video stream"),
        ([{"codec_type": "video"}], "no audio stream"),
    ],
)
def test_local_probe_requires_video_and_audio(tmp_path, streams, error):
    media = tmp_path / "bad.mp4"
    media.write_bytes(b"bad")
    result = Mock(
        returncode=0,
        stderr="",
        stdout=json.dumps({"format": {"duration": "1"}, "streams": streams}),
    )
    tools = Mock()
    tools.get_tool_command.return_value = ["ffmpeg"]
    with patch("src.services.local_media.subprocess.run", return_value=result):
        with pytest.raises(LocalMediaError, match=error):
            build_local_video_files([media.resolve()], tools)


def test_title_inference_exact_command_basename_prompt_and_cache(tmp_path):
    media = tmp_path / "private" / "Movie.1080p.WEB-DL.mp4"
    media.parent.mkdir()
    video = _video(media)
    completed = Mock(
        returncode=0,
        stderr="",
        stdout=json.dumps({"titles": [{"index": 0, "title": "Movie"}]}),
    )
    inferrer = LocalTitleInferrer(tmp_path / "cache")

    with (
        patch("src.services.local_media.shutil.which", return_value="/bin/codex"),
        patch("src.services.local_media.subprocess.run", return_value=completed) as run,
    ):
        assert inferrer.infer([video]) == ["Movie"]

    command = run.call_args.args[0]
    assert command[:7] == [
        "/bin/codex",
        "exec",
        "--model",
        "gpt-5.6-luna",
        "--sandbox",
        "read-only",
        "--ephemeral",
    ]
    assert "--cd" in command
    assert "--output-schema" in command
    assert command[-1] == "-"
    assert run.call_args.kwargs["timeout"] == 120
    prompt = run.call_args.kwargs["input"]
    assert media.name in prompt
    assert str(media.parent) not in prompt

    with patch("src.services.local_media.subprocess.run") as second_run:
        assert inferrer.infer([video]) == ["Movie"]
    second_run.assert_not_called()


@pytest.mark.parametrize(
    "completed",
    [
        Mock(returncode=1, stderr="auth failed", stdout=""),
        Mock(returncode=0, stderr="", stdout="not json"),
        Mock(returncode=0, stderr="", stdout='{"titles": []}'),
        Mock(
            returncode=0,
            stderr="",
            stdout='{"titles": [{"index": 1, "title": "Wrong"}]}',
        ),
    ],
)
def test_title_inference_warns_once_and_falls_back(tmp_path, caplog, completed):
    video = _video(tmp_path / "Fallback.Name.mp4")
    with (
        patch("src.services.local_media.shutil.which", return_value="codex"),
        patch("src.services.local_media.subprocess.run", return_value=completed),
    ):
        assert LocalTitleInferrer(tmp_path / "cache").infer([video]) == [
            "Fallback.Name"
        ]
    assert caplog.text.lower().count("could not infer local video titles") == 1


def test_title_inference_timeout_and_opt_out(tmp_path, caplog):
    video = _video(tmp_path / "No_AI.mkv")
    inferrer = LocalTitleInferrer(tmp_path / "cache")
    with (
        patch("src.services.local_media.shutil.which", return_value="codex"),
        patch(
            "src.services.local_media.subprocess.run",
            side_effect=subprocess.TimeoutExpired("codex", 120),
        ),
    ):
        assert inferrer.infer([video]) == ["No_AI"]
    with patch("src.services.local_media.subprocess.run") as run:
        assert inferrer.infer([video], enabled=False) == ["No_AI"]
    run.assert_not_called()
    assert caplog.text.lower().count("could not infer local video titles") == 1


def test_title_inference_missing_cli_falls_back(tmp_path, caplog):
    video = _video(tmp_path / "No Codex.mp4")
    with (
        patch("src.services.local_media.shutil.which", return_value=None),
        patch("src.services.local_media.subprocess.run") as run,
    ):
        assert LocalTitleInferrer(tmp_path / "cache").infer([video]) == ["No Codex"]
    run.assert_not_called()
    assert caplog.text.lower().count("could not infer local video titles") == 1


@patch("src.services.local_media.LocalTitleInferrer.infer")
@patch("src.services.local_media.build_local_video_files")
def test_default_local_menu_titles(build, infer, tmp_path):
    one = _video(tmp_path / "One.mp4", "1" * 64)
    two = _video(tmp_path / "Two.mp4", "2" * 64)
    build.return_value = [one, two]
    infer.return_value = ["Clean One", "Clean Two"]
    tools = Mock()

    result = load_local_media([tmp_path], tools, tmp_path / "cache")
    assert result.default_menu_title == tmp_path.name

    build.return_value = [one]
    infer.return_value = ["Clean One"]
    result = load_local_media([one.file_path], tools, tmp_path / "cache")
    assert result.default_menu_title == "Clean One"
