# DVD Maker Implementation Plan

## Phase 1: Project Setup & Infrastructure

### 1.1 Environment Setup
- [x] Create virtual environment (`python -m venv venv`)
- [x] Create requirements.txt with runtime dependencies
- [x] Create requirements-dev.txt with development dependencies
- [x] Create pyproject.toml for modern Python project configuration
- [x] Create setup.py for package configuration
- [x] Create .gitignore with Python and project-specific patterns

### 1.2 Development Tools Configuration
- [x] Create pytest.ini for test configuration
- [x] Create .flake8 for linting configuration
- [x] Create Makefile or scripts for common development tasks
- [ ] Set up pre-commit hooks (optional but recommended)

### 1.3 Project Structure
- [x] Create src/ directory with __init__.py
- [x] Create models/ package with __init__.py
- [x] Create services/ package with __init__.py
- [x] Create utils/ package with __init__.py
- [x] Create config/ package with __init__.py
- [x] Create tests/ directory with corresponding test packages
- [x] Create bin/, cache/, and output/ directories

## Phase 2: Core Models & Data Structures

### 2.1 Video Models (src/models/video.py)
- [x] Create VideoMetadata dataclass with type hints
  - [x] video_id: str
  - [x] title: str
  - [x] duration: int
  - [x] url: str
  - [x] thumbnail_url: Optional[str]
  - [x] description: Optional[str]
- [x] Create VideoFile dataclass
  - [x] metadata: VideoMetadata
  - [x] file_path: Path
  - [x] file_size: int
  - [x] checksum: str
  - [x] format: str

### 2.2 Playlist Models (src/models/playlist.py)
- [x] Create PlaylistMetadata dataclass
  - [x] playlist_id: str (YouTube playlist ID format)
  - [x] title: str
  - [x] description: Optional[str]
  - [x] video_count: int
  - [x] total_size_estimate: Optional[int] (for DVD capacity warnings)
- [x] Create VideoStatus enum for tracking video availability
  - [x] AVAILABLE, MISSING, PRIVATE, FAILED, DOWNLOADING, DOWNLOADED
- [x] Create Playlist dataclass
  - [x] metadata: PlaylistMetadata
  - [x] videos: List[VideoMetadata] (maintain original ordering)
  - [x] video_statuses: Dict[str, VideoStatus] (video_id -> status mapping)
- [x] Add playlist validation methods
  - [x] check_dvd_capacity() -> bool (warn if > 4.7GB)
  - [x] get_available_videos() -> List[VideoMetadata]
  - [x] get_failed_videos() -> List[VideoMetadata]

### 2.3 DVD Models (src/models/dvd.py)
- [x] Create DVDChapter dataclass
  - [x] chapter_number: int
  - [x] video_file: VideoFile
  - [x] start_time: int (for concatenated video)
- [x] Create DVDStructure dataclass
  - [x] chapters: List[DVDChapter] (single title with multiple chapters)
  - [x] menu_title: str
  - [x] total_size: int

## Phase 3: Utility Functions

### 3.1 Platform Detection (src/utils/platform.py)
- [x] Create function to detect OS (Linux, macOS, Windows)
- [x] Create function to detect architecture (x64, arm64)
- [x] Create function to get platform-specific download URLs
- [x] Add type hints and error handling

### 3.2 Filename Utilities (src/utils/filename.py)
- [x] Create ASCII normalization function using unidecode
- [x] Create filename sanitization function
- [x] Create unique filename generation function
- [x] Create filename mapping management functions
- [x] Add comprehensive test coverage

### 3.3 Progress Reporting (src/utils/progress.py)
- [x] Create progress callback interface
- [x] Create console progress reporter
- [x] Create progress aggregation for multi-step operations
- [x] Add cancellation support

## Phase 4: Logging Infrastructure

### 4.1 Logging Utilities (src/utils/logging.py)
- [x] Create logging configuration with JSON formatting
- [x] Implement TRACE log level support
- [x] Create rotating file handler with size and time-based rotation
- [x] Add structured logging with correlation IDs
- [x] Create context managers for operation logging
- [x] Implement performance timing decorators
- [x] Add log filtering for sensitive information
- [x] Create console and file output handlers

### 4.2 Logger Integration
- [x] Set up hierarchical loggers for each module
- [x] Create logging mixins for service classes
- [x] Add operation context tracking
- [x] Implement log aggregation utilities
- [x] Create debug logging helpers
- [x] Add error context preservation

## Phase 5: Configuration Management

### 5.1 Settings (src/config/settings.py)
- [x] Create Settings dataclass with Pydantic validation
  - [x] cache_dir: Path
  - [x] output_dir: Path
  - [x] temp_dir: Path
  - [x] bin_dir: Path
  - [x] log_dir: Path
  - [x] log_level: str
  - [x] log_file_max_size: int
  - [x] log_file_backup_count: int
  - [x] download_rate_limit: str
  - [x] video_quality: str
- [x] Create configuration loading from files/environment
- [x] Create configuration validation

## Phase 6: Tool Management

### 6.1 Tool Manager (src/services/tool_manager.py)
- [x] Create ToolManager class with dependency injection
- [x] Implement tool version checking
  - [x] Load tool_versions.json
  - [x] Check local bin/ directory for tools
  - [x] Verify tool functionality
- [x] Implement automatic tool downloading
  - [x] Download ffmpeg from official sources
  - [x] Download yt-dlp from GitHub releases
  - [x] Handle platform-specific binaries
  - [x] Make downloaded files executable
  - [x] Update tool_versions.json
- [x] Implement dvdauthor validation
  - [x] Check system PATH for dvdauthor
  - [x] Provide installation instructions if missing
- [ ] Implement mkisofs validation
  - [ ] Check system PATH for mkisofs/genisoimage
  - [ ] Provide installation instructions if missing (macOS: `brew install cdrtools`, Linux: `sudo apt install genisoimage`)
- [x] Add comprehensive error handling and user messaging

### 6.2 Tool Manager Tests
- [x] Test tool detection logic
- [x] Test download functionality with mocked HTTP requests
- [x] Test platform detection
- [x] Test error scenarios (network failures, permission issues)
- [x] Test tool validation

## Phase 7: Cache Management

### 7.1 Cache Manager (src/services/cache_manager.py)
- [x] Create CacheManager class
- [x] Implement cache directory structure management
  - [x] Create downloads/, converted/, metadata/ directories
  - [x] Create .in-progress/ subdirectories
- [x] Implement file caching logic
  - [x] Check cache using video ID as key
  - [x] Verify file integrity with checksums
  - [x] Handle atomic operations with .tmp files
- [x] Implement filename mapping persistence
  - [x] Load/save filename_mapping.json
  - [x] Maintain original to ASCII mappings
- [x] Add cache cleanup and maintenance functions

### 7.2 Cache Manager Tests
- [x] Test cache hit/miss logic
- [x] Test atomic file operations
- [x] Test filename mapping persistence
- [x] Test cache cleanup
- [x] Test error recovery

## Phase 8: Video Downloading

### 8.1 Downloader Service (src/services/downloader.py)
- [x] Create VideoDownloader class
- [x] Implement yt-dlp integration
  - [x] Configure yt-dlp options (cache-dir, limit-rate, etc.)
  - [x] Handle playlist extraction (maintain original video ordering)
  - [x] Download individual videos
  - [x] Extract metadata from yt-dlp only
  - [x] Handle missing/private videos gracefully with status logging
  - [x] Detect and handle playlist changes between runs
- [x] Implement caching integration
  - [x] Check cache before downloading
  - [x] Store downloads in cache
  - [x] Handle in-progress downloads
- [x] Add progress reporting
- [x] Add comprehensive error handling for partial playlist success

### 8.2 Downloader Tests
- [x] Test playlist extraction with mocked yt-dlp
- [x] Test video downloading with cache integration
- [x] Test progress reporting
- [x] Test error scenarios (missing/private videos)
- [x] Test rate limiting
- [x] Test playlist change detection
- [x] Test partial playlist success scenarios

## Phase 9: Video Processing

### 9.1 Video Converter (src/services/converter.py)
- [x] Create VideoConverter class
- [x] Implement ffmpeg integration
  - [x] Convert to DVD-compatible formats (MPEG-2)
  - [x] Handle aspect ratio and frame rate conversion
  - [x] Convert audio to DVD standards
  - [x] Generate thumbnails for menus
- [x] Implement caching for converted files
- [x] Add progress reporting for conversion
- [x] Add quality validation for converted files

### 9.2 Converter Tests
- [x] Test video format conversion with mocked ffmpeg
- [x] Test audio conversion
- [x] Test thumbnail generation
- [x] Test cache integration
- [x] Test error handling

## Phase 10: DVD Authoring

### 10.1 DVD Author Service (src/services/dvd_author.py)
- [x] Create DVDAuthor class
- [x] Implement dvdauthor integration
  - [x] Create DVD menu structure
  - [x] Generate VIDEO_TS directory structure
  - [x] Handle multiple videos as chapters in single title (maintain playlist order)
  - [x] Apply ASCII filename normalization
  - [x] Warn users when playlist exceeds DVD capacity (4.7GB)
  - [x] Create DVDs with successfully processed videos only
- [x] Implement ISO generation using mkisofs command `mkisofs -dvd-video -o mydisc.iso dvd`
- [x] Add validation of final DVD structure

### 10.2 DVD Author Tests
- [x] Test DVD structure creation with mocked dvdauthor
- [x] Test menu generation
- [x] Test filename normalization integration
- [x] Test ISO generation
- [x] Test validation logic
- [x] Test DVD capacity warnings
- [x] Test partial playlist DVD creation

## Phase 11: CLI Interface

### 11.1 Main CLI (src/main.py)
- [x] Create argument parser with all required options
- [x] Implement tool validation at startup
- [x] Orchestrate the complete workflow
  - [x] Tool validation/download
  - [x] Playlist download
  - [x] Video conversion
  - [x] DVD authoring
- [x] Add comprehensive logging
- [x] Add user-friendly error messages and progress updates

### 11.2 CLI Tests
- [x] Test argument parsing
- [x] Test workflow orchestration with mocked services
- [x] Test error handling and user messaging
- [x] Test tool validation flow

## Phase 12: ISO Creation Enhancement

### 12.1 Update Tool Manager for mkisofs
- [x] Add mkisofs/genisoimage tool validation to ToolManager
- [x] Implement system PATH checking for mkisofs
- [x] Add installation instructions for mkisofs
  - [x] macOS: `brew install dvdrtools` (includes mkisofs)
  - [x] Linux: `sudo apt install genisoimage` (Ubuntu/Debian) or `sudo yum install genisoimage` (RHEL/CentOS)
- [x] Update tool validation process to include mkisofs

### 12.2 Update DVD Author Service
- [x] Modify `_create_iso` method to use mkisofs and genisoimage (fallback support)
- [x] Implement mkisofs command: `mkisofs -dvd-video -o output.iso input_directory`
- [x] Update error handling for mkisofs-specific errors
- [x] Test ISO creation with mkisofs command
- [x] Enable ISO creation by default (change default generate_iso setting)

### 12.3 Update Tests
- [x] Add mkisofs validation tests to tool manager tests
- [x] Update DVD author ISO creation tests for mkisofs
- [x] Test error scenarios when mkisofs is not available

## Phase 13: Integration Testing

### 13.1 End-to-End Tests
- [ ] Create integration test with small test playlist
- [ ] Test complete workflow with mocked external tools
- [ ] Test error recovery scenarios
- [ ] Test caching behavior across multiple runs
- [ ] Performance testing with larger playlists

### 13.2 Documentation
- [ ] Update README.md with installation and usage instructions
- [ ] Create examples and troubleshooting guide
- [ ] Document configuration options
- [ ] Create development setup guide

## Phase 14: Quality Assurance

### 14.1 Code Quality
- [ ] Achieve >90% test coverage
- [ ] Pass all linting checks (flake8, mypy)
- [ ] Format all code with Black and isort
- [ ] Review and refactor for SOLID principles
- [ ] Add comprehensive docstrings

### 14.2 Final Testing
- [ ] Test on Linux and macOS platforms
- [ ] Test with various playlist sizes
- [ ] Test error scenarios and recovery
- [ ] Validate DVD compatibility with players
- [ ] Performance optimization if needed

## Estimated Timeline
- **Phase 1-3**: 2-3 days (Setup, models, and utilities)
- **Phase 4**: 1 day (Logging infrastructure)
- **Phase 5**: 1 day (Configuration management)
- **Phase 6**: 2-3 days (Tool management)
- **Phase 7**: 2 days (Cache management)
- **Phase 8**: 2-3 days (Video downloading)
- **Phase 9**: 2-3 days (Video processing)
- **Phase 10**: 2-3 days (DVD authoring)
- **Phase 11**: 1-2 days (CLI interface)
- **Phase 12**: 1 day (ISO creation enhancement)
- **Phase 13-14**: 2-3 days (Testing and QA)

**Total Estimated Time**: 17-25 days

## Dependencies Between Phases
- Phase 2 depends on Phase 1
- Phases 3-4 can be done in parallel with Phase 2
- Phase 5 depends on Phase 4
- Phase 6 depends on Phases 4-5
- Phase 7 depends on Phase 2
- Phases 8-10 depend on Phases 6-7
- Phase 11 depends on Phases 8-10
- Phase 12 depends on Phases 6 and 10 (tool management and DVD authoring)
- Phases 13-14 depend on all previous phases