"""Discovery, validation, and conservative naming for local video inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from ..exceptions import DVDMakerError
from ..models.video import VideoFile, VideoMetadata
from ..utils.logging import get_logger
from .tool_manager import ToolManager

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts",
}
TITLE_MODEL = "gpt-5.6-luna"
TITLE_PROMPT_VERSION = "local-title-cleanup-v1"


class LocalMediaError(DVDMakerError):
    """Raised when a local input cannot be discovered or validated."""


@dataclass(frozen=True)
class LocalMediaSet:
    """Validated local files plus the menu title implied by their locations."""

    videos: List[VideoFile]
    default_menu_title: str


def natural_filename_key(path: Path) -> List[object]:
    """Return a case-insensitive natural ordering key for one filename."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    ]


def expand_local_inputs(inputs: Sequence[Path]) -> List[Path]:
    """Expand directory arguments in place, non-recursively, and deduplicate."""
    expanded: List[Path] = []
    seen: set[Path] = set()

    for supplied_path in inputs:
        path = supplied_path.expanduser().resolve()
        if not path.exists():
            raise LocalMediaError(f"Local input does not exist: {supplied_path}")

        if path.is_dir():
            try:
                candidates = sorted(
                    (
                        child.resolve()
                        for child in path.iterdir()
                        if child.is_file()
                        and child.suffix.casefold() in VIDEO_EXTENSIONS
                    ),
                    key=natural_filename_key,
                )
            except OSError as exc:
                raise LocalMediaError(
                    f"Cannot read input directory {path}: {exc}"
                ) from exc
            if not candidates:
                raise LocalMediaError(f"No supported video files found in {path}")
        elif path.is_file():
            candidates = [path]
        else:
            raise LocalMediaError(
                f"Local input is not a regular file or directory: {path}"
            )

        for candidate in candidates:
            if candidate in seen:
                logger.warning("Ignoring duplicate local input: %s", candidate)
                continue
            seen.add(candidate)
            expanded.append(candidate)

    if not expanded:
        raise LocalMediaError("No local video files were selected")
    return expanded


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LocalMediaError(f"Cannot read local media {path}: {exc}") from exc
    return digest.hexdigest()


def _ffprobe_command(tool_manager: ToolManager) -> str:
    ffmpeg = Path(tool_manager.get_tool_command("ffmpeg")[0])
    return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe")))


def probe_local_video(path: Path, tool_manager: ToolManager) -> Dict[str, Any]:
    """Probe a local file and require usable video, audio, and duration."""
    if not os.access(path, os.R_OK):
        raise LocalMediaError(f"Local media is not readable: {path}")
    command = [
        _ffprobe_command(tool_manager),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LocalMediaError(f"Failed to inspect local media {path}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "ffprobe rejected the file"
        raise LocalMediaError(f"Unreadable local media {path}: {detail}")
    try:
        info: Dict[str, Any] = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LocalMediaError(f"Invalid ffprobe response for {path}") from exc

    streams = info.get("streams", [])
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise LocalMediaError(f"Local media has no video stream: {path}")
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise LocalMediaError(f"Local media has no audio stream: {path}")
    try:
        duration = float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        stream_durations: List[float] = []
        for stream in streams:
            try:
                stream_durations.append(float(stream.get("duration", 0)))
            except (TypeError, ValueError):
                pass
        duration = max(stream_durations, default=0)
    if duration <= 0:
        raise LocalMediaError(f"Local media has no positive duration: {path}")
    info["_dvdmaker_duration"] = duration
    return info


def build_local_video_files(
    paths: Sequence[Path], tool_manager: ToolManager
) -> List[VideoFile]:
    """Build content-addressed VideoFile objects for validated local sources."""
    videos: List[VideoFile] = []
    for path in paths:
        info = probe_local_video(path, tool_manager)
        checksum = _sha256(path)
        duration = max(1, int(float(info["_dvdmaker_duration"])))
        metadata = VideoMetadata(
            video_id=checksum,
            title=path.stem,
            duration=duration,
            url=path.as_uri(),
        )
        videos.append(
            VideoFile(
                metadata=metadata,
                file_path=path,
                file_size=path.stat().st_size,
                checksum=checksum,
                format=path.suffix.lstrip(".").casefold() or "unknown",
                stream_details=info,
            )
        )
    return videos


class LocalTitleInferrer:
    """Infer conservative display titles with a content-addressed JSON cache."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_file = cache_dir / "local_title_cache.json"

    @staticmethod
    def _cache_key(checksum: str) -> str:
        return f"{checksum}:{TITLE_MODEL}:{TITLE_PROMPT_VERSION}"

    def _load_cache(self) -> Dict[str, str]:
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cache(self, cache: Dict[str, str]) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
        )

    @staticmethod
    def _schema(count: int) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "titles": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "title": {"type": "string", "minLength": 1},
                        },
                        "required": ["index", "title"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["titles"],
            "additionalProperties": False,
        }

    @staticmethod
    def _prompt(basenames: Iterable[str]) -> str:
        indexed = "\n".join(
            f"{index}: {json.dumps(name)}" for index, name in enumerate(basenames)
        )
        return (
            "Return one conservative display title for every indexed filename below. "
            "Only normalize separators and remove obvious release, source, codec, and "
            "resolution tags. Do not invent, translate, summarize, or add missing "
            "details. Preserve meaningful years and episode information.\n\n"
            f"Filenames:\n{indexed}"
        )

    @staticmethod
    def _validate_response(stdout: str, count: int) -> List[str]:
        data = json.loads(stdout)
        items = data.get("titles") if isinstance(data, dict) else None
        if not isinstance(items, list) or len(items) != count:
            raise ValueError("response did not contain the expected title count")
        by_index: Dict[int, str] = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("title entry was not an object")
            index, title = item.get("index"), item.get("title")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not isinstance(title, str)
                or not title.strip()
                or index in by_index
            ):
                raise ValueError("invalid indexed title entry")
            by_index[index] = title.strip()
        if set(by_index) != set(range(count)):
            raise ValueError("response title indexes were incomplete")
        return [by_index[index] for index in range(count)]

    def infer(self, videos: Sequence[VideoFile], enabled: bool = True) -> List[str]:
        fallbacks = [video.file_path.stem for video in videos]
        if not enabled or not videos:
            return fallbacks

        cache = self._load_cache()
        results: List[str | None] = [None] * len(videos)
        missing_indexes: List[int] = []
        for index, video in enumerate(videos):
            cached = cache.get(self._cache_key(video.checksum))
            if isinstance(cached, str) and cached.strip():
                results[index] = cached.strip()
            else:
                missing_indexes.append(index)
        if not missing_indexes:
            return [title or fallback for title, fallback in zip(results, fallbacks)]

        missing = [videos[index] for index in missing_indexes]
        try:
            codex = shutil.which("codex")
            if not codex:
                raise FileNotFoundError("codex executable was not found")
            with tempfile.TemporaryDirectory(prefix="dvdmaker-titles-") as temp_name:
                temp_dir = Path(temp_name)
                schema_file = temp_dir / "title-schema.json"
                schema_file.write_text(
                    json.dumps(self._schema(len(missing))), encoding="utf-8"
                )
                command = [
                    codex,
                    "exec",
                    "--model",
                    TITLE_MODEL,
                    "--sandbox",
                    "read-only",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--cd",
                    str(temp_dir),
                    "--output-schema",
                    str(schema_file),
                    "-",
                ]
                completed = subprocess.run(
                    command,
                    input=self._prompt(video.file_path.name for video in missing),
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        completed.stderr.strip()
                        or f"codex exited with status {completed.returncode}"
                    )
                inferred = self._validate_response(completed.stdout, len(missing))
            for original_index, title in zip(missing_indexes, inferred):
                results[original_index] = title
                cache[self._cache_key(videos[original_index].checksum)] = title
            self._save_cache(cache)
        except Exception as exc:
            logger.warning(
                "Could not infer local video titles with Codex; using filename "
                "stems instead: %s",
                exc,
            )
            for index in missing_indexes:
                results[index] = fallbacks[index]
        return [title or fallback for title, fallback in zip(results, fallbacks)]


def load_local_media(
    inputs: Sequence[Path],
    tool_manager: ToolManager,
    cache_dir: Path,
    ai_titles: bool = True,
) -> LocalMediaSet:
    """Expand, validate, identify, and title all local media inputs."""
    paths = expand_local_inputs(inputs)
    videos = build_local_video_files(paths, tool_manager)
    titles = LocalTitleInferrer(cache_dir).infer(videos, enabled=ai_titles)
    titled_videos = [
        replace(video, metadata=replace(video.metadata, title=title))
        for video, title in zip(videos, titles)
    ]

    if len(titled_videos) == 1:
        default_title = titled_videos[0].metadata.title
    elif len({video.file_path.parent for video in titled_videos}) == 1:
        default_title = titled_videos[0].file_path.parent.name or "Local Videos"
    else:
        default_title = "Local Videos"
    return LocalMediaSet(titled_videos, default_title)
