"""Tests for video downloader service."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.models.playlist import Playlist, PlaylistMetadata, VideoStatus
from src.models.video import VideoFile, VideoMetadata
from src.services.cache_manager import CacheManager
from src.services.downloader import VideoDownloader, YtDlpError
from src.services.tool_manager import ToolManager


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.cache_dir = Path("/test/cache")
    settings.temp_dir = Path("/test/temp")
    settings.download_rate_limit = "1M"
    settings.video_quality = "best"
    return settings


@pytest.fixture
def mock_cache_manager():
    """Create mock cache manager for testing."""
    return Mock(spec=CacheManager)


@pytest.fixture
def mock_tool_manager():
    """Create mock tool manager for testing."""
    tool_manager = Mock(spec=ToolManager)
    tool_manager.is_tool_available_locally.return_value = True
    tool_manager.get_tool_path.return_value = Path("/test/bin/yt-dlp")
    tool_manager.get_tool_command.return_value = ["/test/bin/yt-dlp"]
    return tool_manager


@pytest.fixture
def downloader(mock_settings, mock_cache_manager, mock_tool_manager):
    """Create video downloader instance for testing."""
    return VideoDownloader(mock_settings, mock_cache_manager, mock_tool_manager)


@pytest.fixture
def sample_video_metadata():
    """Create sample video metadata for testing."""
    return VideoMetadata(
        video_id="test_video_id",
        title="Test Video",
        duration=300,
        url="https://youtube.com/watch?v=test_video_id",
        thumbnail_url="https://img.youtube.com/vi/test_video_id/default.jpg",
        description="Test video description",
    )


@pytest.fixture
def sample_playlist_metadata():
    """Create sample playlist metadata for testing."""
    return PlaylistMetadata(
        playlist_id="test_playlist_id",
        title="Test Playlist",
        description="Test playlist description",
        video_count=2,
        total_size_estimate=1000000,  # 1MB
    )


@pytest.fixture
def sample_playlist(sample_playlist_metadata, sample_video_metadata):
    """Create sample playlist for testing."""
    videos = [
        sample_video_metadata,
        VideoMetadata(
            video_id="test_video_id_2",
            title="Test Video 2",
            duration=200,
            url="https://youtube.com/watch?v=test_video_id_2",
        ),
    ]
    video_statuses = {video.video_id: VideoStatus.AVAILABLE for video in videos}
    return Playlist(
        metadata=sample_playlist_metadata,
        videos=videos,
        video_statuses=video_statuses,
    )


class TestVideoDownloader:
    """Test VideoDownloader class."""

    def test_init(self, mock_settings, mock_cache_manager, mock_tool_manager):
        """Test downloader initialization."""
        downloader = VideoDownloader(
            mock_settings, mock_cache_manager, mock_tool_manager
        )

        assert downloader.settings == mock_settings
        assert downloader.cache_manager == mock_cache_manager
        assert downloader.tool_manager == mock_tool_manager
        # yt_dlp_path is no longer stored as an attribute

    def test_ensure_yt_dlp_available_cached(self, downloader):
        """Test ensuring yt-dlp is available when already cached."""
        # Mock tool manager to indicate yt-dlp is available locally
        downloader.tool_manager.is_tool_available_locally.return_value = True

        # Should not raise any exception
        downloader._ensure_yt_dlp_available()

        # Verify tool manager was called correctly
        downloader.tool_manager.is_tool_available_locally.assert_called_with("yt-dlp")
        downloader.tool_manager.get_tool_command.assert_called_with("yt-dlp")

    def test_ensure_yt_dlp_available_download_needed(self, downloader):
        """Test ensuring yt-dlp is available when download is needed."""
        downloader.tool_manager.is_tool_available_locally.return_value = False

        # Should not raise any exception
        downloader._ensure_yt_dlp_available()

        downloader.tool_manager.is_tool_available_locally.assert_called_once_with(
            "yt-dlp"
        )
        downloader.tool_manager.download_tool.assert_called_once_with("yt-dlp")
        downloader.tool_manager.get_tool_command.assert_called_with("yt-dlp")

    def test_ensure_yt_dlp_available_failure(self, downloader):
        """Test ensuring yt-dlp available when download fails."""
        downloader.tool_manager.is_tool_available_locally.return_value = False
        downloader.tool_manager.get_tool_command.side_effect = Exception(
            "Tool not found"
        )

        with pytest.raises(RuntimeError, match="yt-dlp is not available"):
            downloader._ensure_yt_dlp_available()

    @patch("subprocess.run")
    def test_run_yt_dlp_success(self, mock_run, downloader):
        """Test successful yt-dlp command execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        with patch.object(downloader, "_ensure_yt_dlp_available"):
            result = downloader._run_yt_dlp(["--version"])

        assert result == mock_result
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_yt_dlp_failure(self, mock_run, downloader):
        """Test failed yt-dlp command execution."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error message"
        mock_run.return_value = mock_result

        with patch.object(downloader, "_ensure_yt_dlp_available"):
            with pytest.raises(YtDlpError, match="yt-dlp failed with return code 1"):
                downloader._run_yt_dlp(["--version"])

    @patch("subprocess.run")
    def test_run_yt_dlp_timeout(self, mock_run, downloader):
        """Test yt-dlp command timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        with patch.object(downloader, "_ensure_yt_dlp_available"):
            with pytest.raises(YtDlpError, match="Command timed out"):
                downloader._run_yt_dlp(["--version"], timeout=30)

    def test_get_base_yt_dlp_args(self, downloader):
        """Test getting base yt-dlp arguments."""
        args = downloader._get_base_yt_dlp_args()

        assert "--no-warnings" in args
        assert "--limit-rate" in args
        assert "1M" in args
        assert "--cache-dir" in args
        # --extract-flat and --dump-json are not in base args anymore
        # as they are added only when needed

    def test_extract_playlist_id_standard_format(self, downloader):
        """Test extracting playlist ID from standard URL format."""
        url = "https://www.youtube.com/watch?v=video123&list=PLtest123"
        result = downloader._extract_playlist_id(url)
        assert result == "PLtest123"

    def test_extract_playlist_id_playlist_url(self, downloader):
        """Test extracting playlist ID from direct playlist URL."""
        url = "https://www.youtube.com/playlist?list=PLtest456"
        result = downloader._extract_playlist_id(url)
        assert result == "PLtest456"

    def test_extract_playlist_id_short_url(self, downloader):
        """Test extracting playlist ID from short URL."""
        url = "https://youtu.be/video123?list=PLtest789"
        result = downloader._extract_playlist_id(url)
        assert result == "PLtest789"

    def test_extract_playlist_id_invalid_url(self, downloader):
        """Test extracting playlist ID from invalid URL."""
        url = "https://www.example.com/invalid"

        with pytest.raises(ValueError, match="Invalid YouTube playlist URL"):
            downloader._extract_playlist_id(url)

    def test_validate_url_valid(self, downloader):
        """Test URL validation with valid playlist URL."""
        url = "https://www.youtube.com/playlist?list=PLtest123"
        assert downloader.validate_url(url) is True

    def test_validate_url_invalid(self, downloader):
        """Test URL validation with invalid URL."""
        url = "https://www.example.com/invalid"
        assert downloader.validate_url(url) is False

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_metadata_success(
        self, mock_run, downloader, sample_playlist_metadata
    ):
        """Test successful playlist metadata extraction."""
        # Mock cached metadata not found
        downloader.cache_manager.get_cached_playlist_metadata.return_value = None

        # Mock yt-dlp output
        mock_result = Mock()
        playlist_json = {
            "title": sample_playlist_metadata.title,
            "description": sample_playlist_metadata.description,
        }
        video_json = {"id": "video1", "title": "Video 1"}
        raw_json_output = f"{json.dumps(playlist_json)}\n{json.dumps(video_json)}"
        mock_result.stdout = raw_json_output
        mock_run.return_value = mock_result

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.extract_playlist_metadata(url)

        assert result.playlist_id == "test_playlist_id"
        assert result.title == sample_playlist_metadata.title
        assert result.description == sample_playlist_metadata.description
        assert result.video_count == 1  # One video line
        downloader.cache_manager.store_playlist_metadata.assert_called_once()
        # Verify raw JSON was cached
        downloader.cache_manager.store_playlist_raw_json.assert_called_once_with(
            "test_playlist_id", raw_json_output
        )

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_metadata_cached(
        self, mock_run, downloader, sample_playlist_metadata
    ):
        """Test playlist metadata extraction using cached data."""
        # Mock cached metadata found
        downloader.cache_manager.get_cached_playlist_metadata.return_value = (
            sample_playlist_metadata
        )

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.extract_playlist_metadata(url)

        assert result == sample_playlist_metadata
        mock_run.assert_not_called()  # Should not call yt-dlp when cached

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_videos_success(self, mock_run, downloader):
        """Test successful playlist video extraction."""
        # Mock no cached raw JSON
        downloader.cache_manager.get_cached_playlist_raw_json.return_value = None

        # Mock yt-dlp output
        mock_result = Mock()
        playlist_json = {"title": "Test Playlist"}
        video1_json = {
            "id": "video1",
            "title": "Video 1",
            "duration": 300,
            "url": "https://youtube.com/watch?v=video1",
            "thumbnail": "https://img.youtube.com/vi/video1/default.jpg",
            "description": "Video 1 description",
        }
        video2_json = {
            "id": "video2",
            "title": "Video 2",
            "duration": 200,
            "url": "https://youtube.com/watch?v=video2",
        }
        raw_json_output = (
            f"{json.dumps(playlist_json)}\n"
            f"{json.dumps(video1_json)}\n"
            f"{json.dumps(video2_json)}"
        )
        mock_result.stdout = raw_json_output
        mock_run.return_value = mock_result

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.extract_playlist_videos(url)

        assert len(result) == 2
        assert result[0].video_id == "video1"
        assert result[0].title == "Video 1"
        assert result[0].duration == 300
        assert result[1].video_id == "video2"
        assert result[1].title == "Video 2"
        assert result[1].duration == 200
        # Verify raw JSON was cached
        downloader.cache_manager.store_playlist_raw_json.assert_called_once_with(
            "test_playlist_id", raw_json_output
        )

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_videos_cached_raw_json(self, mock_run, downloader):
        """Test playlist video extraction using cached raw JSON."""
        # Mock cached raw JSON found
        cached_raw_json = (
            '{"title": "Cached Playlist"}\n'
            '{"id": "cached_video1", "title": "Cached Video 1", "duration": 150, '
            '"url": "https://youtube.com/watch?v=cached_video1"}\n'
            '{"id": "cached_video2", "title": "Cached Video 2", "duration": 250, '
            '"url": "https://youtube.com/watch?v=cached_video2"}'
        )
        downloader.cache_manager.get_cached_playlist_raw_json.return_value = (
            cached_raw_json
        )

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.extract_playlist_videos(url)

        assert len(result) == 2
        assert result[0].video_id == "cached_video1"
        assert result[0].title == "Cached Video 1"
        assert result[0].duration == 150
        assert result[0].url == "https://youtube.com/watch?v=cached_video1"
        assert result[1].video_id == "cached_video2"
        assert result[1].title == "Cached Video 2"
        assert result[1].duration == 250
        assert result[1].url == "https://youtube.com/watch?v=cached_video2"

        # yt-dlp should not be called when using cached raw JSON
        mock_run.assert_not_called()
        # store_playlist_raw_json should not be called when using cached data
        downloader.cache_manager.store_playlist_raw_json.assert_not_called()

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_videos_empty(self, mock_run, downloader):
        """Test playlist video extraction with empty playlist."""
        # Mock no cached raw JSON
        downloader.cache_manager.get_cached_playlist_raw_json.return_value = None

        # Mock yt-dlp output with only playlist metadata
        mock_result = Mock()
        playlist_json = {"title": "Empty Playlist"}
        mock_result.stdout = json.dumps(playlist_json)
        mock_run.return_value = mock_result

        url = "https://www.youtube.com/playlist?list=empty_playlist"

        with pytest.raises(YtDlpError, match="Playlist appears to be empty"):
            downloader.extract_playlist_videos(url)

    @patch.object(VideoDownloader, "extract_playlist_metadata")
    @patch.object(VideoDownloader, "extract_playlist_videos")
    def test_extract_full_playlist_success(
        self, mock_videos, mock_metadata, downloader, sample_playlist_metadata
    ):
        """Test successful full playlist extraction."""
        # Mock methods
        mock_metadata.return_value = sample_playlist_metadata
        mock_videos.return_value = [
            VideoMetadata(
                video_id="video1",
                title="Video 1",
                duration=300,
                url="https://youtube.com/watch?v=video1",
            ),
            VideoMetadata(
                video_id="video2",
                title="Video 2",
                duration=200,
                url="https://youtube.com/watch?v=video2",
            ),
        ]

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.extract_full_playlist(url)

        assert result.metadata.playlist_id == "test_playlist_id"
        assert len(result.videos) == 2
        assert len(result.video_statuses) == 2
        assert all(
            status == VideoStatus.AVAILABLE for status in result.video_statuses.values()
        )

    @patch.object(VideoDownloader, "_run_yt_dlp")
    @patch("tempfile.TemporaryDirectory")
    @patch("pathlib.Path.glob")
    def test_download_video_success(
        self,
        mock_glob,
        mock_temp_dir,
        mock_run,
        downloader,
        sample_video_metadata,
        sample_playlist,
    ):
        """Test successful video download."""
        # Mock cache miss
        downloader.cache_manager.get_cached_download.return_value = None

        # Mock temporary directory
        temp_path = Path("/tmp/test_download")
        mock_temp_dir.return_value.__enter__.return_value = str(temp_path)

        # Mock downloaded file
        downloaded_file = temp_path / "test_video_id.mp4"
        mock_glob.return_value = [downloaded_file]

        # Mock successful yt-dlp run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Mock cache storage
        mock_video_file = Mock(spec=VideoFile)
        mock_video_file.size_mb = 10.5
        downloader.cache_manager.store_download.return_value = mock_video_file

        result = downloader.download_video(sample_video_metadata, sample_playlist)

        assert result is True
        downloader.cache_manager.store_download.assert_called_once()
        assert sample_playlist.video_statuses["test_video_id"] == VideoStatus.DOWNLOADED

    def test_download_video_cached(
        self, downloader, sample_video_metadata, sample_playlist
    ):
        """Test video download with cached file."""
        # Mock cache hit
        mock_video_file = Mock(spec=VideoFile)
        downloader.cache_manager.get_cached_download.return_value = mock_video_file

        result = downloader.download_video(sample_video_metadata, sample_playlist)

        assert result is True
        assert sample_playlist.video_statuses["test_video_id"] == VideoStatus.DOWNLOADED

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_download_video_yt_dlp_failure(
        self, mock_run, downloader, sample_video_metadata, sample_playlist
    ):
        """Test video download with yt-dlp failure."""
        # Mock cache miss
        downloader.cache_manager.get_cached_download.return_value = None

        # Mock yt-dlp failure
        mock_run.side_effect = YtDlpError("Download failed")

        result = downloader.download_video(sample_video_metadata, sample_playlist)

        assert result is False
        assert sample_playlist.video_statuses["test_video_id"] == VideoStatus.FAILED

    @patch.object(VideoDownloader, "extract_full_playlist")
    @patch.object(VideoDownloader, "download_video")
    def test_download_playlist_success(
        self, mock_download, mock_extract, downloader, sample_playlist
    ):
        """Test successful playlist download."""
        # Mock playlist extraction
        mock_extract.return_value = sample_playlist

        # Mock video downloads
        downloader.cache_manager.is_download_cached.return_value = False
        mock_download.return_value = True

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.download_playlist(url)

        assert result == sample_playlist
        assert mock_download.call_count == len(sample_playlist.videos)

    @patch.object(VideoDownloader, "extract_full_playlist")
    @patch.object(VideoDownloader, "download_video")
    def test_download_playlist_partial_success(
        self, mock_download, mock_extract, downloader, sample_playlist
    ):
        """Test playlist download with some failures."""
        # Mock playlist extraction
        mock_extract.return_value = sample_playlist

        # Mock mixed download results
        downloader.cache_manager.is_download_cached.return_value = False
        mock_download.side_effect = [True, False]  # First succeeds, second fails

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.download_playlist(url)

        assert result == sample_playlist
        assert mock_download.call_count == 2

    @patch.object(VideoDownloader, "extract_full_playlist")
    def test_download_playlist_cached_videos(
        self, mock_extract, downloader, sample_playlist
    ):
        """Test playlist download with all videos cached."""
        # Mock playlist extraction
        mock_extract.return_value = sample_playlist

        # Mock all videos cached
        downloader.cache_manager.is_download_cached.return_value = True

        url = "https://www.youtube.com/playlist?list=test_playlist_id"
        result = downloader.download_playlist(url)

        assert result == sample_playlist
        # Should update status for all videos
        assert all(
            status == VideoStatus.DOWNLOADED
            for status in result.video_statuses.values()
        )

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_get_download_info_success(self, mock_run, downloader):
        """Test successful video info extraction."""
        mock_result = Mock()
        info_json = {
            "id": "test_video",
            "title": "Test Video",
            "duration": 300,
            "formats": [{"format_id": "22", "ext": "mp4"}],
        }
        mock_result.stdout = json.dumps(info_json)
        mock_run.return_value = mock_result

        url = "https://youtube.com/watch?v=test_video"
        result = downloader.get_download_info(url)

        assert result == info_json
        mock_run.assert_called_once()

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_get_download_info_failure(self, mock_run, downloader):
        """Test video info extraction failure."""
        mock_run.side_effect = YtDlpError("Info extraction failed")

        url = "https://youtube.com/watch?v=test_video"

        with pytest.raises(YtDlpError, match="Failed to get download info"):
            downloader.get_download_info(url)


class TestRawJsonCachingIntegration:
    """Test cases for raw yt-dlp JSON caching integration in downloader."""

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_extract_playlist_videos_cached_json_parsing_error(
        self, mock_run, downloader
    ):
        """Test handling of corrupted cached raw JSON."""
        # Mock cached raw JSON with invalid JSON
        downloader.cache_manager.get_cached_playlist_raw_json.return_value = (
            "invalid json\n{malformed}"
        )

        url = "https://www.youtube.com/playlist?list=test_playlist_id"

        # Should handle JSON parsing errors gracefully and return empty list
        # (after failing to parse, it continues with remaining lines)
        result = downloader.extract_playlist_videos(url)
        assert result == []  # No valid videos extracted due to JSON parsing errors

    @patch.object(VideoDownloader, "_run_yt_dlp")
    def test_raw_json_caching_integration_with_metadata_extraction(
        self, mock_run, downloader
    ):
        """Test that raw JSON caching works correctly with metadata extraction."""
        # Mock no cached metadata
        downloader.cache_manager.get_cached_playlist_metadata.return_value = None

        # Mock yt-dlp output for metadata extraction (include required URL field)
        mock_result = Mock()
        playlist_json = {"title": "Integration Test Playlist", "description": "Test"}
        video_json = {
            "id": "integration_video",
            "title": "Integration Video",
            "url": "https://youtube.com/watch?v=integration_video",
            "duration": 120,
        }
        raw_json_output = f"{json.dumps(playlist_json)}\n{json.dumps(video_json)}"
        mock_result.stdout = raw_json_output
        mock_run.return_value = mock_result

        url = "https://www.youtube.com/playlist?list=integration_test"

        # Extract metadata first (should cache raw JSON)
        metadata_result = downloader.extract_playlist_metadata(url)
        assert metadata_result.playlist_id == "integration_test"
        assert metadata_result.title == "Integration Test Playlist"

        # Verify raw JSON was cached during metadata extraction
        downloader.cache_manager.store_playlist_raw_json.assert_called_with(
            "integration_test", raw_json_output
        )

        # Reset mock for video extraction
        mock_run.reset_mock()

        # Mock that cached raw JSON is now available
        downloader.cache_manager.get_cached_playlist_raw_json.return_value = (
            raw_json_output
        )

        # Extract videos (should use cached raw JSON, not call yt-dlp again)
        video_result = downloader.extract_playlist_videos(url)
        assert len(video_result) == 1
        assert video_result[0].video_id == "integration_video"
        assert video_result[0].title == "Integration Video"
        assert video_result[0].url == "https://youtube.com/watch?v=integration_video"

        # yt-dlp should not be called for video extraction when raw JSON is cached
        mock_run.assert_not_called()

    def test_raw_json_caching_with_extract_full_playlist(self, downloader):
        """Test raw JSON caching with full playlist extraction."""
        with patch.object(downloader, "extract_playlist_metadata") as mock_metadata:
            with patch.object(downloader, "extract_playlist_videos") as mock_videos:
                # Mock return values
                mock_metadata.return_value = PlaylistMetadata(
                    playlist_id="full_test",
                    title="Full Test Playlist",
                    description="Full test",
                    video_count=2,
                    total_size_estimate=None,
                )
                mock_videos.return_value = [
                    VideoMetadata(
                        video_id="full_video1",
                        title="Full Video 1",
                        duration=300,
                        url="https://youtube.com/watch?v=full_video1",
                    ),
                    VideoMetadata(
                        video_id="full_video2",
                        title="Full Video 2",
                        duration=200,
                        url="https://youtube.com/watch?v=full_video2",
                    ),
                ]

                url = "https://www.youtube.com/playlist?list=full_test"
                result = downloader.extract_full_playlist(url)

                assert result.metadata.playlist_id == "full_test"
                assert len(result.videos) == 2

                # Both methods should be called with the same URL and progress callback
                # The callback is not None but a SilentProgressCallback
                assert mock_metadata.call_count == 1
                assert mock_videos.call_count == 1

                # Verify the URL parameter
                metadata_call_args = mock_metadata.call_args[0]
                videos_call_args = mock_videos.call_args[0]
                assert metadata_call_args[0] == url
                assert videos_call_args[0] == url


class TestYtDlpError:
    """Test YtDlpError exception class."""

    def test_yt_dlp_error_creation(self):
        """Test creating YtDlpError exception."""
        error = YtDlpError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_yt_dlp_error_inheritance(self):
        """Test YtDlpError inherits from Exception."""
        error = YtDlpError("Test error")
        assert isinstance(error, Exception)


@pytest.mark.integration
class TestVideoDownloaderIntegration:
    """Integration tests for VideoDownloader (require actual tools)."""

    @pytest.fixture
    def real_settings(self, tmp_path):
        """Create real settings for integration tests."""
        settings = Settings(
            cache_dir=tmp_path / "cache",
            temp_dir=tmp_path / "temp",
            bin_dir=tmp_path / "bin",
            log_dir=tmp_path / "logs",
            download_rate_limit="100K",  # Slower for testing
            video_quality="worst",  # Faster download
        )
        settings.create_directories()
        return settings

    @pytest.fixture
    def real_cache_manager(self, real_settings):
        """Create real cache manager for integration tests."""
        return CacheManager(real_settings.cache_dir)

    @pytest.fixture
    def real_tool_manager(self, real_settings):
        """Create real tool manager for integration tests."""
        return ToolManager(real_settings)

    @pytest.fixture
    def integration_downloader(
        self, real_settings, real_cache_manager, real_tool_manager
    ):
        """Create real downloader for integration tests."""
        return VideoDownloader(real_settings, real_cache_manager, real_tool_manager)

    @pytest.mark.slow
    def test_validate_real_playlist_url(self, integration_downloader):
        """Test validation with a real YouTube playlist URL."""
        # Use a known public playlist
        url = "https://www.youtube.com/playlist?list=PLrAXtmRdnqeiGF0lEzfz7"
        assert integration_downloader.validate_url(url) is True

    def test_validate_invalid_real_url(self, integration_downloader):
        """Test validation with an invalid URL."""
        url = "https://www.example.com/not-a-playlist"
        assert integration_downloader.validate_url(url) is False
