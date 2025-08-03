"""Tests for the video converter service."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.models.video import VideoFile, VideoMetadata
from src.services.cache_manager import CacheManager
from src.services.converter import (
    ConversionError,
    ConvertedVideoFile,
    VideoConverter,
)
from src.services.tool_manager import ToolManager


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.cache_dir = Path("/tmp/test_cache")
    settings.use_system_tools = False
    settings.download_tools = True
    settings.video_format = "NTSC"  # Default video format
    settings.aspect_ratio = "16:9"  # Default aspect ratio
    settings.car_dvd_compatibility = False  # Default car DVD compatibility
    return settings


@pytest.fixture
def mock_tool_manager():
    """Create mock tool manager for testing."""
    tool_manager = Mock(spec=ToolManager)
    tool_manager.get_tool_command.return_value = ["ffmpeg"]
    return tool_manager


@pytest.fixture
def mock_cache_manager():
    """Create mock cache manager for testing."""
    return Mock(spec=CacheManager)


@pytest.fixture
def sample_video_metadata():
    """Create sample video metadata for testing."""
    return VideoMetadata(
        video_id="test_video_123",
        title="Test Video",
        duration=120,
        url="https://example.com/video",
        thumbnail_url="https://example.com/thumb.jpg",
        description="A test video",
    )


@pytest.fixture
def sample_video_file(sample_video_metadata, tmp_path):
    """Create sample video file for testing."""
    video_path = tmp_path / "test_video.mp4"
    video_path.write_bytes(b"fake video content")

    return VideoFile(
        metadata=sample_video_metadata,
        file_path=video_path,
        file_size=len(b"fake video content"),
        checksum="fake_checksum",
        format="mp4",
    )


@pytest.fixture
def video_converter(mock_settings, mock_tool_manager, mock_cache_manager):
    """Create video converter instance for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_settings.cache_dir = Path(temp_dir)
        converter = VideoConverter(
            settings=mock_settings,
            tool_manager=mock_tool_manager,
            cache_manager=mock_cache_manager,
        )
        yield converter


class TestConvertedVideoFile:
    """Test the ConvertedVideoFile class."""

    def test_converted_video_file_creation(self, sample_video_metadata, tmp_path):
        """Test creating a ConvertedVideoFile instance."""
        video_file = tmp_path / "converted.mpg"
        video_file.write_bytes(b"converted content")

        converted = ConvertedVideoFile(
            metadata=sample_video_metadata,
            video_file=video_file,
            file_size=1000,
            checksum="abc123",
            duration=120,
            resolution="720x480",
            video_codec="mpeg2video",
            audio_codec="ac3",
        )

        assert converted.metadata == sample_video_metadata
        assert converted.video_file == video_file
        assert converted.file_size == 1000
        assert converted.size_mb == pytest.approx(1000 / (1024 * 1024))
        assert converted.exists

    def test_converted_video_file_serialization(self, sample_video_metadata, tmp_path):
        """Test serialization and deserialization of ConvertedVideoFile."""
        video_file = tmp_path / "converted.mpg"
        thumbnail_file = tmp_path / "thumb.jpg"

        converted = ConvertedVideoFile(
            metadata=sample_video_metadata,
            video_file=video_file,
            thumbnail_file=thumbnail_file,
            file_size=1000,
            checksum="abc123",
            duration=120,
            resolution="720x480",
            video_codec="mpeg2video",
            audio_codec="ac3",
        )

        # Test to_dict
        data = converted.to_dict()
        expected_data = {
            "video_id": "test_video_123",
            "video_file": str(video_file),
            "thumbnail_file": str(thumbnail_file),
            "file_size": 1000,
            "checksum": "abc123",
            "duration": 120,
            "resolution": "720x480",
            "video_codec": "mpeg2video",
            "audio_codec": "ac3",
        }
        assert data == expected_data

        # Test from_dict
        restored = ConvertedVideoFile.from_dict(data, sample_video_metadata)
        assert restored.video_file == video_file
        assert restored.thumbnail_file == thumbnail_file
        assert restored.file_size == 1000


class TestVideoConverter:
    """Test the VideoConverter class."""

    def test_video_converter_initialization(self, video_converter):
        """Test VideoConverter initialization."""
        assert video_converter.settings is not None
        assert video_converter.tool_manager is not None
        assert video_converter.cache_manager is not None
        assert video_converter.converted_cache_dir.exists()

    def test_load_save_converted_metadata(self, video_converter):
        """Test loading and saving converted metadata."""
        # Initially empty
        metadata = video_converter._load_converted_metadata()
        assert metadata == {}

        # Save some metadata
        test_metadata = {
            "video_123": {
                "video_id": "video_123",
                "video_file": "/path/to/video.mpg",
                "file_size": 1000,
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(test_metadata)

        # Load it back
        loaded_metadata = video_converter._load_converted_metadata()
        assert loaded_metadata == test_metadata

    def test_calculate_file_checksum(self, video_converter, tmp_path):
        """Test file checksum calculation."""
        test_file = tmp_path / "test.txt"
        test_content = b"hello world"
        test_file.write_bytes(test_content)

        checksum = video_converter._calculate_file_checksum(test_file)
        assert checksum != ""
        assert len(checksum) == 64  # SHA-256 hex string length

        # Same content should produce same checksum
        checksum2 = video_converter._calculate_file_checksum(test_file)
        assert checksum == checksum2

    @patch("subprocess.run")
    def test_get_video_info_success(self, mock_run, video_converter, sample_video_file):
        """Test successful video info extraction."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "120.0"},
            }
        )
        mock_run.return_value = mock_result

        info = video_converter._get_video_info(sample_video_file.file_path)

        assert "streams" in info
        assert "format" in info
        assert len(info["streams"]) == 2

    @patch("subprocess.run")
    def test_get_video_info_failure(self, mock_run, video_converter, sample_video_file):
        """Test video info extraction failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error"
        mock_run.return_value = mock_result

        with pytest.raises(ConversionError, match="ffprobe failed"):
            video_converter._get_video_info(sample_video_file.file_path)

    def test_determine_dvd_format_ntsc_from_settings(self, video_converter):
        """Test DVD format determination using NTSC from settings."""
        # Mock settings with NTSC format
        video_converter.settings.video_format = "NTSC"
        video_info = {"streams": [{"codec_type": "video", "r_frame_rate": "29.97/1"}]}

        resolution, framerate = video_converter._determine_dvd_format(video_info)
        assert resolution == VideoConverter.NTSC_RESOLUTION
        assert framerate == VideoConverter.NTSC_FRAMERATE

    def test_determine_dvd_format_pal_from_settings(self, video_converter):
        """Test DVD format determination using PAL from settings."""
        # Mock settings with PAL format
        video_converter.settings.video_format = "PAL"
        video_info = {"streams": [{"codec_type": "video", "r_frame_rate": "25/1"}]}

        resolution, framerate = video_converter._determine_dvd_format(video_info)
        assert resolution == VideoConverter.PAL_RESOLUTION
        assert framerate == VideoConverter.PAL_FRAMERATE

    def test_determine_dvd_format_default_ntsc(self, video_converter):
        """Test DVD format determination defaults to NTSC for invalid format."""
        # Mock settings with invalid format (should default to NTSC)
        video_converter.settings.video_format = "INVALID"
        video_info = {"streams": []}

        resolution, framerate = video_converter._determine_dvd_format(video_info)
        assert resolution == VideoConverter.NTSC_RESOLUTION  # Default
        assert framerate == VideoConverter.NTSC_FRAMERATE

    def test_determine_dvd_format_case_insensitive(self, video_converter):
        """Test DVD format determination is case insensitive."""
        # Test lowercase PAL
        video_converter.settings.video_format = "pal"
        video_info = {"streams": []}

        resolution, framerate = video_converter._determine_dvd_format(video_info)
        assert resolution == VideoConverter.PAL_RESOLUTION
        assert framerate == VideoConverter.PAL_FRAMERATE

        # Test lowercase NTSC
        video_converter.settings.video_format = "ntsc"
        resolution, framerate = video_converter._determine_dvd_format(video_info)
        assert resolution == VideoConverter.NTSC_RESOLUTION
        assert framerate == VideoConverter.NTSC_FRAMERATE

    def test_build_conversion_command(self, video_converter, tmp_path):
        """Test building conversion command."""
        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mpg"

        cmd = video_converter._build_conversion_command(
            input_path, output_path, "720x480", "29.97"
        )

        assert "ffmpeg" in cmd[0]
        assert "-i" in cmd
        assert str(input_path) in cmd
        assert str(output_path) in cmd
        assert "-c:v" in cmd
        assert "mpeg2video" in cmd
        assert "-s" in cmd
        assert "720x480" in cmd

    def test_build_thumbnail_command(self, video_converter, tmp_path):
        """Test building thumbnail command."""
        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "thumb.jpg"

        cmd = video_converter._build_thumbnail_command(input_path, output_path, 30)

        assert "ffmpeg" in cmd[0]
        assert "-i" in cmd
        assert str(input_path) in cmd
        assert str(output_path) in cmd
        assert "-ss" in cmd
        assert "30" in cmd
        assert "-vframes" in cmd
        assert "1" in cmd

    @patch("subprocess.Popen")
    def test_run_conversion_command_success(self, mock_popen, video_converter):
        """Test successful conversion command execution."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # First call
        mock_process.poll.side_effect = [None, 0]  # Then return 0
        mock_process.returncode = 0
        mock_process.stderr = None
        mock_process.communicate.return_value = ("", "")
        mock_popen.return_value = mock_process

        # Should not raise an exception
        video_converter._run_conversion_command(
            ["ffmpeg", "-version"], "test operation"
        )

    @patch("subprocess.Popen")
    def test_run_conversion_command_failure(self, mock_popen, video_converter):
        """Test conversion command execution failure."""
        mock_process = Mock()
        mock_process.poll.return_value = 1
        mock_process.returncode = 1
        mock_process.stderr = None
        mock_process.communicate.return_value = ("", "error occurred")
        mock_popen.return_value = mock_process

        with pytest.raises(ConversionError, match="test operation failed"):
            video_converter._run_conversion_command(
                ["ffmpeg", "-invalid"], "test operation"
            )

    def test_is_video_converted_false_not_in_cache(
        self, video_converter, sample_video_metadata
    ):
        """Test is_video_converted returns False when not in cache."""
        assert not video_converter.is_video_converted(sample_video_metadata)

    def test_is_video_converted_false_file_missing(
        self, video_converter, sample_video_metadata
    ):
        """Test is_video_converted returns False when file is missing."""
        # Add to metadata but file doesn't exist
        metadata = {
            sample_video_metadata.video_id: {
                "video_id": sample_video_metadata.video_id,
                "video_file": "/nonexistent/file.mpg",
                "file_size": 1000,
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(metadata)

        assert not video_converter.is_video_converted(sample_video_metadata)

    def test_is_video_converted_true(
        self, video_converter, sample_video_metadata, tmp_path
    ):
        """Test is_video_converted returns True for valid cached file."""
        # Create a real file
        video_file = tmp_path / "converted.mpg"
        content = b"converted video content"
        video_file.write_bytes(content)

        # Add to metadata
        metadata = {
            sample_video_metadata.video_id: {
                "video_id": sample_video_metadata.video_id,
                "video_file": str(video_file),
                "file_size": len(content),
                "checksum": "abc123",
                "duration": 120,
                "resolution": "720x480",
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
                "thumbnail_file": None,
            }
        }
        video_converter._save_converted_metadata(metadata)

        assert video_converter.is_video_converted(sample_video_metadata)

    def test_get_converted_video_none_when_not_converted(
        self, video_converter, sample_video_metadata
    ):
        """Test get_converted_video returns None when video not converted."""
        result = video_converter.get_converted_video(sample_video_metadata)
        assert result is None

    def test_get_converted_video_success(
        self, video_converter, sample_video_metadata, tmp_path
    ):
        """Test get_converted_video returns ConvertedVideoFile when available."""
        # Create a real file
        video_file = tmp_path / "converted.mpg"
        content = b"converted video content"
        video_file.write_bytes(content)

        # Add to metadata
        metadata = {
            sample_video_metadata.video_id: {
                "video_id": sample_video_metadata.video_id,
                "video_file": str(video_file),
                "file_size": len(content),
                "checksum": "abc123",
                "duration": 120,
                "resolution": "720x480",
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
                "thumbnail_file": None,
            }
        }
        video_converter._save_converted_metadata(metadata)

        result = video_converter.get_converted_video(sample_video_metadata)
        assert result is not None
        assert result.metadata == sample_video_metadata
        assert result.video_file == video_file

    def test_convert_video_input_file_missing(self, video_converter, sample_video_file):
        """Test convert_video raises error when input file is missing."""
        # Make the file path point to non-existent file
        sample_video_file.file_path.unlink()

        with pytest.raises(ConversionError, match="Input video file does not exist"):
            video_converter.convert_video(sample_video_file)

    @patch.object(VideoConverter, "_get_video_info")
    @patch.object(VideoConverter, "_run_conversion_command")
    @patch.object(VideoConverter, "_calculate_file_checksum")
    def test_convert_video_success(
        self,
        mock_checksum,
        mock_run_cmd,
        mock_get_info,
        video_converter,
        sample_video_file,
        tmp_path,
    ):
        """Test successful video conversion."""
        # Mock video info
        mock_get_info.side_effect = [
            # First call for input analysis
            {
                "streams": [{"codec_type": "video", "r_frame_rate": "30/1"}],
                "format": {"duration": "120.0"},
            },
            # Second call for output analysis
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "mpeg2video",
                        "width": 720,
                        "height": 480,
                    },
                    {"codec_type": "audio", "codec_name": "ac3"},
                ],
                "format": {"duration": "120.0"},
            },
        ]

        mock_checksum.return_value = "abc123"
        mock_run_cmd.return_value = None  # Success

        # Mock the temporary file creation
        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            temp_video = tmp_path / "temp_video.mpg"
            temp_thumb = tmp_path / "temp_thumb.jpg"

            # Create actual temp files
            temp_video.write_bytes(b"converted content")
            temp_thumb.write_bytes(b"thumbnail content")

            # Create proper mock temp file objects with context manager support
            def mock_temp_factory(suffix=None, delete=None):
                mock_file = Mock()
                if suffix == ".mpg":
                    mock_file.name = str(temp_video)
                else:
                    mock_file.name = str(temp_thumb)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                return mock_file

            mock_temp.side_effect = mock_temp_factory

            # Mock the rename operation by copying to the expected location
            with patch.object(Path, "rename") as mock_rename:

                def side_effect(dest):
                    dest.write_bytes(b"converted content")

                mock_rename.side_effect = side_effect

                result = video_converter.convert_video(sample_video_file)

        assert isinstance(result, ConvertedVideoFile)
        assert result.metadata == sample_video_file.metadata
        assert result.checksum == "abc123"

    @patch.object(VideoConverter, "convert_video")
    def test_convert_videos_success(
        self, mock_convert, video_converter, sample_video_file
    ):
        """Test successful batch video conversion."""
        # Mock individual conversion
        mock_converted = Mock(spec=ConvertedVideoFile)
        mock_convert.return_value = mock_converted

        video_files = [sample_video_file]
        results = video_converter.convert_videos(video_files)

        assert len(results) == 1
        assert results[0] == mock_converted
        mock_convert.assert_called_once_with(sample_video_file, False)

    @patch.object(VideoConverter, "convert_video")
    def test_convert_videos_with_failures(
        self, mock_convert, video_converter, sample_video_file
    ):
        """Test batch conversion with some failures."""
        # Mock conversion to fail
        mock_convert.side_effect = ConversionError("Conversion failed")

        video_files = [sample_video_file]
        results = video_converter.convert_videos(video_files)

        # Should continue despite failures
        assert len(results) == 0

    def test_get_conversion_stats_empty(self, video_converter):
        """Test conversion statistics with no conversions."""
        stats = video_converter.get_conversion_stats()

        expected = {
            "total_videos": 0,
            "total_size_mb": 0,
            "average_size_mb": 0,
            "formats": {},
        }
        assert stats == expected

    def test_get_conversion_stats_with_data(self, video_converter):
        """Test conversion statistics with some data."""
        metadata = {
            "video1": {
                "file_size": 1024 * 1024,  # 1 MB
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
            },
            "video2": {
                "file_size": 2 * 1024 * 1024,  # 2 MB
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
            },
        }
        video_converter._save_converted_metadata(metadata)

        stats = video_converter.get_conversion_stats()

        assert stats["total_videos"] == 2
        assert stats["total_size_mb"] == 3.0
        assert stats["average_size_mb"] == 1.5
        assert stats["formats"]["mpeg2video/ac3"] == 2

    def test_cleanup_cache(self, video_converter, tmp_path):
        """Test cache cleanup functionality."""
        # Create some test files and metadata
        metadata = {}
        for i in range(5):
            video_id = f"video_{i}"
            video_file = tmp_path / f"{video_id}.mpv"
            video_file.write_bytes(b"content")

            metadata[video_id] = {
                "video_id": video_id,
                "video_file": str(video_file),
                "file_size": 1000,
                "checksum": "abc123",
                "thumbnail_file": None,
            }

        video_converter._save_converted_metadata(metadata)

        # Cleanup keeping only 2 recent files
        video_converter.cleanup_cache(keep_recent=2)

        # Check that only 2 remain in metadata
        remaining_metadata = video_converter._load_converted_metadata()
        assert len(remaining_metadata) == 2


class TestVideoConverterIntegration:
    """Integration tests for VideoConverter."""

    @pytest.fixture
    def real_video_converter(self, tmp_path):
        """Create a real VideoConverter instance for integration testing."""
        settings = Mock(spec=Settings)
        settings.cache_dir = tmp_path / "cache"
        settings.use_system_tools = False
        settings.download_tools = True

        tool_manager = Mock(spec=ToolManager)
        tool_manager.get_tool_command.return_value = ["echo", "ffmpeg"]  # Mock ffmpeg

        cache_manager = Mock(spec=CacheManager)

        return VideoConverter(
            settings=settings,
            tool_manager=tool_manager,
            cache_manager=cache_manager,
        )

    def test_converter_initialization_creates_directories(self, real_video_converter):
        """Test that converter creates necessary directories."""
        assert real_video_converter.converted_cache_dir.exists()
        assert real_video_converter.metadata_file.parent.exists()

    def test_metadata_persistence_across_instances(self, tmp_path):
        """Test that metadata persists across converter instances."""
        settings = Mock(spec=Settings)
        settings.cache_dir = tmp_path / "cache"

        tool_manager = Mock(spec=ToolManager)
        cache_manager = Mock(spec=CacheManager)

        # Create first instance and save some metadata
        converter1 = VideoConverter(settings, tool_manager, cache_manager)
        test_metadata = {"video1": {"file_size": 1000}}
        converter1._save_converted_metadata(test_metadata)

        # Create second instance and verify metadata is loaded
        converter2 = VideoConverter(settings, tool_manager, cache_manager)
        loaded_metadata = converter2._load_converted_metadata()

        assert loaded_metadata == test_metadata


class TestVideoConverterErrorHandling:
    """Test error handling in VideoConverter."""

    def test_load_converted_metadata_json_decode_error(self, video_converter):
        """Test handling of corrupted metadata file."""
        # Create invalid JSON file
        with open(video_converter.metadata_file, "w") as f:
            f.write("invalid json content")

        metadata = video_converter._load_converted_metadata()
        assert metadata == {}

    def test_load_converted_metadata_io_error(self, video_converter):
        """Test handling of IO error when loading metadata."""
        # Create a file first, then make it unreadable
        video_converter.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        video_converter.metadata_file.write_text('{"test": "data"}')
        video_converter.metadata_file.chmod(0o000)

        try:
            metadata = video_converter._load_converted_metadata()
            assert metadata == {}
        finally:
            # Restore permissions for cleanup
            video_converter.metadata_file.chmod(0o644)

    def test_save_converted_metadata_io_error(self, video_converter):
        """Test handling of IO error when saving metadata."""
        # Mock open to raise IOError
        with patch("builtins.open", side_effect=IOError("Mocked IO error")):
            # Should not raise exception, just log error
            video_converter._save_converted_metadata({"test": {"data": "value"}})

    def test_calculate_file_checksum_io_error(self, video_converter, tmp_path):
        """Test checksum calculation with IO error."""
        nonexistent_file = tmp_path / "nonexistent.txt"

        checksum = video_converter._calculate_file_checksum(nonexistent_file)
        assert checksum == ""

    def test_get_video_info_file_not_found(self, video_converter, tmp_path):
        """Test video info extraction with missing ffprobe."""
        nonexistent_file = tmp_path / "test.mp4"
        nonexistent_file.write_bytes(b"fake content")

        # Mock tool manager to return non-existent command
        video_converter.tool_manager.get_tool_command.return_value = [
            "/nonexistent/ffprobe"
        ]

        with pytest.raises(ConversionError, match="Failed to analyze video"):
            video_converter._get_video_info(nonexistent_file)

    @patch("subprocess.run")
    def test_get_video_info_timeout(self, mock_run, video_converter, tmp_path):
        """Test video info extraction with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 30)

        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake content")

        with pytest.raises(ConversionError, match="Failed to analyze video"):
            video_converter._get_video_info(test_file)

    @patch("subprocess.run")
    def test_get_video_info_invalid_json(self, mock_run, video_converter, tmp_path):
        """Test video info extraction with invalid JSON response."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"
        mock_run.return_value = mock_result

        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake content")

        with pytest.raises(ConversionError, match="Failed to analyze video"):
            video_converter._get_video_info(test_file)


class TestVideoConverterProgressReporting:
    """Test progress reporting functionality."""

    def test_progress_callback_during_conversion(self, video_converter):
        """Test that progress callback is called during conversion."""
        progress_calls = []

        def mock_callback(message, progress):
            progress_calls.append((message, progress))

        video_converter.progress_callback = mock_callback

        # Mock subprocess with progress output
        mock_process = Mock()
        mock_process.poll.side_effect = [None, None, 0]
        mock_process.returncode = 0
        mock_process.stderr.readline.side_effect = [
            "frame=  100 time=00:01:30.45 bitrate=1000.0kbits/s speed=1.5x\n",
            "frame=  200 time=00:03:00.90 bitrate=1000.0kbits/s speed=1.5x\n",
            "",
        ]
        mock_process.communicate.return_value = ("", "")

        with patch("subprocess.Popen", return_value=mock_process):
            video_converter._run_conversion_command(
                ["ffmpeg", "-i", "input.mp4", "output.mpv"],
                "test conversion",
                estimated_duration=300,  # 5 minutes
            )

        # Should have called progress callback
        assert len(progress_calls) >= 1

    def test_progress_callback_with_invalid_time_format(self, video_converter):
        """Test progress parsing with invalid time format."""
        progress_calls = []

        def mock_callback(message, progress):
            progress_calls.append((message, progress))

        video_converter.progress_callback = mock_callback

        # Mock subprocess with invalid time format
        mock_process = Mock()
        mock_process.poll.side_effect = [None, 0]
        mock_process.returncode = 0
        mock_process.stderr.readline.side_effect = [
            "frame=  100 time=invalid_time bitrate=1000.0kbits/s\n",
            "",
        ]
        mock_process.communicate.return_value = ("", "")

        with patch("subprocess.Popen", return_value=mock_process):
            video_converter._run_conversion_command(
                ["ffmpeg", "-i", "input.mp4", "output.mpv"],
                "test conversion",
                estimated_duration=300,
            )

        # Should complete without error, just skip invalid progress
        assert mock_process.communicate.called

    @patch("subprocess.Popen")
    def test_run_conversion_command_subprocess_error(self, mock_popen, video_converter):
        """Test handling of subprocess errors."""
        mock_popen.side_effect = subprocess.SubprocessError("Process failed")

        with pytest.raises(ConversionError, match="test operation failed"):
            video_converter._run_conversion_command(
                ["ffmpeg", "-version"], "test operation"
            )


class TestVideoConverterCacheHandling:
    """Test cache-related functionality."""

    def test_is_video_converted_size_mismatch(
        self, video_converter, sample_video_metadata, tmp_path
    ):
        """Test is_video_converted with file size mismatch."""
        # Create file with different size
        video_file = tmp_path / "converted.mpg"
        video_file.write_bytes(b"different content")

        # Add to metadata with wrong size
        metadata = {
            sample_video_metadata.video_id: {
                "video_id": sample_video_metadata.video_id,
                "video_file": str(video_file),
                "file_size": 999999,  # Wrong size
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(metadata)

        assert not video_converter.is_video_converted(sample_video_metadata)

    def test_convert_video_uses_cache_when_available(
        self, video_converter, sample_video_file, tmp_path
    ):
        """Test that convert_video uses cached version when available."""
        # Create cached file
        video_file = tmp_path / "converted.mpg"
        content = b"cached content"
        video_file.write_bytes(content)

        metadata = {
            sample_video_file.metadata.video_id: {
                "video_id": sample_video_file.metadata.video_id,
                "video_file": str(video_file),
                "file_size": len(content),
                "checksum": "abc123",
                "duration": 120,
                "resolution": "720x480",
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
                "thumbnail_file": None,
            }
        }
        video_converter._save_converted_metadata(metadata)

        # Should return cached version without conversion
        result = video_converter.convert_video(sample_video_file)
        assert isinstance(result, ConvertedVideoFile)
        assert result.video_file == video_file

    def test_convert_video_force_convert_bypasses_cache(
        self, video_converter, sample_video_file, tmp_path
    ):
        """Test that force_convert bypasses cache."""
        # Create cached file
        video_file = tmp_path / "converted.mpg"
        content = b"cached content"
        video_file.write_bytes(content)

        metadata = {
            sample_video_file.metadata.video_id: {
                "video_id": sample_video_file.metadata.video_id,
                "video_file": str(video_file),
                "file_size": len(content),
                "checksum": "abc123",
                "duration": 120,
                "resolution": "720x480",
                "video_codec": "mpeg2video",
                "audio_codec": "ac3",
                "thumbnail_file": None,
            }
        }
        video_converter._save_converted_metadata(metadata)

        # Mock conversion process
        with (
            patch.object(video_converter, "_get_video_info") as mock_info,
            patch.object(video_converter, "_run_conversion_command") as mock_run,
            patch.object(video_converter, "_calculate_file_checksum") as mock_checksum,
            patch("tempfile.NamedTemporaryFile") as mock_temp,
        ):

            mock_info.side_effect = [
                {"streams": [], "format": {"duration": "120.0"}},  # Input analysis
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "mpeg2video",
                            "width": 720,
                            "height": 480,
                        },
                        {"codec_type": "audio", "codec_name": "ac3"},
                    ],
                    "format": {"duration": "120.0"},
                },  # Output analysis
            ]
            mock_checksum.return_value = "new_checksum"

            # Mock temp files
            temp_video = tmp_path / "temp_video.mpg"
            temp_thumb = tmp_path / "temp_thumb.jpg"
            temp_video.write_bytes(b"new content")
            temp_thumb.write_bytes(b"thumb content")

            def mock_temp_factory(suffix=None, delete=None):
                mock_file = Mock()
                if suffix == ".mpg":
                    mock_file.name = str(temp_video)
                else:
                    mock_file.name = str(temp_thumb)
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                return mock_file

            mock_temp.side_effect = mock_temp_factory

            with patch.object(Path, "rename") as mock_rename:

                def side_effect(dest):
                    dest.write_bytes(b"new content")

                mock_rename.side_effect = side_effect

                # Should perform conversion despite cached version
                result = video_converter.convert_video(
                    sample_video_file, force_convert=True
                )
                assert mock_run.called
                assert isinstance(result, ConvertedVideoFile)


class TestVideoConverterCarDVDCompatibility:
    """Test car DVD compatibility features."""

    def test_build_conversion_command_car_dvd_compatibility(
        self, video_converter, tmp_path
    ):
        """Test conversion command with car DVD compatibility enabled."""
        video_converter.settings.car_dvd_compatibility = True

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mpg"

        cmd = video_converter._build_conversion_command(
            input_path, output_path, "720x480", "29.97"
        )

        # Should use conservative settings for car DVD compatibility
        assert "3500k" in cmd  # Conservative video bitrate (both -b:v and -minrate)
        assert "6000k" in cmd  # Conservative max rate
        assert "ac3" in cmd  # AC-3 audio (more compatible than PCM)
        assert "192k" in cmd  # Standard AC-3 bitrate
        assert "12" in cmd  # Shorter GOP size
        assert "0" in cmd  # No B-frames for compatibility

        # Should include strict DVD-Video spec compliance flags
        assert "+ilme+ildct" in cmd  # Interlaced motion estimation and DCT
        assert "1" in cmd  # Top field first (-top 1)
        assert "yadif=0:-1:0,setsar=32/27" in cmd  # Deinterlacing and SAR filter

        # Should NOT include incompatible flags
        assert "+aic" not in cmd  # Not DVD spec compliant
        assert "+mv4" not in cmd  # 4MV not supported by MPEG-2
        assert "+bpyramid" not in cmd  # B-frame pyramid not compatible with MPEG-2

    def test_build_conversion_command_standard_mode(self, video_converter, tmp_path):
        """Test conversion command with standard DVD settings."""
        video_converter.settings.car_dvd_compatibility = False

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mpg"

        cmd = video_converter._build_conversion_command(
            input_path, output_path, "720x480", "29.97"
        )

        # Should use standard bitrate and AC-3 audio
        assert "6000k" in cmd  # Standard video bitrate
        assert "ac3" in cmd  # AC-3 audio
        assert "448k" in cmd  # AC-3 audio bitrate


class TestVideoConverterCleanup:
    """Test cleanup and maintenance functionality."""

    def test_cleanup_cache_removes_old_files(self, video_converter, tmp_path):
        """Test that cleanup removes old converted files."""
        # Create test files and metadata
        metadata = {}
        created_files = []

        for i in range(5):
            video_id = f"video_{i}"
            video_dir = video_converter.converted_cache_dir / video_id
            video_dir.mkdir(parents=True, exist_ok=True)

            video_file = video_dir / f"{video_id}_dvd.mpv"
            thumb_file = video_dir / f"{video_id}_thumb.jpg"

            video_file.write_bytes(b"content")
            thumb_file.write_bytes(b"thumb")
            created_files.extend([video_file, thumb_file])

            metadata[video_id] = {
                "video_id": video_id,
                "video_file": str(video_file),
                "thumbnail_file": str(thumb_file),
                "file_size": 1000,
                "checksum": "abc123",
            }

        video_converter._save_converted_metadata(metadata)

        # All files should exist
        for file_path in created_files:
            assert file_path.exists()

        # Cleanup keeping only 2 recent files
        video_converter.cleanup_cache(keep_recent=2)

        # Check metadata was updated
        remaining_metadata = video_converter._load_converted_metadata()
        assert len(remaining_metadata) == 2

        # Check files were removed (3 oldest should be gone)
        removed_files = created_files[:6]  # First 3 videos * 2 files each
        for file_path in removed_files:
            assert not file_path.exists()

    def test_cleanup_cache_handles_missing_files(self, video_converter):
        """Test cleanup handles missing files gracefully."""
        # Create metadata for non-existent files
        metadata = {
            "video1": {
                "video_id": "video1",
                "video_file": "/nonexistent/file.mpv",
                "thumbnail_file": "/nonexistent/thumb.jpg",
                "file_size": 1000,
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(metadata)

        # Should not raise exception
        video_converter.cleanup_cache(keep_recent=0)

        # Metadata should be cleaned up
        remaining_metadata = video_converter._load_converted_metadata()
        assert len(remaining_metadata) == 0

    def test_cleanup_cache_keep_recent_zero(self, video_converter, tmp_path):
        """Test cleanup with keep_recent=0 removes all files."""
        # Create one test file
        video_id = "test_video"
        video_dir = video_converter.converted_cache_dir / video_id
        video_dir.mkdir(parents=True, exist_ok=True)

        video_file = video_dir / f"{video_id}_dvd.mpv"
        video_file.write_bytes(b"content")

        metadata = {
            video_id: {
                "video_id": video_id,
                "video_file": str(video_file),
                "thumbnail_file": None,
                "file_size": 1000,
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(metadata)

        # Cleanup with keep_recent=0
        video_converter.cleanup_cache(keep_recent=0)

        # All should be removed
        remaining_metadata = video_converter._load_converted_metadata()
        assert len(remaining_metadata) == 0
        assert not video_file.exists()

    def test_cleanup_cache_no_cleanup_needed(self, video_converter):
        """Test cleanup when no cleanup is needed."""
        # Create metadata with fewer items than keep_recent
        metadata = {
            "video1": {
                "video_id": "video1",
                "video_file": "/path/file.mpv",
                "file_size": 1000,
                "checksum": "abc123",
            }
        }
        video_converter._save_converted_metadata(metadata)

        # Should not remove anything
        video_converter.cleanup_cache(keep_recent=5)

        remaining_metadata = video_converter._load_converted_metadata()
        assert len(remaining_metadata) == 1
