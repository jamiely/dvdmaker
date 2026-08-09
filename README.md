# DVD Maker

Author physical DVDs from YouTube playlists or local video files.

## Features

- **Video Downloading**: Download YouTube playlists using yt-dlp with intelligent caching
- **Local Media**: Accept repeatable file and directory inputs without modifying the sources
- **Automatic Chapters**: Add interval markers with paginated visual chapter selection
- **Video Processing**: Convert videos to DVD-compatible format using ffmpeg with advanced car DVD player compatibility
- **DVD Authoring**: Create DVD structure with interactive menus and DVDStyler-compatible autoplay functionality
- **Car DVD Compatibility**: Confirmed working on Honda Odyssey 2016 and other car DVD players with automatic playback
- **Interactive DVD Menus**: Six-thumbnail chapter pages with remote navigation, pagination, and visual feedback
- **Clean ISO Generation**: Professional ISOs containing only AUDIO_TS/VIDEO_TS directories (no build artifacts)
- **Smart Caching**: Intelligent file caching to avoid redundant operations with comprehensive cleanup tools
- **Filename Normalization**: ASCII filename normalization for DVD compatibility
- **Progress Tracking**: Real-time progress reporting for all operations
- **Error Handling**: Graceful handling of missing/private videos with partial playlist success
- **Rate Limiting**: Respectful downloading with configurable rate limits
- **Cross-platform**: Support for Linux and macOS (Intel/Apple Silicon)
- **DVD Capacity Management**: Automatically excludes videos when playlist exceeds DVD capacity with detailed warnings
- **Comprehensive Metrics**: Reports total processing time, file sizes, and video durations in human-readable format
- **Platform-specific Instructions**: Provides tailored tool installation instructions based on detected platform
- **Build Artifact Management**: All temporary files and build artifacts organized in cache directories

## Requirements

- Python 3.10+
- ffmpeg (auto-downloaded)
- yt-dlp (auto-downloaded and required only for playlist input)
- dvdauthor (system installation required)
- spumux (included with dvdauthor package - for interactive DVD menus)
- genisoimage or mkisofs (when ISO generation is enabled)
- Codex CLI (optional; local title cleanup safely falls back to filename stems)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd dvdmaker
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

For development, also install development dependencies:
```bash
pip install -r requirements-dev.txt
```

4. On Ubuntu, Debian, or WSL, install all system prerequisites with:

```bash
./scripts/setup.sh
```

Use `./scripts/setup.sh --check` to verify an existing installation or
`./scripts/setup.sh --dry-run` to preview the apt commands.

Alternatively, install the platform media and authoring prerequisites manually:
```bash
# macOS
brew install ffmpeg dvdauthor dvdrtools

# Ubuntu/Debian
sudo apt install ffmpeg dvdauthor genisoimage lsdvd

# RHEL/CentOS
sudo yum install dvdauthor
```

## Usage

```bash
python -m src.main --playlist-url "https://www.youtube.com/playlist?list=..." [options]
```

### Examples

Basic usage:
```bash
python -m src.main --playlist-url "https://www.youtube.com/playlist?list=PLxxx"
```

Custom output directory and DVD title:
```bash
python -m src.main --playlist-url "PLxxx" --output-dir ./my-dvd --menu-title "My Collection"
```

PAL format with 4:3 aspect ratio:
```bash
python -m src.main --playlist-url "PLxxx" --video-format PAL --aspect-ratio "4:3"
```

One local video with 10-minute chapter markers:
```bash
python -m src.main --input ./movie.mp4 --chapter-interval-minutes 10
```

Playback starts automatically by default. Start at the main menu instead:

```bash
python -m src.main --input ./movie.mp4 --no-autoplay
```

Add an optional line beneath the menu title:

```bash
python -m src.main --input ./movie.mp4 --menu-subtitle "Family movie night"
```

Files and directories can be mixed and repeated. Directory expansion occurs at
that exact argument position, is non-recursive, and uses case-insensitive natural
filename order:
```bash
python -m src.main \
  --input ./opening.mov \
  --input ./episodes \
  --input ./bonus.mkv
```

Use filename stems without optional AI cleanup:
```bash
python -m src.main --input ./videos --no-ai-titles
```

Skip ISO generation:
```bash
python -m src.main --playlist-url "PLxxx" --no-iso
```

Clean cache files:
```bash
python -m src.main --clean conversions  # Clean converted video files
python -m src.main --clean all          # Clean all cache types
```

### Options

#### Operation Mode
- `--playlist-url`: YouTube playlist URL or playlist ID
- `--input`: Local file or directory; repeat the flag for additional inputs
- `--clean`: Clean cached/output data by type

These modes are mutually exclusive. Directories discover `.mp4`, `.mov`, `.mkv`,
`.avi`, `.webm`, `.m4v`, `.mpg`, `.mpeg`, `.ts`, and `.m2ts` files. Explicit
files with other extensions are accepted when `ffprobe` recognizes them. Paths
are resolved and deduplicated while preserving their first occurrence.

#### Directory Options
- `--output-dir`: Specify output directory (default: ./output)
- `--cache-dir`: Cache directory for downloaded/processed files (default: ./cache)
- `--temp-dir`: Temporary files location (default: ./temp)

#### Video Options
- `--quality`: Video quality preference (default: best)
- `--video-format`: DVD video format - NTSC (29.97fps, 720x480) or PAL (25fps, 720x576) (default: NTSC)
- `--aspect-ratio`: DVD aspect ratio - 4:3 (standard) or 16:9 (widescreen) (default: 16:9)
- `--no-ai-titles`: Disable conservative Codex title cleanup for local files

#### DVD Options
- `--menu-title`: Custom DVD menu title (default: playlist/local source title)
- `--menu-subtitle`: Optional text beneath the menu title (default: empty; also configurable with `DVDMAKER_MENU_SUBTITLE`)
- `--no-iso`: Skip ISO image generation (ISO creation is enabled by default)
- `--autoplay`: Explicitly retain the default behavior of starting playback on insertion
- `--no-autoplay`: Show the main menu when the disc is inserted
- `--chapter-interval-minutes`: Override chapter spacing with 1-120 minutes within each source

#### Cache Options
- `--force-download`: Force re-download all video files and refresh playlist data, even if cached
- `--force-convert`: Force re-conversion even if cached
- `--refresh-playlist`: Refresh playlist data to detect newly added videos (without re-downloading existing videos)

#### Tool Options
- `--download-tools`: Download required tools to local bin directory
- `--use-system-tools`: Use system-installed tools instead of local bin

#### Logging Options
- `--log-level`: Set logging level (TRACE, DEBUG, INFO, WARNING, ERROR)
- `--log-file`: Specify log file path (default: logs/dvdmaker.log)
- `--verbose`: Enable verbose console output
- `--quiet`: Suppress all console output except errors

#### Cleanup Options
- `--clean`: Clean cache/output/temp files by type (downloads, conversions, dvd-output, isos, all)

#### Configuration
- `--config`: Configuration file path

## How It Works

### Video Downloading

The system uses yt-dlp to extract and download YouTube playlist content:

- **Playlist Extraction**: Extracts playlist metadata and video information while maintaining original video ordering
- **Intelligent Caching**: Checks cache before downloading to avoid redundant operations
- **Progress Reporting**: Provides real-time progress updates during downloads
- **Error Handling**: Gracefully handles missing/private videos, continuing with available content
- **Rate Limiting**: Respects YouTube's servers with configurable download rate limits (default: 1MB/s)
- **Metadata Storage**: Caches video metadata for faster subsequent operations
- **Atomic Operations**: Uses temporary files and atomic moves to prevent corruption

### Video Processing

Converts downloaded videos to DVD-compatible formats using ffmpeg:

- **DVD Format Conversion**: Converts videos to MPEG-2 with DVD-standard resolutions (720x480 NTSC/720x576 PAL)
- **Audio Standardization**: Converts audio to AC-3 format with proper bitrates and sample rates for DVD compatibility
- **Aspect Ratio Handling**: Automatically determines and applies appropriate DVD aspect ratios with proper sample aspect ratio
- **Frame Rate Conversion**: Handles NTSC (29.97fps) and PAL (25fps) frame rate conversion based on source material
- **Car DVD Compatibility**: Strict DVD-Video specification compliance with interlaced encoding for maximum car player compatibility
- **Thumbnail Generation**: Creates DVD menu thumbnails from video content
- **Quality Validation**: Verifies converted files meet DVD specifications
- **Compatible MPEG Reuse**: Reuses an already compliant MPEG-2 program stream while still generating its thumbnail
- **Intelligent Caching**: Validates the source checksum and complete conversion-profile fingerprint. Legacy entries are converted once; changing a title or chapter interval does not re-encode media.

Technical specifications:
- **Video**: MPEG-2 encoding with standard bitrate (6Mbps) or conservative car-compatible bitrate (3.5Mbps)
- **Audio**: AC-3 encoding at 448kbps (standard) or 192kbps (car-compatible), stereo, 48kHz sample rate
- **Resolution**: 720x480 (NTSC) or 720x576 (PAL) with proper interlaced encoding for car players
- **Aspect Ratio**: 16:9 widescreen (default) or 4:3 standard format with correct sample aspect ratio
- **Frame Rate**: Exact 30000/1001fps (NTSC) or 25fps (PAL) timing with top-field-first interlaced encoding
- **Car Compatibility**: Conservative GOP size (12), no B-frames, and strict DVD-Video spec compliance

### DVD Authoring

Creates complete DVD structures using dvdauthor with DVDStyler-compatible menus:

- **DVD Structure Creation**: Generates VIDEO_TS directory structure with proper IFO/BUP/VOB files
- **Chapter Organization**: Combines multiple videos into a single title with sequential chapters (maintains playlist order)
- **Interval Navigation**: Each source independently receives markers at 0, interval, 2 × interval, and so on, strictly before its converted duration
- **Autoplay by Default**: A First Program Chain starts the title immediately; `--no-autoplay` starts at the main menu
- **Interactive Menu System**: "Play all" plus a chapter browser when at least three total markers exist
- **Thumbnail Pages**: Six selectable chapter thumbnails per page with Back, Previous, and Next controls
- **Remote Menu Return**: The title's root-menu path and end-of-title action return to the main menu
- **Car DVD Player Compatibility**: Confirmed working autoplay functionality on Honda Odyssey 2016 and other car players
- **Professional ISO Output**: Clean ISOs containing only AUDIO_TS/VIDEO_TS directories (no build artifacts)
- **Capacity Management**: Automatically excludes videos when content exceeds standard DVD capacity (4.7GB) with detailed warnings
- **Partial Success**: Creates DVDs with successfully processed videos even if some conversions fail
- **ISO Generation**: Optional professional-quality ISO image creation for burning or virtual drive mounting
- **Structure Validation**: Validates completed DVD structure for compatibility

Technical specifications:
- **DVD Format**: Single-layer DVD structure (4.7GB capacity)
- **Title Structure**: Single title with sequential source videos and chapter markers
- **Menu System**: Static DVD-compliant MPEG menus with cached thumbnails and Spumux-generated multi-button overlays
- **Autoplay**: An explicit First Program Chain runs `g0=1;jump title 1;`
- **Chapter Pages**: A 3x2 grid maps source-local offsets to cumulative global DVD chapter numbers
- **Compatibility**: Playable on standard DVD players, car DVD systems, and software players

Interval markers remain available through a player's next/previous controls. A
disc containing one video longer than 10 minutes defaults to markers every 10
minutes; an explicit `--chapter-interval-minutes` value overrides that spacing.
When there are at least three markers across the disc, the main menu adds Select
chapter and every marker receives a thumbnail button. Pages contain up to six
buttons and continue in chronological order across source boundaries. With one or
two markers, the main menu contains only Play all. Multiple source videos without
an explicit interval continue to receive one initial marker each. Changing chapter
spacing or menu labels re-authors the menus and disc without re-encoding media.

### Local title privacy and defaults

For local input, title cleanup is enabled by default and uses one ephemeral
`codex exec` request with the cost-oriented `gpt-5.6-luna` model. Only basenames
are sent—never full paths or media contents—and the request asks only for
conservative separator/tag cleanup. CLI absence, authentication errors, timeouts,
invalid output, and all other inference failures produce one warning and fall
back to filename stems without stopping DVD creation. Successful results are
cached by content hash, model, and prompt version.

`--menu-title` always wins. Otherwise one local video uses its inferred/fallback
title, multiple files from one directory use that directory name, and mixed
locations use `Local Videos`. `DVDMAKER_AI_TITLES` and
`DVDMAKER_CHAPTER_INTERVAL_MINUTES` provide environment-level controls.

### Cache Management & Cleanup

Comprehensive cache management system for efficient disk space usage:

- **Intelligent Cleanup**: Selective removal of downloads, conversions, DVD output, ISOs, and temporary files
- **Subdirectory Support**: Properly handles nested cache structures including video-specific subdirectories
- **Metadata Synchronization**: Cleans both cached files and their associated metadata
- **Progress Tracking**: Shows detailed cleanup statistics including files removed, directories cleaned, and space freed
- **Safety Preservation**: Protects in-progress operations from accidental cleanup
- **Granular Control**: Clean specific cache types (downloads, conversions, etc.) or all at once

Cleanup types:
- **downloads**: Downloaded video files from yt-dlp
- **conversions**: DVD-converted video files and thumbnails (includes subdirectories)
- **dvd-output**: Generated VIDEO_TS directory structures and DVDs
- **isos**: Created ISO image files
- **temp**: Temporary processing files
- **all**: Complete cache cleanup across all types

## Development

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run quality checks:
```bash
make check
```

Individual commands:
```bash
make format    # Format with black and isort
make lint      # Run flake8
make typecheck # Run mypy
make test      # Run tests
make coverage  # Run tests with coverage
```

## License

MIT License
