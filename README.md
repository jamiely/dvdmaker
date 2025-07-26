# DVD Maker

Convert YouTube playlists into physical DVDs.

## Features

- **Video Downloading**: Download YouTube playlists using yt-dlp with intelligent caching
- **Video Processing**: Convert videos to DVD-compatible format using ffmpeg
- **DVD Authoring**: Create DVD structure with single title and multiple chapters (one per video)
- **Smart Caching**: Intelligent file caching to avoid redundant operations
- **Filename Normalization**: ASCII filename normalization for DVD compatibility
- **Progress Tracking**: Real-time progress reporting for all operations
- **Error Handling**: Graceful handling of missing/private videos with partial playlist success
- **Rate Limiting**: Respectful downloading with configurable rate limits
- **Cross-platform**: Support for Linux and macOS (Intel/Apple Silicon)

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

### Options

- `--output-dir`: Specify output directory (default: ./output)
- `--cache-dir`: Cache directory for downloaded/processed files (default: ./cache)
- `--temp-dir`: Temporary files location (default: ./temp)
- `--quality`: Video quality preference (default: best)
- `--menu-title`: Custom DVD menu title
- `--iso`: Generate ISO image after DVD creation
- `--force-download`: Force re-download even if cached
- `--force-convert`: Force re-conversion even if cached
- `--download-tools`: Download required tools to local bin directory
- `--use-system-tools`: Use system-installed tools instead of local bin
- `--log-level`: Set logging level (TRACE, DEBUG, INFO, WARNING, ERROR)
- `--log-file`: Specify log file path (default: logs/dvdmaker.log)
- `--verbose`: Enable verbose console output
- `--quiet`: Suppress all console output except errors

## How It Works

### Video Downloading (Phase 8 - Completed)

The video downloading system uses yt-dlp to extract and download YouTube playlist content:

1. **Playlist Extraction**: Extracts playlist metadata and video information while maintaining original video ordering
2. **Intelligent Caching**: Checks cache before downloading to avoid redundant operations
3. **Progress Reporting**: Provides real-time progress updates during downloads
4. **Error Handling**: Gracefully handles missing/private videos, continuing with available content
5. **Rate Limiting**: Respects YouTube's servers with configurable download rate limits (default: 1MB/s)
6. **Metadata Storage**: Caches video metadata for faster subsequent operations
7. **Atomic Operations**: Uses temporary files and atomic moves to prevent corruption

The downloader supports:
- Full playlist downloads with video ordering preservation
- Individual video downloads with caching
- Partial playlist success (continues even if some videos fail)
- Video status tracking (AVAILABLE, DOWNLOADING, DOWNLOADED, FAILED, MISSING, PRIVATE)
- Automatic tool management (downloads yt-dlp if not available)

### Video Processing (Phase 9 - Completed)

The video processing system converts downloaded videos to DVD-compatible formats using ffmpeg:

1. **DVD Format Conversion**: Converts videos to MPEG-2 with DVD-standard resolutions (720x480 NTSC/720x576 PAL)
2. **Audio Standardization**: Converts audio to AC-3 format with proper bitrates and sample rates for DVD compatibility
3. **Aspect Ratio Handling**: Automatically determines and applies appropriate DVD aspect ratios
4. **Frame Rate Conversion**: Handles NTSC (29.97fps) and PAL (25fps) frame rate conversion based on source material
5. **Thumbnail Generation**: Creates DVD menu thumbnails from video content
6. **Quality Validation**: Verifies converted files meet DVD specifications
7. **Intelligent Caching**: Caches converted files to avoid redundant processing
8. **Progress Reporting**: Provides detailed progress updates during conversion operations
9. **Atomic Operations**: Uses temporary files to ensure conversion integrity

The converter supports:
- Automatic format detection and DVD standard determination
- Batch processing of multiple videos
- Cache hit/miss optimization for faster subsequent conversions
- Comprehensive error handling with detailed logging
- Metadata tracking for converted files (codecs, resolution, duration, file size)
- Cleanup utilities for cache management

Key technical specifications:
- **Video**: MPEG-2 encoding at 6Mbps bitrate
- **Audio**: AC-3 encoding at 448kbps bitrate, stereo, 48kHz sample rate
- **Resolution**: 720x480 (NTSC) or 720x576 (PAL)
- **Aspect Ratio**: 4:3 standard DVD format
- **Thumbnails**: 160x120 pixel JPEG format for menu generation

### Coming Next

- **Phase 10**: DVD Authoring - Create DVD structure with menus and chapters
- **Phase 11**: CLI Interface - Complete command-line interface

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