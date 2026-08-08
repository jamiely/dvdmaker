"""Conversion profile, compatibility reuse, and cache identity tests."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.models.video import VideoFile, VideoMetadata
from src.services.converter import ConvertedVideoFile, VideoConverter


@pytest.fixture
def converter(tmp_path):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        temp_dir=tmp_path / "temp",
        bin_dir=tmp_path / "bin",
        log_dir=tmp_path / "logs",
        use_system_tools=True,
        download_tools=False,
    )
    tools = Mock()
    tools.get_tool_command.return_value = ["ffmpeg"]
    return VideoConverter(settings, tools, Mock())


def _source(tmp_path, checksum="source-checksum"):
    path = tmp_path / "source.mp4"
    path.write_bytes(b"source")
    metadata = VideoMetadata("source-id", "Source", 180, path.resolve().as_uri())
    return VideoFile(metadata, path, path.stat().st_size, checksum, "mp4")


def _info(
    *,
    format_name="mpeg",
    codec="mpeg2video",
    pix_fmt="yuv420p",
    size=(720, 480),
    rate="30000/1001",
    aspect="16:9",
    audio="ac3",
    sample_rate="48000",
    duration="180.0",
):
    return {
        "format": {"format_name": format_name, "duration": duration},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": codec,
                "pix_fmt": pix_fmt,
                "width": size[0],
                "height": size[1],
                "avg_frame_rate": rate,
                "display_aspect_ratio": aspect,
            },
            {
                "codec_type": "audio",
                "codec_name": audio,
                "sample_rate": sample_rate,
            },
        ],
    }


@pytest.mark.parametrize(
    "video_format,aspect,car,gop,sar,vbit,abit,rate",
    [
        ("NTSC", "16:9", True, "12", "32/27", "3500k", "192k", "30000/1001"),
        ("NTSC", "4:3", False, "18", "8/9", "6000k", "448k", "30000/1001"),
        ("PAL", "16:9", False, "15", "64/45", "6000k", "448k", "25"),
        ("PAL", "4:3", True, "12", "16/15", "3500k", "192k", "25"),
    ],
)
def test_ffmpeg_profile(
    converter, tmp_path, video_format, aspect, car, gop, sar, vbit, abit, rate
):
    converter.settings.video_format = video_format
    converter.settings.aspect_ratio = aspect
    converter.settings.car_dvd_compatibility = car
    resolution = "720x480" if video_format == "NTSC" else "720x576"

    command = converter._build_conversion_command(
        tmp_path / "in.mkv", tmp_path / "out.mpg", resolution, rate
    )
    joined = " ".join(command)

    assert "-map 0:v:0 -map 0:a:0 -sn -dn" in joined
    assert "-fflags +genpts" in joined
    assert "-avoid_negative_ts make_zero" in joined
    assert "bwdif=mode=send_frame:parity=auto:deint=interlaced" in joined
    assert "force_original_aspect_ratio=decrease" in joined
    assert f"setsar={sar}" in joined
    assert command[command.index("-r") + 1] == rate
    assert command[command.index("-g") + 1] == gop
    assert command[command.index("-b:v") + 1] == vbit
    assert command[command.index("-b:a") + 1] == abit
    assert "aresample=async=1:first_pts=0" in command
    assert "-muxrate" in command and "-packetsize" in command


def test_dvd_compatible_source_requires_every_stream_property(converter):
    assert converter._is_dvd_compatible(_info())
    for changed in [
        {"format_name": "mpegts"},
        {"codec": "h264"},
        {"pix_fmt": "yuv422p"},
        {"size": (704, 480)},
        {"rate": "25/1"},
        {"aspect": "4:3"},
        {"audio": "mp2"},
        {"sample_rate": "44100"},
        {"duration": "0"},
    ]:
        assert not converter._is_dvd_compatible(_info(**changed))


def test_compatible_source_is_reused_but_thumbnail_and_metadata_are_generated(
    converter, tmp_path
):
    source = _source(tmp_path)

    def create_output(command, *_args):
        Path(command[-1]).write_bytes(b"thumbnail")

    with (
        patch.object(converter, "_get_video_info", side_effect=[_info(), _info()]),
        patch.object(
            converter, "_run_conversion_command", side_effect=create_output
        ) as run,
    ):
        converted = converter.convert_video(source)

    assert converted.video_file == source.file_path
    assert converted.reused_source is True
    assert converted.thumbnail_file.exists()
    assert run.call_count == 1
    assert run.call_args.args[1].startswith("Generating thumbnail")
    cached = converter._load_converted_metadata()[source.metadata.video_id]
    assert cached["source_checksum"] == source.checksum
    assert cached["profile_fingerprint"] == converter._conversion_profile_fingerprint()


def test_incompatible_source_runs_conversion_and_thumbnail(converter, tmp_path):
    source = _source(tmp_path)
    output_info = _info()

    def create_output(command, *_args):
        Path(command[-1]).write_bytes(b"generated")

    with (
        patch.object(
            converter,
            "_get_video_info",
            side_effect=[_info(format_name="mov"), output_info],
        ),
        patch.object(
            converter, "_run_conversion_command", side_effect=create_output
        ) as run,
    ):
        converted = converter.convert_video(source)

    assert converted.video_file != source.file_path
    assert converted.reused_source is False
    assert run.call_count == 2


def test_source_and_profile_fingerprint_invalidate_cache_but_titles_and_chapters_do_not(
    converter, tmp_path
):
    source = _source(tmp_path)
    converted_path = tmp_path / "cached.mpg"
    converted_path.write_bytes(b"cached")
    current_fingerprint = converter._conversion_profile_fingerprint()
    converted = ConvertedVideoFile(
        source.metadata,
        converted_path,
        file_size=converted_path.stat().st_size,
        checksum="converted",
        duration=180,
        resolution="720x480",
        video_codec="mpeg2video",
        audio_codec="ac3",
        source_checksum=source.checksum,
        profile_fingerprint=current_fingerprint,
    )
    converter._save_converted_metadata({source.metadata.video_id: converted.to_dict()})

    assert converter.is_video_converted(source.metadata, source.checksum)
    assert not converter.is_video_converted(source.metadata, "different-source")
    converter.settings.menu_title = "Renamed"
    converter.settings.chapter_interval_minutes = 20
    assert converter._conversion_profile_fingerprint() == current_fingerprint
    assert converter.is_video_converted(source.metadata, source.checksum)
    converter.settings.aspect_ratio = "4:3"
    assert not converter.is_video_converted(source.metadata, source.checksum)


def test_legacy_cache_entry_is_stale_for_real_conversion_lookup(converter, tmp_path):
    source = _source(tmp_path)
    cached = tmp_path / "legacy.mpg"
    cached.write_bytes(b"legacy")
    converter._save_converted_metadata(
        {
            source.metadata.video_id: {
                "video_id": source.metadata.video_id,
                "video_file": str(cached),
                "thumbnail_file": None,
                "file_size": cached.stat().st_size,
                "checksum": "old",
                "duration": 180,
                "resolution": "720x480",
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
            }
        }
    )
    assert not converter.is_video_converted(source.metadata, source.checksum)
