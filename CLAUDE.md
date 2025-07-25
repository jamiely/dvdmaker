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
- Use virtual environment (venv) for dependency isolation
- Standard pip dependency management with requirements.txt and requirements-dev.txt
- Code quality tools: Black (formatting), isort (imports), flake8 (linting), mypy (typing)
- Testing: pytest with >90% coverage requirement

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
Before commits, always run:
```bash
black src/ tests/
isort src/ tests/
flake8 src/ tests/
mypy src/
pytest --cov=src
```

## External Dependencies
- yt-dlp: YouTube video downloading (auto-downloadable)
- ffmpeg: Video processing (auto-downloadable)  
- dvdauthor: DVD creation (system installation required)

## Error Handling
- Graceful failure when tools unavailable
- Clear installation instructions for dvdauthor
- Atomic operations for file caching
- Proper cleanup of temporary files