"""Automatic chapters and paginated thumbnail-menu regression tests."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image, ImageChops

from src.config.settings import Settings
from src.models.dvd import DVDStructure
from src.models.video import VideoMetadata
from src.services.converter import ConvertedVideoFile
from src.services.dvd_author import (
    CHAPTER_MENU_MIN_MARKERS,
    DVDAuthor,
    DVDAuthoringError,
    format_chapter_timestamp,
    generate_chapter_offsets,
    minimum_interval_for_program_limit,
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


@pytest.mark.parametrize(
    "duration,expected",
    [
        (600, (0,)),
        (601, (0, 600)),
        (3600, (0, 600, 1200, 1800, 2400, 3000)),
    ],
)
def test_single_video_defaults_to_ten_minute_chapters_when_longer_than_ten_minutes(
    tmp_path, duration, expected
):
    author = _author(tmp_path, interval=None)
    chapters = author._create_chapters([_converted(tmp_path, 1, duration)])
    assert chapters[0].chapter_offsets == expected


def test_automatic_single_video_interval_does_not_apply_to_multiple_sources(tmp_path):
    author = _author(tmp_path, interval=None)
    chapters = author._create_chapters(
        [_converted(tmp_path, 1, 601), _converted(tmp_path, 2, 3600)]
    )
    assert [chapter.chapter_offsets for chapter in chapters] == [(0,), (0,)]


def test_explicit_interval_overrides_single_video_default(tmp_path):
    author = _author(tmp_path, interval=15)
    chapters = author._create_chapters([_converted(tmp_path, 1, 1801)])
    assert chapters[0].chapter_offsets == (0, 900, 1800)


def test_program_limit_suggests_smallest_valid_whole_minute_interval():
    assert minimum_interval_for_program_limit([300 * 60]) == 2
    assert minimum_interval_for_program_limit([60, 60], maximum_programs=1) is None


def _author(
    tmp_path,
    interval=10,
    autoplay=True,
    video_format="NTSC",
    aspect_ratio="16:9",
    menu_subtitle="",
):
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
        aspect_ratio=aspect_ratio,
        menu_subtitle=menu_subtitle,
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


def _structure(author, videos, title="Test"):
    return DVDStructure(
        author._create_chapters(videos),
        title,
        sum(video.file_size for video in videos),
    )


def _xml_without_rendering(author, structure, video_ts):
    def chapter_page(entries, page_number, page_count, *_args, **_kwargs):
        return author._chapter_page_buttons(entries, page_number, page_count)

    with (
        patch.object(author, "_create_menu_video"),
        patch.object(author, "_create_chapter_menu_video", side_effect=chapter_page),
    ):
        return author._create_dvd_xml(structure, video_ts)


def test_flattened_entries_keep_local_offsets_and_global_chapter_numbers(tmp_path):
    author = _author(tmp_path, interval=10)
    structure = _structure(
        author,
        [_converted(tmp_path, 1, 1201), _converted(tmp_path, 2, 601)],
    )
    entries = author._flatten_chapter_menu_entries(structure.chapters)
    assert [entry.chapter_number for entry in entries] == [1, 2, 3, 4, 5]
    assert [entry.source_index for entry in entries] == [1, 1, 1, 2, 2]
    assert [entry.source_offset for entry in entries] == [0, 600, 1200, 0, 600]
    assert [entry.chapter_end for entry in entries] == [600, 1200, 1201, 600, 601]


@pytest.mark.parametrize(
    "duration,expected",
    [(600, False), (601, False), (1201, True)],
)
def test_select_chapter_requires_three_total_markers(tmp_path, duration, expected):
    author = _author(tmp_path, interval=10)
    structure = _structure(author, [_converted(tmp_path, 1, duration)])
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    root = ET.parse(_xml_without_rendering(author, structure, video_ts)).getroot()
    main_buttons = root.findall("./vmgm/menus/pgc/button")
    assert (len(main_buttons) >= CHAPTER_MENU_MIN_MARKERS - 1) is expected
    assert (
        main_buttons[-1].text.endswith("menu entry ptt;") if expected else False
    ) is expected


def test_default_autoplay_uses_first_program_chain_and_opt_out_shows_menu(tmp_path):
    for autoplay in (True, False):
        case_dir = tmp_path / str(autoplay)
        case_dir.mkdir()
        author = _author(case_dir, interval=10, autoplay=autoplay)
        structure = _structure(author, [_converted(case_dir, 1, 1201)])
        video_ts = case_dir / "VIDEO_TS"
        video_ts.mkdir()
        root = ET.parse(_xml_without_rendering(author, structure, video_ts)).getroot()
        fpc = root.find("./vmgm/fpc")
        assert (fpc is not None) is autoplay
        if fpc is not None:
            assert fpc.text == "g0=1;jump title 1;"


def test_single_source_seven_markers_builds_two_grid_pages(tmp_path):
    author = _author(tmp_path, interval=10)
    structure = _structure(author, [_converted(tmp_path, 1, 3601)], "Seven")
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    root = ET.parse(_xml_without_rendering(author, structure, video_ts)).getroot()
    menu_pgcs = root.findall("./titleset/menus/pgc")
    assert len(menu_pgcs) == 3  # Root redirect plus two chapter pages.
    assert menu_pgcs[0].attrib["entry"] == "root"
    assert menu_pgcs[0].find("pre").text == "jump vmgm menu 1;"
    assert menu_pgcs[1].attrib["entry"] == "ptt"
    first_commands = {
        button.attrib["name"]: button.text for button in menu_pgcs[1].findall("button")
    }
    second_commands = {
        button.attrib["name"]: button.text for button in menu_pgcs[2].findall("button")
    }
    assert first_commands["button06"] == "g0=0;jump title 1 chapter 6;"
    assert first_commands["button09"] == "g0=0;jump menu 3;"
    assert second_commands["button01"] == "g0=0;jump title 1 chapter 7;"
    assert second_commands["button08"] == "g0=0;jump menu 2;"


def test_per_source_offsets_keep_vobs_and_cumulative_menu_targets(tmp_path):
    author = _author(tmp_path, interval=10)
    videos = [_converted(tmp_path, 1, 1201), _converted(tmp_path, 2, 601)]
    structure = _structure(author, videos, "A & B")
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    xml_file = _xml_without_rendering(author, structure, video_ts)
    root = ET.parse(xml_file).getroot()
    vobs = root.findall("./titleset/titles/pgc/vob")
    assert len(vobs) == 2
    assert vobs[0].attrib["chapters"] == "0:00:00,0:10:00,0:20:00"
    assert vobs[1].attrib["chapters"] == "0:00:00,0:10:00"
    page_buttons = root.findall("./titleset/menus/pgc[@entry='ptt']/button")
    assert page_buttons[3].text == "g0=0;jump title 1 chapter 4;"
    assert "&amp;" in xml_file.read_text(encoding="utf-8")


def test_title_completion_and_root_menu_return_to_main_menu(tmp_path):
    author = _author(tmp_path)
    structure = _structure(author, [_converted(tmp_path, 1, 1201)])
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()
    root = ET.parse(_xml_without_rendering(author, structure, video_ts)).getroot()
    assert root.find("./titleset/titles/pgc/post").text == "call menu entry root;"
    assert root.find("./titleset/menus/pgc[@entry='root']/pre").text == (
        "jump vmgm menu 1;"
    )


def test_main_menu_button_graph_matches_visible_actions(tmp_path):
    author = _author(tmp_path)
    one = author._main_menu_buttons(False)
    two = author._main_menu_buttons(True)
    assert [button.name for button in one] == ["button01"]
    assert one[0].down == "button01"
    assert [button.name for button in two] == ["button01", "button02"]
    assert two[0].down == "button02"
    assert two[1].up == "button01"


@pytest.mark.parametrize(
    "subtitle,expected_text",
    [
        ("", ["Tangled 2010", "Play all", "Select chapter"]),
        (
            "Family movie night",
            ["Tangled 2010", "Family movie night", "Play all", "Select chapter"],
        ),
    ],
)
def test_main_menu_subtitle_is_optional(tmp_path, subtitle, expected_text):
    author = _author(tmp_path)
    output = tmp_path / "main-menu.mpg"
    draw = Mock()
    draw.textlength.side_effect = lambda text, font: len(text)
    draw.textbbox.return_value = (0, 0, 100, 20)

    with (
        patch("src.services.dvd_author.ImageDraw.Draw", return_value=draw),
        patch.object(author, "_encode_menu_still"),
    ):
        author._create_menu_video(
            tmp_path / "source.mpg",
            output,
            show_chapter_selection=True,
            menu_title="Tangled 2010",
            menu_subtitle=subtitle,
        )

    assert [call.args[1] for call in draw.text.call_args_list] == expected_text


def test_main_menu_subtitle_band_is_blank_by_default_and_visible_when_set(tmp_path):
    author = _author(tmp_path)

    def render(subtitle, filename):
        output = tmp_path / filename
        with patch.object(author, "_encode_menu_still"):
            author._create_menu_video(
                tmp_path / "source.mpg",
                output,
                show_chapter_selection=True,
                menu_title="Tangled 2010",
                menu_subtitle=subtitle,
            )
        with Image.open(output.with_suffix(".png")) as image:
            return image.crop((0, 145, 720, 185)).copy()

    blank_band = render("", "blank.mpg")
    subtitle_band = render("Family movie night", "subtitle.mpg")
    background = Image.new("RGB", blank_band.size, (12, 18, 30))

    assert ImageChops.difference(blank_band, background).getbbox() is None
    assert ImageChops.difference(subtitle_band, background).getbbox() is not None


def test_configured_menu_subtitle_is_passed_to_main_menu_renderer(tmp_path):
    author = _author(tmp_path, menu_subtitle="Family movie night")
    structure = _structure(author, [_converted(tmp_path, 1, 1201)])
    video_ts = tmp_path / "VIDEO_TS"
    video_ts.mkdir()

    with (
        patch.object(author, "_create_menu_video") as render_main,
        patch.object(
            author,
            "_create_chapter_menu_video",
            side_effect=lambda entries, page_number, page_count, *_args, **_kwargs: (
                author._chapter_page_buttons(entries, page_number, page_count)
            ),
        ),
    ):
        author._create_dvd_xml(structure, video_ts)

    assert render_main.call_args.kwargs["menu_subtitle"] == "Family movie night"


def test_partial_second_page_remote_navigation_reaches_back_and_previous(tmp_path):
    author = _author(tmp_path)
    chapters = author._create_chapters([_converted(tmp_path, 1, 3601)])
    entries = author._flatten_chapter_menu_entries(chapters)
    configs = author._chapter_page_buttons(entries[6:], 2, 2)
    by_name = {config.name: config for config in configs}
    assert by_name["button01"].down == "button07"
    assert by_name["button07"].right == "button08"
    assert by_name["button08"].navigation_command == "g0=0;jump menu 2;"


def test_thumbnail_extracts_one_second_after_marker_and_uses_cache(tmp_path):
    author = _author(tmp_path)
    author.tool_manager.get_tool_command.return_value = ["ffmpeg"]
    entry = author._flatten_chapter_menu_entries(
        author._create_chapters([_converted(tmp_path, 1, 1201)])
    )[1]

    def create_thumbnail(command, **_kwargs):
        Image.new("RGB", (180, 96), "navy").save(Path(command[-1]))
        return Mock(stderr="")

    with patch(
        "src.services.dvd_author.subprocess.run", side_effect=create_thumbnail
    ) as run:
        first = author._chapter_thumbnail(entry, 180, 96)
        second = author._chapter_thumbnail(entry, 180, 96)
    command = run.call_args.args[0]
    assert command[command.index("-ss") + 1] == "601"
    assert command[command.index("-map") + 1] == "0:v:0"
    assert first == second
    assert run.call_count == 1


def test_effectively_black_thumbnail_retries_later_inside_same_chapter(tmp_path):
    author = _author(tmp_path)
    author.tool_manager.get_tool_command.return_value = ["ffmpeg"]
    entry = author._flatten_chapter_menu_entries(
        author._create_chapters([_converted(tmp_path, 1, 1201)])
    )[0]
    seeks = []

    def create_thumbnail(command, **_kwargs):
        seek = int(command[command.index("-ss") + 1])
        seeks.append(seek)
        color = "black" if seek == 1 else "white"
        Image.new("RGB", (180, 96), color).save(Path(command[-1]))
        return Mock(stderr="")

    with patch("src.services.dvd_author.subprocess.run", side_effect=create_thumbnail):
        thumbnail = author._chapter_thumbnail(entry, 180, 96)
    assert seeks == [1, 3]
    assert author._thumbnail_has_picture(thumbnail)


def test_thumbnail_failure_creates_timestamp_placeholder(tmp_path):
    author = _author(tmp_path)
    author.tool_manager.get_tool_command.return_value = ["ffmpeg"]
    entry = author._flatten_chapter_menu_entries(
        author._create_chapters([_converted(tmp_path, 1, 1201)])
    )[0]
    with patch(
        "src.services.dvd_author.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["ffmpeg"]),
    ):
        thumbnail = author._chapter_thumbnail(entry, 180, 96)
    assert thumbnail.exists()
    assert Image.open(thumbnail).size == (180, 96)


@pytest.mark.parametrize("video_format,expected_height", [("NTSC", 480), ("PAL", 576)])
def test_chapter_page_renders_six_thumbnail_grid_at_disc_resolution(
    tmp_path, video_format, expected_height
):
    author = _author(tmp_path, interval=10, video_format=video_format)
    entries = author._flatten_chapter_menu_entries(
        author._create_chapters([_converted(tmp_path, 1, 3001)])
    )
    thumbnail = tmp_path / "thumb.png"
    Image.new("RGB", (180, author._scale_y(96)), "navy").save(thumbnail)
    output = tmp_path / "menu1-0.mpg"
    with (
        patch.object(author, "_chapter_thumbnail", return_value=thumbnail),
        patch.object(author, "_encode_menu_still") as encode,
    ):
        configs = author._create_chapter_menu_video(
            entries, 1, 1, "Movie", output, False
        )
    still = output.with_suffix(".png")
    assert Image.open(still).size == (720, expected_height)
    assert len([config for config in configs if config.name <= "button06"]) == 6
    encode.assert_called_once_with(still, output, "16:9")


def test_menu_encoder_requires_dvd_video_and_audio_properties(tmp_path):
    author = _author(tmp_path, video_format="PAL", aspect_ratio="4:3")
    author.tool_manager.get_tool_command.return_value = ["ffmpeg"]
    still = tmp_path / "menu.png"
    output = tmp_path / "menu.mpg"
    with patch("src.services.dvd_author.subprocess.run") as run:
        author._encode_menu_still(still, output, "4:3")
    command = run.call_args.args[0]
    assert command[command.index("-r") + 1] == "25"
    assert command[command.index("-g") + 1] == "15"
    assert command[command.index("-c:a") + 1] == "ac3"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-aspect") + 1] == "4:3"


def test_authoring_rejects_more_programs_than_one_dvd_title_can_hold(tmp_path):
    author = _author(tmp_path, interval=None)
    videos = [_converted(tmp_path, index, 1) for index in range(1, 257)]
    with pytest.raises(DVDAuthoringError, match="256 chapter markers.*split"):
        author.create_dvd_structure(videos, "Too Many", tmp_path, "too-many")
