# DVD Maker

Convert YouTube playlists into physical DVDs.

## Features

- **Video Downloading**: Download YouTube playlists using yt-dlp with intelligent caching
- **Video Processing**: Convert videos to DVD-compatible format using ffmpeg with advanced car DVD player compatibility
- **DVD Authoring**: Create DVD structure with single title and multiple chapters (one per video)
- **Smart Caching**: Intelligent file caching to avoid redundant operations with comprehensive cleanup tools
- **Filename Normalization**: ASCII filename normalization for DVD compatibility
- **Progress Tracking**: Real-time progress reporting for all operations
- **Error Handling**: Graceful handling of missing/private videos with partial playlist success
- **Rate Limiting**: Respectful downloading with configurable rate limits
- **Cross-platform**: Support for Linux and macOS (Intel/Apple Silicon)
- **DVD Capacity Management**: Automatically excludes videos when playlist exceeds DVD capacity with detailed warnings
- **Comprehensive Metrics**: Reports total processing time, file sizes, and video durations in human-readable format
- **Platform-specific Instructions**: Provides tailored tool installation instructions based on detected platform

## Requirements

- Python 3.10+
- ffmpeg (auto-downloaded)
- yt-dlp (auto-downloaded)
- dvdauthor (system installation required)

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

4. Install dvdauthor:
```bash
# macOS
brew install dvdauthor

# Ubuntu/Debian
sudo apt install dvdauthor

# RHEL/CentOS
sudo yum install dvdauthor
```

## Usage

```bash
python -m dvdmaker --playlist-url "https://www.youtube.com/playlist?list=..." [options]
```

### Examples

Basic usage:
```bash
python -m dvdmaker --playlist-url "https://www.youtube.com/playlist?list=PLxxx"
```

Custom output directory and DVD title:
```bash
python -m dvdmaker --playlist-url "PLxxx" --output-dir ./my-dvd --menu-title "My Collection"
```

PAL format with 4:3 aspect ratio:
```bash
python -m dvdmaker --playlist-url "PLxxx" --video-format PAL --aspect-ratio "4:3"
```

Skip ISO generation:
```bash
python -m dvdmaker --playlist-url "PLxxx" --no-iso
```

Clean cache files:
```bash
python -m dvdmaker --clean conversions  # Clean converted video files
python -m dvdmaker --clean all          # Clean all cache types
```

### Options

#### Required
- `--playlist-url`: YouTube playlist URL or playlist ID

#### Directory Options
- `--output-dir`: Specify output directory (default: ./output)
- `--cache-dir`: Cache directory for downloaded/processed files (default: ./cache)
- `--temp-dir`: Temporary files location (default: ./temp)

#### Video Options
- `--quality`: Video quality preference (default: best)
- `--video-format`: DVD video format - NTSC (29.97fps, 720x480) or PAL (25fps, 720x576) (default: NTSC)
- `--aspect-ratio`: DVD aspect ratio - 4:3 (standard) or 16:9 (widescreen) (default: 16:9)

#### DVD Options
- `--menu-title`: Custom DVD menu title (default: playlist title)
- `--no-iso`: Skip ISO image generation (ISO creation is enabled by default)
- `--autoplay`: Enable DVD autoplay (automatically start playing videos on insertion)

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
- **Intelligent Caching**: Caches converted files to avoid redundant processing

Technical specifications:
- **Video**: MPEG-2 encoding with standard bitrate (6Mbps) or conservative car-compatible bitrate (3.5Mbps)
- **Audio**: AC-3 encoding at 448kbps (standard) or 192kbps (car-compatible), stereo, 48kHz sample rate
- **Resolution**: 720x480 (NTSC) or 720x576 (PAL) with proper interlaced encoding for car players
- **Aspect Ratio**: 16:9 widescreen (default) or 4:3 standard format with correct sample aspect ratio
- **Frame Rate**: 29.97fps (NTSC) or 25fps (PAL) with top-field-first interlaced encoding
- **Car Compatibility**: Conservative GOP size (12), no B-frames, and strict DVD-Video spec compliance

### DVD Authoring

Creates complete DVD structures using dvdauthor:

- **DVD Structure Creation**: Generates VIDEO_TS directory structure with proper IFO/BUP/VOB files
- **Chapter Organization**: Combines multiple videos into a single title with sequential chapters (maintains playlist order)
- **Menu Generation**: Creates interactive DVD menus with chapter navigation
- **Capacity Management**: Automatically excludes videos when content exceeds standard DVD capacity (4.7GB) with detailed warnings including video names and YouTube URLs
- **Partial Success**: Creates DVDs with successfully processed videos even if some conversions fail
- **ISO Generation**: Optional ISO image creation for burning or virtual drive mounting
- **Structure Validation**: Validates completed DVD structure for compatibility

Technical specifications:
- **DVD Format**: Single-layer DVD structure (4.7GB capacity)
- **Title Structure**: Single title with multiple chapters (sequential playlist videos)
- **Menu System**: Simple chapter selection menu with thumbnail previews
- **Compatibility**: Playable on standard DVD players and software

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