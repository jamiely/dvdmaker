"""Tests for DVD authoring service."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.config.settings import Settings
from src.models.dvd import DVDChapter, DVDStructure
from src.models.video import VideoFile, VideoMetadata
from src.services.cache_manager import CacheManager
from src.services.converter import ConvertedVideoFile
from src.services.dvd_author import (
    AuthoredDVD,
    DVDAuthor,
    DVDAuthoringError,
    DVDStructureCreationError,
)
from src.services.tool_manager import ToolManager


@pytest.fixture
def settings(tmp_path):
    """Create test settings."""
    return Settings(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        temp_dir=tmp_path / "temp",
        bin_dir=tmp_path / "bin",
        log_dir=tmp_path / "logs",
        log_level="DEBUG",
        log_file_max_size=10485760,
        log_file_backup_count=5,
        download_rate_limit="1M",
        video_quality="best",
        video_format="NTSC",  # Default video format for tests
    )


@pytest.fixture
def mock_tool_manager():
    """Create mock tool manager."""
    mock = Mock(spec=ToolManager)
    mock.get_tool_path.return_value = "/usr/bin/dvdauthor"
    return mock


@pytest.fixture
def mock_cache_manager():
    """Create mock cache manager."""
    return Mock(spec=CacheManager)


@pytest.fixture
def mock_progress_callback():
    """Create mock progress callback."""
    return Mock()


@pytest.fixture
def sample_video_metadata():
    """Create sample video metadata."""
    return [
        VideoMetadata(
            video_id="video1",
            title="Test Video 1",
            duration=120,
            url="https://example.com/video1",
            thumbnail_url="https://example.com/thumb1.jpg",
            description="First test video",
        ),
        VideoMetadata(
            video_id="video2",
            title="Test Video 2",
            duration=180,
            url="https://example.com/video2",
            thumbnail_url="https://example.com/thumb2.jpg",
            description="Second test video",
        ),
    ]


@pytest.fixture
def sample_converted_videos(tmp_path, sample_video_metadata):
    """Create sample converted video files."""
    converted_videos = []

    for i, metadata in enumerate(sample_video_metadata, 1):
        # Create mock video file
        video_file = tmp_path / f"video{i}.mpg"
        video_file.write_text(f"mock video {i} content")

        # Create mock thumbnail file
        thumbnail_file = tmp_path / f"thumb{i}.jpg"
        thumbnail_file.write_text(f"mock thumbnail {i}")

        converted_video = ConvertedVideoFile(
            metadata=metadata,
            video_file=video_file,
            thumbnail_file=thumbnail_file,
            file_size=video_file.stat().st_size,
            checksum=f"checksum{i}",
            duration=metadata.duration,
            resolution="720x480",
            video_codec="mpeg2video",
            audio_codec="ac3",
        )
        converted_videos.append(converted_video)

    return converted_videos


@pytest.fixture
def dvd_author(settings, mock_tool_manager, mock_cache_manager, mock_progress_callback):
    """Create DVDAuthor instance."""
    return DVDAuthor(
        settings=settings,
        tool_manager=mock_tool_manager,
        cache_manager=mock_cache_manager,
        progress_callback=mock_progress_callback,
    )


class TestAuthoredDVD:
    """Test AuthoredDVD class."""

    def test_authored_dvd_initialization(self, tmp_path, sample_converted_videos):
        """Test AuthoredDVD initialization."""
        # Create mock DVD structure
        chapters = []
        for i, video in enumerate(sample_converted_videos, 1):
            video_file = VideoFile(
                metadata=video.metadata,
                file_path=video.video_file,
                file_size=video.file_size,
                checksum=video.checksum,
                format="mpeg2",
            )
            chapter = DVDChapter(
                chapter_number=i,
                video_file=video_file,
                start_time=(i - 1) * 120,
            )
            chapters.append(chapter)

        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test DVD",
            total_size=sum(v.file_size for v in sample_converted_videos),
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        authored_dvd = AuthoredDVD(
            dvd_structure=dvd_structure,
            video_ts_dir=video_ts_dir,
            creation_time=30.5,
        )

        assert authored_dvd.dvd_structure == dvd_structure
        assert authored_dvd.video_ts_dir == video_ts_dir
        assert authored_dvd.iso_file is None
        assert authored_dvd.creation_time == 30.5

    def test_authored_dvd_exists_check(self, tmp_path, sample_converted_videos):
        """Test AuthoredDVD exists property."""
        # Create mock DVD structure
        chapters = []
        for i, video in enumerate(sample_converted_videos, 1):
            video_file = VideoFile(
                metadata=video.metadata,
                file_path=video.video_file,
                file_size=video.file_size,
                checksum=video.checksum,
                format="mpeg2",
            )
            chapter = DVDChapter(
                chapter_number=i,
                video_file=video_file,
                start_time=(i - 1) * 120,
            )
            chapters.append(chapter)

        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test DVD",
            total_size=1000,
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        authored_dvd = AuthoredDVD(
            dvd_structure=dvd_structure,
            video_ts_dir=video_ts_dir,
        )

        # Should not exist without VIDEO_TS.IFO
        assert not authored_dvd.exists

        # Create VIDEO_TS.IFO
        (video_ts_dir / "VIDEO_TS.IFO").touch()
        assert authored_dvd.exists

    def test_authored_dvd_validate_structure(self, tmp_path, sample_converted_videos):
        """Test AuthoredDVD structure validation."""
        # Create mock DVD structure
        chapters = []
        for i, video in enumerate(sample_converted_videos, 1):
            video_file = VideoFile(
                metadata=video.metadata,
                file_path=video.video_file,
                file_size=video.file_size,
                checksum=video.checksum,
                format="mpeg2",
            )
            chapter = DVDChapter(
                chapter_number=i,
                video_file=video_file,
                start_time=(i - 1) * 120,
            )
            chapters.append(chapter)

        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test DVD",
            total_size=1000,
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        authored_dvd = AuthoredDVD(
            dvd_structure=dvd_structure,
            video_ts_dir=video_ts_dir,
        )

        # Should fail validation initially
        assert not authored_dvd.validate_structure()

        # Create required files
        required_files = [
            "VIDEO_TS.IFO",
            "VIDEO_TS.BUP",
            "VIDEO_TS.VOB",
            "VTS_01_0.IFO",
            "VTS_01_0.BUP",
            "VTS_01_1.VOB",  # At least one VOB file
        ]

        for filename in required_files:
            (video_ts_dir / filename).touch()

        # Should pass validation now
        assert authored_dvd.validate_structure()


class TestDVDAuthor:
    """Test DVDAuthor class."""

    def test_dvd_author_initialization(self, dvd_author, settings):
        """Test DVDAuthor initialization."""
        assert dvd_author.settings == settings
        assert dvd_author.progress_callback is not None
        assert dvd_author.DVD_CAPACITY_GB == 4.7

    def test_create_chapters(self, dvd_author, sample_converted_videos):
        """Test creating DVD chapters from converted videos."""
        chapters = dvd_author._create_chapters(sample_converted_videos)

        assert len(chapters) == 2

        # Check first chapter
        assert chapters[0].chapter_number == 1
        assert chapters[0].start_time == 0
        assert chapters[0].video_file.metadata.video_id == "video1"
        assert chapters[0].duration == 120

        # Check second chapter
        assert chapters[1].chapter_number == 2
        assert chapters[1].start_time == 120  # After first video
        assert chapters[1].video_file.metadata.video_id == "video2"
        assert chapters[1].duration == 180

    def test_estimate_dvd_capacity(self, dvd_author, sample_converted_videos):
        """Test DVD capacity estimation."""
        # Small files should fit
        size_gb, fits = dvd_author.estimate_dvd_capacity(sample_converted_videos)
        assert size_gb < 0.001  # Very small test files
        assert fits is True

        # Create large mock files
        large_videos = []
        for video in sample_converted_videos:
            large_video = ConvertedVideoFile(
                metadata=video.metadata,
                video_file=video.video_file,
                thumbnail_file=video.thumbnail_file,
                file_size=3 * 1024 * 1024 * 1024,  # 3GB each
                checksum=video.checksum,
                duration=video.duration,
                resolution=video.resolution,
                video_codec=video.video_codec,
                audio_codec=video.audio_codec,
            )
            large_videos.append(large_video)

        size_gb, fits = dvd_author.estimate_dvd_capacity(large_videos)
        assert size_gb > 4.7  # Should exceed DVD capacity
        assert fits is False

    def test_get_successfully_converted_videos(
        self, dvd_author, sample_converted_videos
    ):
        """Test filtering successfully converted videos."""
        # All videos should be successful initially
        successful = dvd_author.get_successfully_converted_videos(
            sample_converted_videos
        )
        assert len(successful) == 2

        # Create a video with missing file
        missing_video = ConvertedVideoFile(
            metadata=sample_converted_videos[0].metadata,
            video_file=Path("/nonexistent/video.mpg"),
            file_size=1000,
            checksum="test",
            duration=120,
            resolution="720x480",
            video_codec="mpeg2video",
            audio_codec="ac3",
        )

        videos_with_missing = sample_converted_videos + [missing_video]
        successful = dvd_author.get_successfully_converted_videos(videos_with_missing)
        assert len(successful) == 2  # Should exclude missing video

    def test_normalize_video_path(self, dvd_author, tmp_path):
        """Test video path normalization for ASCII compatibility."""
        # Create test video with Unicode filename
        unicode_video = tmp_path / "tëst_vídéo.mpg"
        unicode_video.write_text("test content")

        normalized_path = dvd_author._normalize_video_path(unicode_video)

        # Should create ASCII-safe filename
        assert "test_video" in str(normalized_path)
        assert normalized_path.exists()

    @patch("subprocess.run")
    def test_run_dvdauthor_success(self, mock_subprocess, dvd_author, tmp_path):
        """Test successful dvdauthor execution."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<dvdauthor></dvdauthor>")
        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        # Mock successful subprocess run
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "INFO: dvdauthor success"
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        creation_time = dvd_author._run_dvdauthor(xml_file, video_ts_dir)

        # Check subprocess was called correctly
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert "dvdauthor" in call_args[0][0][0]  # Check dvdauthor command is used
        assert "-x" in call_args[0][0]
        assert str(xml_file) in call_args[0][0]

        assert creation_time > 0

    @patch("subprocess.run")
    def test_run_dvdauthor_failure(self, mock_subprocess, dvd_author, tmp_path):
        """Test dvdauthor execution failure."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<dvdauthor></dvdauthor>")
        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        # Mock failed subprocess run
        error = subprocess.CalledProcessError(1, "dvdauthor")
        error.stdout = ""
        error.stderr = "ERROR: invalid XML"
        mock_subprocess.side_effect = error

        with pytest.raises(DVDAuthoringError, match="dvdauthor execution failed"):
            dvd_author._run_dvdauthor(xml_file, video_ts_dir)

    @patch("shutil.which")
    def test_run_dvdauthor_tool_not_found(self, mock_which, dvd_author, tmp_path):
        """Test dvdauthor when tool is not found."""
        xml_file = tmp_path / "test.xml"
        video_ts_dir = tmp_path / "VIDEO_TS"

        # Mock shutil.which to return None (tool not found)
        mock_which.return_value = None

        with pytest.raises(DVDAuthoringError, match="dvdauthor not found"):
            dvd_author._run_dvdauthor(xml_file, video_ts_dir)

    @patch("subprocess.run")
    def test_create_iso_success(self, mock_subprocess, dvd_author, tmp_path):
        """Test successful ISO creation."""
        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        # Mock genisoimage availability check and ISO creation
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--version" in cmd:
                # Tool availability check
                result = Mock()
                result.returncode = 0
                result.stdout = "genisoimage 1.1.11"
                result.stderr = ""
                return result
            else:
                # ISO creation
                result = Mock()
                result.returncode = 0
                result.stdout = "ISO creation successful"
                result.stderr = ""
                return result

        mock_subprocess.side_effect = subprocess_side_effect

        iso_file = dvd_author._create_iso(tmp_path, video_ts_dir)

        assert iso_file == tmp_path / "dvd.iso"
        assert mock_subprocess.call_count == 2  # Version check + ISO creation

    @patch("subprocess.run")
    def test_create_iso_no_tool(self, mock_subprocess, dvd_author, tmp_path):
        """Test ISO creation when no tool is available."""
        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir()

        # Mock no ISO tools available
        mock_subprocess.side_effect = FileNotFoundError()

        with pytest.raises(DVDAuthoringError, match="No ISO creation tool found"):
            dvd_author._create_iso(tmp_path, video_ts_dir)

    @patch("src.services.dvd_author.DVDAuthor._run_dvdauthor")
    @patch("src.services.dvd_author.DVDAuthor._create_dvd_xml")
    def test_create_dvd_structure_success(
        self,
        mock_create_xml,
        mock_run_dvdauthor,
        dvd_author,
        sample_converted_videos,
        tmp_path,
    ):
        """Test successful DVD structure creation."""
        # Mock XML creation
        xml_file = tmp_path / "test.xml"
        mock_create_xml.return_value = xml_file

        # Mock dvdauthor run
        mock_run_dvdauthor.return_value = 25.5

        # Create required DVD files for validation
        video_ts_dir = tmp_path / "output" / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)
        required_files = [
            "VIDEO_TS.IFO",
            "VIDEO_TS.BUP",
            "VIDEO_TS.VOB",
            "VTS_01_0.IFO",
            "VTS_01_0.BUP",
            "VTS_01_1.VOB",
        ]
        for filename in required_files:
            (video_ts_dir / filename).touch()

        authored_dvd = dvd_author.create_dvd_structure(
            converted_videos=sample_converted_videos,
            menu_title="Test DVD",
            output_dir=tmp_path / "output",
            create_iso=False,
        )

        assert isinstance(authored_dvd, AuthoredDVD)
        assert authored_dvd.dvd_structure.menu_title == "Test DVD"
        assert authored_dvd.creation_time == 25.5
        assert authored_dvd.iso_file is None
        assert len(authored_dvd.dvd_structure.chapters) == 2

        # Check progress callbacks were called
        assert dvd_author.progress_callback.call_count > 0

    def test_create_dvd_structure_no_videos(self, dvd_author, tmp_path):
        """Test DVD structure creation with no videos."""
        with pytest.raises(DVDAuthoringError, match="No videos provided"):
            dvd_author.create_dvd_structure(
                converted_videos=[],
                menu_title="Test DVD",
                output_dir=tmp_path / "output",
            )

    @patch("src.services.dvd_author.DVDAuthor._run_dvdauthor")
    @patch("src.services.dvd_author.DVDAuthor._create_dvd_xml")
    def test_create_dvd_structure_capacity_warning(
        self, mock_create_xml, mock_run_dvdauthor, dvd_author, tmp_path
    ):
        """Test DVD structure creation with capacity warning."""
        # Create large video files that exceed DVD capacity
        large_videos = []
        for i in range(2):
            metadata = VideoMetadata(
                video_id=f"large_video{i}",
                title=f"Large Video {i}",
                duration=120,
                url=f"https://example.com/large{i}",
            )

            video_file = tmp_path / f"large{i}.mpg"
            video_file.write_text("large video content")

            large_video = ConvertedVideoFile(
                metadata=metadata,
                video_file=video_file,
                file_size=3 * 1024 * 1024 * 1024,  # 3GB each = 6GB total > 4.7GB
                checksum=f"checksum{i}",
                duration=120,
                resolution="720x480",
                video_codec="mpeg2video",
                audio_codec="ac3",
            )
            large_videos.append(large_video)

        # Mock XML creation and dvdauthor run
        xml_file = tmp_path / "test.xml"
        mock_create_xml.return_value = xml_file
        mock_run_dvdauthor.return_value = 30.0

        # Create required DVD files for validation
        video_ts_dir = tmp_path / "output" / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)
        required_files = [
            "VIDEO_TS.IFO",
            "VIDEO_TS.BUP",
            "VIDEO_TS.VOB",
            "VTS_01_0.IFO",
            "VTS_01_0.BUP",
            "VTS_01_1.VOB",
        ]
        for filename in required_files:
            (video_ts_dir / filename).touch()

        # Should succeed but log capacity warning
        authored_dvd = dvd_author.create_dvd_structure(
            converted_videos=large_videos,
            menu_title="Large DVD",
            output_dir=tmp_path / "output",
        )

        assert isinstance(authored_dvd, AuthoredDVD)
        assert authored_dvd.dvd_structure.size_gb > 4.7

    def test_report_progress(self, dvd_author, mock_progress_callback):
        """Test progress reporting."""
        dvd_author._report_progress("Test message", 0.5)

        mock_progress_callback.assert_called_once_with("Test message", 0.5)

    def test_create_dvd_xml(self, dvd_author, sample_converted_videos, tmp_path):
        """Test DVD XML creation."""
        # Create DVD structure
        chapters = dvd_author._create_chapters(sample_converted_videos)
        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test DVD",
            total_size=1000,
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)

        xml_file = dvd_author._create_dvd_xml(dvd_structure, video_ts_dir)

        assert xml_file.exists()
        assert xml_file.name == "dvd_structure.xml"

        # Read and verify XML content
        xml_content = xml_file.read_text()
        assert "<dvdauthor" in xml_content
        assert "<vmgm>" in xml_content
        assert "<titleset>" in xml_content
        assert str(video_ts_dir) in xml_content
        # Check for video format specification (NTSC is default in settings)
        assert 'videoformat="NTSC"' in xml_content

    def test_create_dvd_xml_with_pal_format(
        self, dvd_author, sample_converted_videos, tmp_path
    ):
        """Test DVD XML creation with PAL format."""
        # Change settings to PAL
        dvd_author.settings.video_format = "PAL"

        # Create DVD structure
        chapters = dvd_author._create_chapters(sample_converted_videos)
        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test PAL DVD",
            total_size=1000,
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)

        xml_file = dvd_author._create_dvd_xml(dvd_structure, video_ts_dir)

        # Read and verify XML content includes PAL format
        xml_content = xml_file.read_text()
        assert "<dvdauthor" in xml_content
        assert "<vmgm>" in xml_content
        assert (
            'videoformat="PAL"' in xml_content
        )  # Should be uppercase for videoformat attribute

    def test_create_dvd_xml_case_insensitive_format(
        self, dvd_author, sample_converted_videos, tmp_path
    ):
        """Test DVD XML creation handles case insensitive format."""
        # Test lowercase input
        dvd_author.settings.video_format = "ntsc"

        # Create DVD structure
        chapters = dvd_author._create_chapters(sample_converted_videos)
        dvd_structure = DVDStructure(
            chapters=chapters,
            menu_title="Test DVD",
            total_size=1000,
        )

        video_ts_dir = tmp_path / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)

        xml_file = dvd_author._create_dvd_xml(dvd_structure, video_ts_dir)

        # Should still output uppercase for videoformat attribute
        xml_content = xml_file.read_text()
        assert 'videoformat="NTSC"' in xml_content

    @patch("src.services.dvd_author.DVDAuthor._run_dvdauthor")
    @patch("src.services.dvd_author.DVDAuthor._create_dvd_xml")
    @patch("src.services.dvd_author.DVDAuthor._create_iso")
    def test_create_dvd_structure_with_iso(
        self,
        mock_create_iso,
        mock_create_xml,
        mock_run_dvdauthor,
        dvd_author,
        sample_converted_videos,
        tmp_path,
    ):
        """Test DVD structure creation with ISO generation."""
        # Mock functions
        xml_file = tmp_path / "test.xml"
        iso_file = tmp_path / "output" / "dvd.iso"
        mock_create_xml.return_value = xml_file
        mock_run_dvdauthor.return_value = 25.5
        mock_create_iso.return_value = iso_file

        # Create required DVD files for validation
        video_ts_dir = tmp_path / "output" / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)
        required_files = [
            "VIDEO_TS.IFO",
            "VIDEO_TS.BUP",
            "VIDEO_TS.VOB",
            "VTS_01_0.IFO",
            "VTS_01_0.BUP",
            "VTS_01_1.VOB",
        ]
        for filename in required_files:
            (video_ts_dir / filename).touch()

        authored_dvd = dvd_author.create_dvd_structure(
            converted_videos=sample_converted_videos,
            menu_title="Test DVD",
            output_dir=tmp_path / "output",
            create_iso=True,
        )

        assert authored_dvd.iso_file == iso_file
        mock_create_iso.assert_called_once_with(tmp_path / "output", video_ts_dir)

    @patch("src.services.dvd_author.DVDAuthor._run_dvdauthor")
    @patch("src.services.dvd_author.DVDAuthor._create_dvd_xml")
    def test_create_dvd_structure_validation_failure(
        self,
        mock_create_xml,
        mock_run_dvdauthor,
        dvd_author,
        sample_converted_videos,
        tmp_path,
    ):
        """Test DVD structure creation with validation failure."""
        # Mock XML creation and dvdauthor run
        xml_file = tmp_path / "test.xml"
        mock_create_xml.return_value = xml_file
        mock_run_dvdauthor.return_value = 25.5

        # Don't create required DVD files - validation should fail
        video_ts_dir = tmp_path / "output" / "VIDEO_TS"
        video_ts_dir.mkdir(parents=True)

        with pytest.raises(
            DVDStructureCreationError, match="Created DVD structure is invalid"
        ):
            dvd_author.create_dvd_structure(
                converted_videos=sample_converted_videos,
                menu_title="Test DVD",
                output_dir=tmp_path / "output",
            )
