"""CLI and settings coverage for local media and automatic chapters."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src.config.settings import Settings
from src.main import (
    create_argument_parser,
    merge_settings_with_args,
    validate_arguments,
    validate_tools,
)


def test_input_is_repeatable_and_operation_modes_are_mutually_exclusive():
    parser = create_argument_parser()
    args = parser.parse_args(["--input", "one.mp4", "--input", "videos"])
    assert args.input == [Path("one.mp4"), Path("videos")]

    with pytest.raises(SystemExit):
        parser.parse_args(["--input", "one.mp4", "--playlist-url", "PL1234567890"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--input", "one.mp4", "--clean", "all"])


@pytest.mark.parametrize("value", [0, 121, -1])
def test_chapter_interval_cli_range(value):
    args = create_argument_parser().parse_args(
        ["--input", "one.mp4", "--chapter-interval-minutes", str(value)]
    )
    with pytest.raises(ValueError, match="between 1 and 120"):
        validate_arguments(args)


@pytest.mark.parametrize("value", [1, 10, 120])
def test_chapter_interval_cli_valid(value):
    args = create_argument_parser().parse_args(
        ["--input", "one.mp4", "--chapter-interval-minutes", str(value)]
    )
    validate_arguments(args)


def test_chapter_interval_and_ai_title_environment(monkeypatch):
    monkeypatch.setenv("DVDMAKER_CHAPTER_INTERVAL_MINUTES", "12")
    monkeypatch.setenv("DVDMAKER_AI_TITLES", "false")
    settings = Settings()
    assert settings.chapter_interval_minutes == 12
    assert settings.ai_titles is False


def test_cli_overrides_environment_for_new_settings(monkeypatch):
    monkeypatch.setenv("DVDMAKER_CHAPTER_INTERVAL_MINUTES", "12")
    monkeypatch.setenv("DVDMAKER_AI_TITLES", "true")
    settings = Settings()
    args = create_argument_parser().parse_args(
        ["--input", "one.mp4", "--chapter-interval-minutes", "20", "--no-ai-titles"]
    )
    merged = merge_settings_with_args(args, settings)
    assert merged.chapter_interval_minutes == 20
    assert merged.ai_titles is False


@pytest.mark.parametrize("value", [0, 121])
def test_settings_reject_invalid_chapter_interval(value):
    with pytest.raises(ValidationError):
        Settings(chapter_interval_minutes=value)


def test_local_tool_validation_does_not_require_or_update_ytdlp():
    manager = Mock()
    manager.ensure_tools_available.return_value = (True, [])

    assert validate_tools(manager, require_ytdlp=False)

    manager.check_and_update_ytdlp.assert_not_called()
    manager.ensure_tools_available.assert_called_once_with(require_ytdlp=False)
