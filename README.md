# DVD Maker

Convert YouTube playlists into physical DVDs.

## Features

- Download YouTube playlists using yt-dlp
- Convert videos to DVD-compatible format using ffmpeg
- Create DVD structure using dvdauthor
- Intelligent file caching to avoid redundant operations
- ASCII filename normalization for DVD compatibility
- Cross-platform support (Linux, macOS)

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

- `--output-dir`: Specify output directory
- `--quality`: Video quality preference
- `--menu-title`: Custom DVD menu title
- `--iso`: Generate ISO image
- `--temp-dir`: Temporary files location
- `--cache-dir`: Cache directory for downloaded/processed files
- `--force-download`: Force re-download even if cached
- `--force-convert`: Force re-conversion even if cached
- `--download-tools`: Download required tools to local bin directory
- `--use-system-tools`: Use system-installed tools instead of local bin

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