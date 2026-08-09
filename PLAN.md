# Local Video Input and Automatic DVD Chapters

## Scope

The Python application authors a DVD from exactly one operation mode:

- `--playlist-url URL`
- one or more repeatable `--input PATH` arguments
- `--clean ...`

The PowerShell conversion helper is outside this change. All sources on a disc
use the selected global NTSC/PAL and 4:3/16:9 settings.

## Local input behavior

Directory arguments expand non-recursively at their position in the argument
list. Recognized extensions are `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`,
`.mpg`, `.mpeg`, `.ts`, and `.m2ts`; their ordering is case-insensitive and
natural. Explicit files with other extensions proceed to `ffprobe`. Resolved
paths are deduplicated while retaining their first occurrence.

Every local file must be readable and contain video, audio, and a positive
duration. Its SHA-256 is both the local content ID and source checksum, and its
source URL is a file URI. Local source files are never changed.

Local display names default to filename stems. Unless `--no-ai-titles` or
`DVDMAKER_AI_TITLES=false` is set, all uncached names are cleaned in one ephemeral
`codex exec` call using `gpt-5.6-luna`, a read-only sandbox, a temporary working
directory, and a strict output schema. Only basenames are sent. Any missing CLI,
authentication, timeout, command, or response-validation problem warns once and
uses the stems without aborting. Successful titles are cached by content hash,
model, and prompt version.

Menu title precedence is an explicit `--menu-title`, the title of a single local
video, the directory name when all local sources share one directory, then
`Local Videos`.

## Conversion

Every input is probed before conversion. A source is reused only if it is an MPEG
program stream with MPEG-2/yuv420p video at the exact selected dimensions,
frame rate, and display aspect, a positive duration, and 48 kHz AC-3 audio. A
thumbnail is generated even for reused MPEG media.

The shared ffmpeg command selects the first video and audio streams, drops
subtitle/data streams, regenerates and normalizes timestamps, asynchronously
resamples audio, conditionally deinterlaces interlaced frames, preserves picture
shape with scale/pad, and assigns the correct DVD sample aspect ratio. NTSC uses
exact 30000/1001 timing and PAL uses 25. Car mode retains 3.5 Mbps video, 192 kbps
audio, and a 12-frame GOP. Standard mode retains 6 Mbps video and 448 kbps audio,
with GOP 18 for NTSC and 15 for PAL. Both use DVD mux safeguards.

Converted cache entries include the source checksum and a fingerprint of every
encoding-affecting setting. Legacy entries are stale once. Titles and chapter
intervals are not part of that fingerprint, so either can change without an
expensive re-encode.

## Chapters and menus

`--chapter-interval-minutes` and `DVDMAKER_CHAPTER_INTERVAL_MINUTES` accept 1–120.
One source longer than 10 minutes defaults to a 10-minute interval when neither is
set. An explicit value overrides that default. Multiple sources, and one source of
10 minutes or less, retain only their initial markers when the setting is omitted.
Enabled intervals emit 0, interval, 2 × interval, and so on strictly before each
converted source duration, formatted as deterministic `H:MM:SS` values. Missing or
zero duration safely yields the initial marker only.

Each source remains one `DVDChapter` model entry and one `<vob>`; interval markers
do not split or duplicate MPEG files. Menu source jumps use a cumulative map to
global DVD chapter numbers, so a later source still targets its beginning after
earlier interval markers.

Playback starts automatically through an explicit DVD First Program Chain;
`--no-autoplay` instead displays the main menu on insertion. The main menu always
offers Play all and adds Select chapter only when there are at least three total
markers. Pressing the title's root-menu control and reaching the end of the title
return to the main menu.

Chapter selection flattens every per-source offset into chronological global DVD
chapter entries. Each page displays a 3x2 grid of up to six cached thumbnails,
sampled one second after its boundary when possible and retried slightly later
when that frame is effectively black, plus a number/timestamp and optional source
title. Back, Previous, and Next buttons provide paginated remote
navigation. Thumbnail failures use a timestamp placeholder. Spumux or button-layer
failure aborts authoring instead of producing visible controls that do nothing.
Chapter counts beyond one title PGC's 255-program limit fail with a suggested
larger interval or instruction to split the disc.

## Tooling and verification

Local mode requires ffmpeg/ffprobe, dvdauthor/spumux, and an ISO utility when ISO
output is enabled. It does not require yt-dlp. Codex remains optional. Playlist
mode continues to validate/update yt-dlp.

Development requires Python 3.10+ plus the media/authoring tools. On Ubuntu/WSL:

```bash
./scripts/setup.sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
make check
```

Acceptance uses generated local media first with `--no-ai-titles`, followed by
the requested real local file with AI titles and a 10-minute interval. Inspect
the retained `VIDEO_TS` and ISO with `lsdvd`, `dvdunauthor`, and `ffprobe`, then
verify play-all, next/previous, thumbnail targets, pagination, and menu-return behavior in
a DVD-aware player. A physical-player smoke test remains the final compatibility
check.
