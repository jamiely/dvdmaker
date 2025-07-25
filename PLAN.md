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
- [ ] Create logging configuration with JSON formatting
- [ ] Implement TRACE log level support
- [ ] Create rotating file handler with size and time-based rotation
- [ ] Add structured logging with correlation IDs
- [ ] Create context managers for operation logging
- [ ] Implement performance timing decorators
- [ ] Add log filtering for sensitive information
- [ ] Create console and file output handlers

### 4.2 Logger Integration
- [ ] Set up hierarchical loggers for each module
- [ ] Create logging mixins for service classes
- [ ] Add operation context tracking
- [ ] Implement log aggregation utilities
- [ ] Create debug logging helpers
- [ ] Add error context preservation

## Phase 5: Configuration Management

### 5.1 Settings (src/config/settings.py)
- [ ] Create Settings dataclass with Pydantic validation
  - [ ] cache_dir: Path
  - [ ] output_dir: Path
  - [ ] temp_dir: Path
  - [ ] bin_dir: Path
  - [ ] log_dir: Path
  - [ ] log_level: str
  - [ ] log_file_max_size: int
  - [ ] log_file_backup_count: int
  - [ ] download_rate_limit: str
  - [ ] video_quality: str
- [ ] Create configuration loading from files/environment
- [ ] Create configuration validation

## Phase 6: Tool Management

### 6.1 Tool Manager (src/services/tool_manager.py)
- [ ] Create ToolManager class with dependency injection
- [ ] Implement tool version checking
  - [ ] Load tool_versions.json
  - [ ] Check local bin/ directory for tools
  - [ ] Verify tool functionality
- [ ] Implement automatic tool downloading
  - [ ] Download ffmpeg from official sources
  - [ ] Download yt-dlp from GitHub releases
  - [ ] Handle platform-specific binaries
  - [ ] Make downloaded files executable
  - [ ] Update tool_versions.json
- [ ] Implement dvdauthor validation
  - [ ] Check system PATH for dvdauthor
  - [ ] Provide installation instructions if missing
- [ ] Add comprehensive error handling and user messaging

### 6.2 Tool Manager Tests
- [ ] Test tool detection logic
- [ ] Test download functionality with mocked HTTP requests
- [ ] Test platform detection
- [ ] Test error scenarios (network failures, permission issues)
- [ ] Test tool validation

## Phase 7: Cache Management

### 7.1 Cache Manager (src/services/cache_manager.py)
- [ ] Create CacheManager class
- [ ] Implement cache directory structure management
  - [ ] Create downloads/, converted/, metadata/ directories
  - [ ] Create .in-progress/ subdirectories
- [ ] Implement file caching logic
  - [ ] Check cache using video ID as key
  - [ ] Verify file integrity with checksums
  - [ ] Handle atomic operations with .tmp files
- [ ] Implement filename mapping persistence
  - [ ] Load/save filename_mapping.json
  - [ ] Maintain original to ASCII mappings
- [ ] Add cache cleanup and maintenance functions

### 7.2 Cache Manager Tests
- [ ] Test cache hit/miss logic
- [ ] Test atomic file operations
- [ ] Test filename mapping persistence
- [ ] Test cache cleanup
- [ ] Test error recovery

## Phase 8: Video Downloading

### 8.1 Downloader Service (src/services/downloader.py)
- [ ] Create VideoDownloader class
- [ ] Implement yt-dlp integration
  - [ ] Configure yt-dlp options (cache-dir, limit-rate, etc.)
  - [ ] Handle playlist extraction (maintain original video ordering)
  - [ ] Download individual videos
  - [ ] Extract metadata from yt-dlp only
  - [ ] Handle missing/private videos gracefully with status logging
  - [ ] Detect and handle playlist changes between runs
- [ ] Implement caching integration
  - [ ] Check cache before downloading
  - [ ] Store downloads in cache
  - [ ] Handle in-progress downloads
- [ ] Add progress reporting
- [ ] Add comprehensive error handling for partial playlist success

### 8.2 Downloader Tests
- [ ] Test playlist extraction with mocked yt-dlp
- [ ] Test video downloading with cache integration
- [ ] Test progress reporting
- [ ] Test error scenarios (missing/private videos)
- [ ] Test rate limiting
- [ ] Test playlist change detection
- [ ] Test partial playlist success scenarios

## Phase 9: Video Processing

### 9.1 Video Converter (src/services/converter.py)
- [ ] Create VideoConverter class
- [ ] Implement ffmpeg integration
  - [ ] Convert to DVD-compatible formats (MPEG-2)
  - [ ] Handle aspect ratio and frame rate conversion
  - [ ] Convert audio to DVD standards
  - [ ] Generate thumbnails for menus
- [ ] Implement caching for converted files
- [ ] Add progress reporting for conversion
- [ ] Add quality validation for converted files

### 9.2 Converter Tests
- [ ] Test video format conversion with mocked ffmpeg
- [ ] Test audio conversion
- [ ] Test thumbnail generation
- [ ] Test cache integration
- [ ] Test error handling

## Phase 10: DVD Authoring

### 10.1 DVD Author Service (src/services/dvd_author.py)
- [ ] Create DVDAuthor class
- [ ] Implement dvdauthor integration
  - [ ] Create DVD menu structure
  - [ ] Generate VIDEO_TS directory structure
  - [ ] Handle multiple videos as chapters in single title (maintain playlist order)
  - [ ] Apply ASCII filename normalization
  - [ ] Warn users when playlist exceeds DVD capacity (4.7GB)
  - [ ] Create DVDs with successfully processed videos only
- [ ] Implement ISO generation (optional)
- [ ] Add validation of final DVD structure

### 10.2 DVD Author Tests
- [ ] Test DVD structure creation with mocked dvdauthor
- [ ] Test menu generation
- [ ] Test filename normalization integration
- [ ] Test ISO generation
- [ ] Test validation logic
- [ ] Test DVD capacity warnings
- [ ] Test partial playlist DVD creation

## Phase 11: CLI Interface

### 11.1 Main CLI (src/main.py)
- [ ] Create argument parser with all required options
- [ ] Implement tool validation at startup
- [ ] Orchestrate the complete workflow
  - [ ] Tool validation/download
  - [ ] Playlist download
  - [ ] Video conversion
  - [ ] DVD authoring
- [ ] Add comprehensive logging
- [ ] Add user-friendly error messages and progress updates

### 11.2 CLI Tests
- [ ] Test argument parsing
- [ ] Test workflow orchestration with mocked services
- [ ] Test error handling and user messaging
- [ ] Test tool validation flow

## Phase 12: Integration Testing

### 12.1 End-to-End Tests
- [ ] Create integration test with small test playlist
- [ ] Test complete workflow with mocked external tools
- [ ] Test error recovery scenarios
- [ ] Test caching behavior across multiple runs
- [ ] Performance testing with larger playlists

### 12.2 Documentation
- [ ] Update README.md with installation and usage instructions
- [ ] Create examples and troubleshooting guide
- [ ] Document configuration options
- [ ] Create development setup guide

## Phase 13: Quality Assurance

### 13.1 Code Quality
- [ ] Achieve >90% test coverage
- [ ] Pass all linting checks (flake8, mypy)
- [ ] Format all code with Black and isort
- [ ] Review and refactor for SOLID principles
- [ ] Add comprehensive docstrings

### 13.2 Final Testing
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
- **Phase 12-13**: 2-3 days (Testing and QA)

**Total Estimated Time**: 16-24 days

## Dependencies Between Phases
- Phase 2 depends on Phase 1
- Phases 3-4 can be done in parallel with Phase 2
- Phase 5 depends on Phase 4
- Phase 6 depends on Phases 4-5
- Phase 7 depends on Phase 2
- Phases 8-10 depend on Phases 6-7
- Phase 11 depends on Phases 8-10
- Phases 12-13 depend on all previous phases