# DVD Maker - Product Requirements Document

## Overview
A Python command-line tool that converts YouTube playlists into physical DVDs by downloading videos, processing them for DVD compatibility, and authoring a complete DVD structure.

## Core Functionality

### 1. Video Download
- Use `yt-dlp` to download all videos from a YouTube playlist
- Support various video qualities and formats
- Handle playlist metadata (titles, descriptions, thumbnails) from yt-dlp only
- Provide download progress indication
- Maintain original playlist video ordering for DVD chapter sequence
- Handle missing/private videos gracefully with status logging
- Use latest playlist state for each run (detect playlist changes)

### 2. Video Processing
- Use `ffmpeg` to convert videos to DVD-compatible format (MPEG-2, 720x480/720x576)
- Ensure proper aspect ratios and frame rates
- Audio conversion to DVD standards (AC-3 or PCM)
- Generate thumbnails for DVD menus

### 3. DVD Authoring
- Use `dvdauthor` to create DVD structure with single title
- Generate interactive DVD menus
- Create chapter points for navigation where each playlist video becomes a chapter
- Combine all playlist videos into a single DVD title with sequential chapters
- Warn users when playlist exceeds DVD capacity (4.7GB single layer)
- Create DVDs with successfully downloaded videos (continue with partial playlists)

### 4. File Caching System
- Implement intelligent file caching to avoid redundant operations
- Skip download if video file already exists in cache
- Skip conversion if processed file already exists
- Use temporary naming/directory structure for in-progress operations
- Verify file integrity before considering cached files valid
- Leverage yt-dlp's built-in cache for authentication tokens and signatures
- Maintain filename mapping for ASCII normalization without duplicating files

### 5. Filename Normalization
- Convert non-ASCII characters to ASCII equivalents before DVD creation
- Maintain mapping between original video IDs and normalized filenames
- Ensure caching system uses original video IDs as keys
- Apply normalization only to final DVD structure, not cache files

### 6. Playlist Management
- Use YouTube playlist IDs (e.g., PLrAXtmRdnqeiGF0lEzfz7) as primary identifiers
- Cache playlist metadata alongside individual video metadata
- Maintain video ordering from original playlist
- Log status of missing/private/failed videos for user visibility
- Always use current playlist state (handle additions/removals between runs)

### 7. Concurrent Script Execution
- Support running multiple script instances concurrently for different playlists
- Share video-level caching between script runs (yt-dlp downloads and ffmpeg conversions)
- Use playlist-specific output directories for DVD authoring to prevent interference
- Isolate dvdauthor and ISO creation operations per playlist to avoid conflicts
- Implement file locking and atomic operations to prevent cache corruption
- Allow multiple script invocations to safely share download and conversion caches

### 8. Cache and Output Cleanup
- Provide granular cleanup options for different types of cached and output data
- Support cleaning downloads cache (yt-dlp downloaded video files)
- Support cleaning conversions cache (ffmpeg converted video files)
- Support cleaning DVD output directories (dvdauthor VIDEO_TS structures)
- Support cleaning ISO files (generated ISO images)
- Provide `--clean all` option to clean all cached and output data
- Preserve metadata and configuration files during cleanup operations
- Display cleanup progress and summary of freed space

## Technical Requirements

### Dependencies
- Python 3.10+ (for modern typing support)
- Virtual environment (venv) for dependency isolation
- `yt-dlp` for YouTube downloads (auto-downloadable)
- `ffmpeg` for video/audio processing (auto-downloadable)
- `dvdauthor` for DVD creation (system installation required)
- `mkisofs` for ISO image creation (system installation required)

### Python Packages
- **Runtime**: `unidecode`, `requests`, `pydantic`
- **Development**: `pytest`, `pytest-cov`, `black`, `isort`, `flake8`, `mypy`
- **Type stubs**: `types-requests`

### Tool Management
- Check for required tools before starting any operations
- Automatically download missing `ffmpeg` and `yt-dlp` to local `bin/` directory
- Use local tools by default, fallback to system PATH if needed
- Support Linux (x64) and macOS (Intel/Apple Silicon) platforms
- Download latest stable versions from official sources
- Provide clear installation instructions for `dvdauthor` if missing
- Display progress and status messages during tool validation/download

### yt-dlp Integration
- Use `--cache-dir` option to specify custom cache location
- Leverage built-in caching for authentication tokens and signatures
- Consider `--no-cache-dir` for troubleshooting authentication issues
- Use `--rm-cache-dir` for cache cleanup operations
- Apply `--limit-rate 1M` to throttle downloads to 1MB/s for respectful downloading

### Input
- YouTube playlist URL
- Optional configuration for video quality, menu styling
- Output directory specification

### Output
- Complete DVD folder structure (VIDEO_TS/)
- Optional ISO image generation
- Progress logging and error handling

## User Interface

### Command Line Interface
```bash
python dvdmaker.py --playlist-url URL [options]
```

Examples:
```bash
# Basic usage (creates both DVD structure and ISO)
python dvdmaker.py --playlist-url "https://www.youtube.com/playlist?list=PLxxx"

# Create only DVD structure without ISO
python dvdmaker.py --playlist-url "PLxxx" --no-iso

# Custom output and menu title
python dvdmaker.py --playlist-url "PLxxx" --output-dir ./my-dvd --menu-title "My Collection"

# Process multiple playlists concurrently (separate script invocations)
python dvdmaker.py --playlist-url "PLxxx" &
python dvdmaker.py --playlist-url "PLyyy" &
python dvdmaker.py --playlist-url "PLzzz" &
wait  # Wait for all background processes to complete

# Cleanup operations
python dvdmaker.py --clean downloads          # Clean downloaded video files
python dvdmaker.py --clean conversions       # Clean converted video files
python dvdmaker.py --clean dvd-output        # Clean DVD structure directories
python dvdmaker.py --clean isos              # Clean ISO image files
python dvdmaker.py --clean all               # Clean all cached and output data
```

### Options

#### Main Operations
- `--playlist-url`: YouTube playlist URL (required for DVD creation)
- `--clean`: Clean specific data type (downloads, conversions, dvd-output, isos, all)

#### DVD Creation Options
- `--output-dir`: Specify output directory
- `--quality`: Video quality preference
- `--menu-title`: Custom DVD menu title
- `--no-iso`: Skip ISO image generation (enabled by default)
- `--temp-dir`: Temporary files location
- `--cache-dir`: Cache directory for downloaded/processed files
- `--force-download`: Force re-download even if cached
- `--force-convert`: Force re-conversion even if cached

#### Tool Management
- `--download-tools`: Download required tools to local bin directory
- `--use-system-tools`: Use system-installed tools instead of local bin

#### Logging and Output
- `--log-level`: Set logging level (TRACE, DEBUG, INFO, WARNING, ERROR)
- `--log-file`: Specify log file path (default: logs/dvdmaker.log)
- `--verbose`: Enable verbose console output (equivalent to --log-level DEBUG)
- `--quiet`: Suppress all console output except errors

## Logging & Monitoring

### Logging Requirements
- **File Logging**: All operations logged to rotating log files in logs/ directory
- **Log Levels**: Support TRACE, DEBUG, INFO, WARNING, ERROR levels
- **Structured Logging**: JSON-formatted logs with timestamps, operation context, and metadata
- **Log Rotation**: Automatic rotation with size-based and time-based triggers
- **Performance Logging**: Execution times for major operations (download, conversion, authoring)
- **Error Logging**: Detailed error context with stack traces for debugging

### Log Content
- **Tool Operations**: All ffmpeg, yt-dlp, and dvdauthor command invocations and outputs
- **Cache Operations**: Cache hits/misses, file operations, integrity checks
- **Network Operations**: Download progress, retry attempts, rate limiting
- **File Operations**: File creation, movement, deletion, size verification
- **User Actions**: Command-line arguments, configuration loading, operation flow
- **System Information**: Platform detection, tool versions, system resources

### Console Output
- **INFO Level**: Progress updates, major operation status, completion messages
- **WARNING Level**: Non-fatal issues, missing videos, capacity warnings
- **ERROR Level**: Fatal errors, configuration issues, tool failures
- **Quiet Mode**: Only critical errors displayed to console
- **Verbose Mode**: Debug-level information displayed alongside file logging

## Success Criteria
- Successfully downloads complete playlists
- Generates playable DVDs on standard players
- Handles common error scenarios gracefully
- Provides clear progress feedback to users
- Maintains reasonable processing times

## File Organization

### Project Structure
```
dvdmaker/
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI entry point
│   ├── models/                # Data models and types
│   │   ├── __init__.py
│   │   ├── video.py           # Video metadata models
│   │   ├── playlist.py        # Playlist models
│   │   └── dvd.py             # DVD structure models
│   ├── services/              # Business logic services
│   │   ├── __init__.py
│   │   ├── downloader.py      # Video downloading logic
│   │   ├── converter.py       # Video conversion logic
│   │   ├── dvd_author.py      # DVD authoring logic
│   │   ├── cache_manager.py   # File caching logic
│   │   └── tool_manager.py    # Tool download/validation logic
│   ├── utils/                 # Utility functions
│   │   ├── __init__.py
│   │   ├── filename.py        # ASCII normalization utilities
│   │   ├── platform.py        # Platform detection utilities
│   │   ├── progress.py        # Progress reporting utilities
│   │   └── logging.py         # Logging configuration and utilities
│   └── config/                # Configuration management
│       ├── __init__.py
│       └── settings.py        # Application settings
├── tests/                     # Unit tests
│   ├── __init__.py
│   ├── test_models/
│   ├── test_services/
│   ├── test_utils/
│   └── test_config/
├── bin/                       # Downloaded tools
│   ├── ffmpeg
│   ├── yt-dlp
│   └── tool_versions.json
├── cache/                     # Runtime cache
│   ├── downloads/
│   ├── converted/
│   ├── metadata/
│   └── filename_mapping.json
├── output/                    # DVD output
│   ├── playlist_1/           # Output for first playlist
│   │   ├── VIDEO_TS/
│   │   └── playlist_1.iso
│   ├── playlist_2/           # Output for second playlist
│   │   ├── VIDEO_TS/
│   │   └── playlist_2.iso
│   └── ...
├── logs/                      # Application logs
│   ├── dvdmaker.log           # Main application log
│   ├── dvdmaker.log.1         # Rotated log files
│   └── debug/                 # Debug-level logs (when enabled)
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Development dependencies
├── setup.py                   # Package configuration
├── pyproject.toml            # Modern Python project config
├── pytest.ini               # Test configuration
├── .flake8                   # Linting configuration
├── .gitignore                # Git ignore patterns
└── README.md
```

### Cache Management
- Use video ID as primary cache key for shared caching between script runs
- Store file checksums for integrity verification
- Implement atomic operations (rename from .tmp on completion)
- Separate in-progress directory prevents incomplete files from being considered valid
- Metadata caching reduces API calls for playlist information
- Coordinate with yt-dlp's native cache for authentication data
- Maintain filename mapping to avoid file duplication during ASCII normalization
- Share download and conversion caches across concurrent script invocations
- Use playlist-specific output directories only for DVD authoring and ISO creation
- Implement file locking to prevent cache corruption during concurrent access

### Filename Normalization Strategy
- Cache files retain original names with video IDs
- Generate ASCII-safe filenames only for final DVD structure
- Store mapping in `filename_mapping.json` for consistency
- Use `unidecode` library for Unicode to ASCII conversion
- Truncate long filenames to filesystem limits while preserving uniqueness

### Tool Download Strategy
- Check `bin/tool_versions.json` for existing tool versions
- Download from official sources:
  - ffmpeg: https://github.com/BtbN/FFmpeg-Builds/releases (Linux), https://evermeet.cx/ffmpeg/ (macOS)
  - yt-dlp: https://github.com/yt-dlp/yt-dlp/releases
- Detect platform architecture (x64, arm64) and OS (Linux, macOS)
- Make downloaded binaries executable
- Verify tool functionality after download
- Update tools when newer versions are available

### Tool Validation Process
1. Check for tools in local `bin/` directory first
2. If missing, inform user and automatically download
3. For `dvdauthor` and `mkisofs`, check system PATH and provide installation instructions if missing:
   - macOS: "Install using: `brew install dvdauthor` and `brew install cdrtools`"
   - Linux: "Install using: `sudo apt install dvdauthor genisoimage` (Ubuntu/Debian) or `sudo yum install dvdauthor genisoimage` (RHEL/CentOS)"
4. Display clear status messages: "Checking tools...", "Downloading ffmpeg...", "Tools ready!"
5. Fail gracefully if required tools cannot be obtained

## Code Architecture

### Design Principles
- Use modern Python 3.10+ with comprehensive type hints
- Follow separation of concerns with domain-specific modules
- Implement dependency injection for testability
- Use dataclasses and Pydantic models for data validation
- Apply SOLID principles throughout the codebase

### Module Responsibilities
- **Models**: Define data structures with type validation
- **Services**: Implement core business logic with clear interfaces
- **Utils**: Provide reusable utility functions
- **Config**: Manage application configuration and settings
- **Main**: CLI interface and application orchestration

### Testing Strategy
- Unit tests for all modules with >90% coverage
- Mock external dependencies (file system, network calls)
- Test error conditions and edge cases
- Use pytest fixtures for test data and setup
- Separate integration tests for end-to-end workflows

### Development Environment
- Use virtual environment for dependency isolation:
  ```bash
  python -m venv venv
  source venv/bin/activate  # Linux/macOS
  # or venv\Scripts\activate  # Windows
  ```
- Install dependencies with pip:
  ```bash
  pip install -r requirements.txt
  pip install -r requirements-dev.txt
  ```

### Code Quality Tools
- **Black**: Code formatting with 88-character line length
- **isort**: Import sorting with Black compatibility
- **flake8**: Linting with E203, W503 exceptions for Black
- **mypy**: Static type checking with strict mode
- **pytest**: Testing framework with coverage reporting

### Development Workflow
```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/ tests/
mypy src/

# Run tests
pytest --cov=src --cov-report=html

# Full check (recommended before commits)
make check  # or equivalent script
```

## Constraints
- DVD capacity constraints (4.7GB single layer) with user warnings
- Video quality trade-offs for DVD format (no automatic quality adjustment)
- Dependency on external tools availability
- Cache storage requirements for large playlists
- Playlist changes between runs require re-processing