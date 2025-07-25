# DVD Maker Project Instructions

## Project Overview
This is a Python command-line tool that converts YouTube playlists into physical DVDs. The program downloads videos using yt-dlp, processes them with ffmpeg for DVD compatibility, and creates DVD structures using dvdauthor.

## Architecture & Code Style
- **Python Version**: 3.10+ with modern typing support
- **Architecture**: Modular design with clear separation of concerns
- **Structure**: Domain-specific modules (models, services, utils, config)
- **Typing**: Comprehensive type hints throughout codebase
- **Data Validation**: Use Pydantic models for data structures
- **Dependency Injection**: For testability and maintainability

## Development Environment
- Use virtual environment (venv) for dependency isolation: `python -m venv venv && source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt && pip install -r requirements-dev.txt`
- Code quality tools: Black (formatting), isort (imports), flake8 (linting), mypy (typing)
- Testing: pytest with >90% coverage requirement
- Use Makefile for common tasks: `make help` for available commands

## File Organization
```
src/
├── models/          # Data models and types (video.py, playlist.py, dvd.py)
├── services/        # Business logic (downloader.py, converter.py, dvd_author.py, cache_manager.py, tool_manager.py)
├── utils/           # Utilities (filename.py, platform.py, progress.py)
└── config/          # Configuration management (settings.py)
```

## Key Requirements
- **Tool Management**: Auto-download ffmpeg and yt-dlp to local bin/ directory
- **Caching**: Intelligent file caching with video ID as primary key
- **ASCII Normalization**: Convert filenames to ASCII for DVD compatibility
- **Rate Limiting**: Throttle yt-dlp downloads to 1MB/s
- **Platform Support**: Linux and macOS (Intel/Apple Silicon)
- **Progress Reporting**: Clear user feedback during operations

## Testing Standards
- Unit tests for all modules with mocking of external dependencies
- Test error conditions and edge cases
- Use pytest fixtures for test setup
- Maintain >90% test coverage

## Quality Checks
Use Makefile commands for development workflow:
```bash
make format    # Format code with black and isort
make lint      # Run flake8 linting
make typecheck # Run mypy type checking
make test      # Run tests with pytest
make coverage  # Run tests with coverage report
make check     # Run all quality checks (recommended before commits)
make clean     # Clean up generated files
```

## External Dependencies
- yt-dlp: YouTube video downloading (auto-downloadable)
- ffmpeg: Video processing (auto-downloadable)  
- dvdauthor: DVD creation (system installation required)

## Implementation Progress

**Important**: All implementation tasks and progress tracking are managed in `PLAN.md`. When completing tasks, always update the checkboxes in `PLAN.md` to mark items as complete `[x]`.

See `PLAN.md` for:
- Detailed 12-phase implementation plan
- Nested todo lists with specific tasks
- Dependencies between phases
- Estimated timeline
- Current progress status

## Logging Standards
- Use Python's logging module with structured JSON output
- Log to files with automatic rotation (10MB max, 5 backups)
- Support TRACE, DEBUG, INFO, WARNING, ERROR levels
- Include operation context and timing information
- Log all external tool invocations and outputs
- Use logger hierarchies (e.g., 'dvdmaker.downloader', 'dvdmaker.converter')
- Include correlation IDs for tracking operations across components
- Never log sensitive information (API keys, personal data)

### Logging Best Practices
- Use appropriate log levels:
  - TRACE: Detailed internal state and flow
  - DEBUG: Development debugging, detailed operations
  - INFO: Normal operation progress and results
  - WARNING: Recoverable issues, missing videos
  - ERROR: Unrecoverable errors requiring user intervention
- Include relevant context in log messages (video IDs, file paths, operation types)
- Use structured logging with consistent field names
- Log performance metrics for major operations
- Ensure all exceptions include full stack traces in logs

## Error Handling
- Graceful failure when tools unavailable
- Clear installation instructions for dvdauthor
- Atomic operations for file caching
- Proper cleanup of temporary files
- Comprehensive error logging with context