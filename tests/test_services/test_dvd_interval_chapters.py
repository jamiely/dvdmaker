"""Automatic interval chapter and source-menu navigation tests."""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.models.dvd import DVDStructure
from src.models.video import VideoMetadata
from src.services.converter import ConvertedVideoFile
from src.services.dvd_author import (
    DVDAuthor,
    format_chapter_timestamp,
    generate_chapter_offsets,
)


@pytest.mark.parametrize(
    "duration,interval,expected",
    [
        (0, 10, (0,)),
        (600, 10, (0,)),
        (601, 10, (0, 600)),
        (1800, 10, (0, 600, 1200)),
        (1801, 10, (0, 600, 1200, 1800)),
        (9999, None, (0,)),
    ],
)
def test_independent_chapter_boundaries(duration, interval, expected):
    assert generate_chapter_offsets(duration, interval) == expected


def test_multi_hour_chapter_formatting():
    assert format_chapter_timestamp(0) == "0:00:00"
    assert format_chapter_timestamp(3661) == "1:01:01"
    assert format_chapter_timestamp(12 * 3600 + 5) == "12:00:05"


def _author(tmp_path, interval=10, autoplay=True, video_format="NTSC"):
    settings = Settings(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        temp_dir=tmp_path / "temp",
        bin_dir=tmp_path / "bin",
        log_dir=tmp_path / "logs",
        use_system_tools=True,
        download_tools=False,
        chapter_interval_minutes=interval,
        autoplay=autoplay,
        video_format=video_format,
    )
    cache = Mock()
    cache.cache_dir = settings.cache_dir
    return DVDAuthor(settings, Mock(), cache)


def _converted(tmp_path, index, duration):
    media = tmp_path / f"source & {index}.mpg"
    media.write_bytes(f"source {index}".encode())
    metadata = VideoMetadata(
        f"id-{index}", f"Title & {index}", duration, media.resolve().as_uri()
    )
    return ConvertedVideoFile(
        metadata,
        media,
        file_size=media.stat().st_size,
        checksum=f"checksum-{index}",
        duration=duration,
        resolution="720x480",
        video_codec="mpeg2video",
        audio_codec="ac3",
    )


def test_per_source_offsets_vob_count_and_cumulative_menu_targets(tmp_path):
    author = _author(tmp_path, interval=10)
    videos = [_converted(tmp_path, 1, 1201), _converted(tmp_path, 2, 601)]
    chapters = author._create_chapters(videos)
    structure = DVDStructure(
        chapters, "A & B", sum(video.file_size for video in videos)
    )
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()

    with patch.object(author, "_create_menu_video"):
        xml_file = author._create_dvd_xml(structure, video_ts)

    root = ET.parse(xml_file).getroot()
    vobs = root.findall("./titleset/titles/pgc/vob")
    assert len(vobs) == 2
    assert vobs[0].attrib["chapters"] == "0:00:00,0:10:00,0:20:00"
    assert vobs[1].attrib["chapters"] == "0:00:00,0:10:00"
    buttons = root.findall("./titleset/menus/pgc/button")
    assert buttons[0].text == "g0=0;jump title 1;"
    # Source two begins after source one's three global chapter markers.
    assert buttons[1].text == "g0=0;jump title 1 chapter 4;"
    assert "&amp;" in xml_file.read_text(encoding="utf-8")


def test_disabled_interval_preserves_legacy_marker_and_autoplay_no_iso_is_unrelated(
    tmp_path,
):
    author = _author(tmp_path, interval=None, autoplay=False, video_format="PAL")
    videos = [_converted(tmp_path, 1, 3600)]
    structure = DVDStructure(
        author._create_chapters(videos), "PAL", videos[0].file_size
    )
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    with patch.object(author, "_create_menu_video"):
        xml_file = author._create_dvd_xml(structure, video_ts)
    root = ET.parse(xml_file).getroot()
    assert root.find("./titleset/titles/pgc/vob").attrib["chapters"] == "0:00"
    assert "jumppad" not in root.attrib
    assert root.find("./titleset/titles/video").attrib["format"] == "pal"


def test_visual_source_menu_stays_limited_to_six_sources(tmp_path):
    author = _author(tmp_path, interval=1)
    videos = [_converted(tmp_path, index, 121) for index in range(1, 8)]
    structure = DVDStructure(
        author._create_chapters(videos),
        "Seven",
        sum(video.file_size for video in videos),
    )
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    with patch.object(author, "_create_menu_video"):
        xml_file = author._create_dvd_xml(structure, video_ts)
    root = ET.parse(xml_file).getroot()
    buttons = root.findall("./titleset/menus/pgc/button")
    # Six source buttons plus the existing return-to-main-menu button.
    assert len(buttons) == 7
