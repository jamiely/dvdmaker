"""Video conversion service for DVD Maker.

This module handles converting downloaded videos to DVD-compatible formats
using ffmpeg, including MPEG-2 video conversion, audio standardization,
and thumbnail generation.
"""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config.settings import Settings
from ..exceptions import DVDMakerError
from ..models.video import VideoFile, VideoMetadata
from ..services.cache_manager import CacheManager
from ..services.tool_manager import ToolManager
from .base import BaseService

# Progress callback type
ProgressCallback = Callable[[str, float], None]


class VideoConverterError(DVDMakerError):
    """Base exception for video converter errors."""

    pass


class ConversionError(VideoConverterError):
    """Exception raised when video conversion fails."""

    pass


class ConvertedVideoFile:
    """Represents a converted video file with DVD-compatible format."""

    def __init__(
        self,
        metadata: VideoMetadata,
        video_file: Path,
        thumbnail_file: Optional[Path] = None,
        file_size: int = 0,
        checksum: str = "",
        duration: int = 0,
        resolution: str = "",
        video_codec: str = "",
        audio_codec: str = "",
    ):
        """Initialize converted video file.

        Args:
            metadata: Original video metadata
            video_file: Path to converted video file
            thumbnail_file: Optional path to thumbnail file
            file_size: Size of converted file in bytes
            checksum: SHA-256 checksum of converted file
            duration: Duration in seconds
            resolution: Video resolution (e.g., "720x480")
            video_codec: Video codec used
            audio_codec: Audio codec used
        """
        self.metadata = metadata
        self.video_file = video_file
        self.thumbnail_file = thumbnail_file
        self.file_size = file_size
        self.checksum = checksum
        self.duration = duration
        self.resolution = resolution
        self.video_codec = video_codec
        self.audio_codec = audio_codec

    @property
    def exists(self) -> bool:
        """Check if the converted video file exists."""
        return self.video_file.exists()

    @property
    def size_mb(self) -> float:
        """Get file size in MB."""
        return self.file_size / (1024 * 1024)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "video_id": self.metadata.video_id,
            "video_file": str(self.video_file),
            "thumbnail_file": str(self.thumbnail_file) if self.thumbnail_file else None,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "duration": self.duration,
            "resolution": self.resolution,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], metadata: VideoMetadata
    ) -> "ConvertedVideoFile":
        """Create from dictionary."""
        return cls(
            metadata=metadata,
            video_file=Path(data["video_file"]),
            thumbnail_file=(
                Path(data["thumbnail_file"]) if data["thumbnail_file"] else None
            ),
            file_size=data["file_size"],
            checksum=data["checksum"],
            duration=data["duration"],
            resolution=data["resolution"],
            video_codec=data["video_codec"],
            audio_codec=data["audio_codec"],
        )


class VideoConverter(BaseService):
    """Converts videos to DVD-compatible formats using ffmpeg.

    This class handles:
    - Video format conversion to MPEG-2
    - Audio conversion to AC-3 or PCM
    - Aspect ratio and frame rate handling
    - Thumbnail generation for DVD menus
    - Caching of converted files
    - Progress reporting during conversion
    """

    # DVD-compatible video specifications
    NTSC_RESOLUTION = "720x480"
    PAL_RESOLUTION = "720x576"
    NTSC_FRAMERATE = "29.97"
    PAL_FRAMERATE = "25"
    VIDEO_CODEC = "mpeg2video"
    AUDIO_CODEC = "ac3"
    AUDIO_BITRATE = "448k"
    VIDEO_BITRATE = "6000k"

    def __init__(
        self,
        settings: Settings,
        tool_manager: ToolManager,
        cache_manager: CacheManager,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Initialize the video converter.

        Args:
            settings: Application settings
            tool_manager: Tool manager for ffmpeg access
            cache_manager: Cache manager for converted files
            progress_callback: Optional callback for progress reporting
        """
        super().__init__(settings)
        self.tool_manager = tool_manager
        self.cache_manager = cache_manager
        self.progress_callback = progress_callback

        # Ensure converted cache directory exists
        self.converted_cache_dir = settings.cache_dir / "converted"
        self.converted_cache_dir.mkdir(parents=True, exist_ok=True)

        # Metadata cache for converted files
        self.metadata_file = self.converted_cache_dir / "converted_metadata.json"

        self.logger.debug(
            f"VideoConverter initialized with cache dir: {self.converted_cache_dir}"
        )

    def _load_converted_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Load metadata for converted files.

        Returns:
            Dictionary mapping video IDs to conversion metadata
        """
        if not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, "r") as f:
                metadata: Dict[str, Dict[str, Any]] = json.load(f)
            self.logger.debug(f"Loaded converted metadata for {len(metadata)} videos")
            return metadata
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load converted metadata: {e}")
            return {}

    def _save_converted_metadata(self, metadata: Dict[str, Dict[str, Any]]) -> None:
        """Save metadata for converted files.

        Args:
            metadata: Dictionary mapping video IDs to conversion metadata
        """
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
            self.logger.debug(f"Saved converted metadata for {len(metadata)} videos")
        except IOError as e:
            self.logger.error(f"Failed to save converted metadata: {e}")

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA-256 checksum as hex string
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except IOError as e:
            self.logger.error(f"Failed to calculate checksum for {file_path}: {e}")
            return ""

    def _get_ffprobe_command(self) -> List[str]:
        """Get ffprobe command based on the ffmpeg command.

        Returns:
            List containing ffprobe command components
        """
        ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")
        # Replace ffmpeg with ffprobe in the path
        ffmpeg_path = Path(ffmpeg_cmd[0])
        ffprobe_path = ffmpeg_path.parent / ffmpeg_path.name.replace(
            "ffmpeg", "ffprobe"
        )
        return [str(ffprobe_path)]

    def _get_video_info(self, video_path: Path) -> Dict[str, Any]:
        """Get video information using ffprobe.

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with video information

        Raises:
            ConversionError: If ffprobe fails
        """
        self.logger.debug(f"Getting video info for {video_path}")

        try:
            ffprobe_cmd = self._get_ffprobe_command()

            cmd = ffprobe_cmd + [
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(video_path),
            ]

            self.logger.debug(f"Executing ffprobe command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.logger.debug(f"ffprobe completed with return code {result.returncode}")

            if result.stderr:
                if result.returncode == 0:
                    self.logger.debug(f"ffprobe stderr: {result.stderr.strip()}")
                else:
                    self.logger.warning(f"ffprobe stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                raise ConversionError(f"ffprobe failed: {result.stderr}")

            info: Dict[str, Any] = json.loads(result.stdout)
            self.logger.debug(
                f"Successfully extracted video info for {video_path.name}"
            )
            return info

        except (
            subprocess.SubprocessError,
            json.JSONDecodeError,
            FileNotFoundError,
        ) as e:
            self.logger.error(f"Failed to get video info for {video_path}: {e}")
            raise ConversionError(f"Failed to analyze video: {e}")

    def _determine_dvd_format(self, video_info: Dict[str, Any]) -> Tuple[str, str]:
        """Determine DVD format based on settings.

        Args:
            video_info: Video information from ffprobe (used for logging only)

        Returns:
            Tuple of (resolution, framerate)
        """
        # Use format from settings
        video_format = self.settings.video_format.upper()

        if video_format == "PAL":
            self.logger.debug(
                f"Using PAL format from settings: {self.PAL_RESOLUTION} at "
                f"{self.PAL_FRAMERATE} fps"
            )
            return self.PAL_RESOLUTION, self.PAL_FRAMERATE
        else:  # Default to NTSC
            self.logger.debug(
                f"Using NTSC format from settings: {self.NTSC_RESOLUTION} at "
                f"{self.NTSC_FRAMERATE} fps"
            )
            return self.NTSC_RESOLUTION, self.NTSC_FRAMERATE

    def _build_conversion_command(
        self,
        input_path: Path,
        output_path: Path,
        resolution: str,
        framerate: str,
    ) -> List[str]:
        """Build ffmpeg command for DVD conversion.

        Args:
            input_path: Input video file path
            output_path: Output video file path
            resolution: Target resolution
            framerate: Target frame rate

        Returns:
            List of command arguments
        """
        ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")

        # Determine format-specific settings
        is_ntsc = "480" in resolution

        if self.settings.car_dvd_compatibility:
            self.logger.debug("Using car DVD compatibility encoding settings")
            # Conservative settings for maximum car DVD player compatibility
            # Based on strict DVD-Video spec compliance for Honda Odyssey and similar
            cmd = ffmpeg_cmd + [
                "-i",
                str(input_path),
                "-c:v",
                self.VIDEO_CODEC,
                "-pix_fmt",
                "yuv420p",  # Standard DVD pixel format
                # Interlaced encoding (DVD spec assumes interlaced, top-field-first)
                "-flags",
                "+ilme+ildct",  # Interlaced motion estimation and DCT
                "-top",
                "1",  # Top field first
                # Video bitrate settings
                "-b:v",
                "3500k",  # Conservative bitrate for car players
                "-maxrate",
                "6000k",  # Lower max rate for compatibility
                "-minrate",
                "3500k",  # Match average bitrate to avoid buffer under-runs
                "-bufsize",
                "1835008",  # DVD buffer size
                "-s",
                resolution,
                "-r",
                framerate,
                # Aspect ratio handling - set both DAR and SAR for compatibility
                "-aspect",
                self.settings.aspect_ratio,
                "-vf",
                "yadif=0:-1:0,setsar=32/27",  # Deinterlace if needed + set SAR for 16:9
                # GOP settings for car DVD compatibility
                "-g",
                "12",  # Shorter GOP for better seeking
                "-bf",
                "0",  # No B-frames for better compatibility
                # Audio settings - AC-3 is more universally supported than PCM
                "-c:a",
                self.AUDIO_CODEC,  # Use AC-3 instead of PCM
                "-b:a",
                "192k",  # Standard AC-3 bitrate for DVD
                "-ac",
                "2",  # Stereo audio
                "-ar",
                "48000",  # 48kHz sample rate for DVD
                # DVD multiplexing settings (simplified - let -f dvd handle details)
                "-f",
                "dvd",  # DVD format for proper multiplexing
                "-y",  # Overwrite output file
                str(output_path),
            ]
        else:
            # Standard encoding with more advanced settings
            gop_size = "15" if is_ntsc else "12"  # GOP size for NTSC/PAL

            cmd = ffmpeg_cmd + [
                "-i",
                str(input_path),
                "-c:v",
                self.VIDEO_CODEC,
                "-pix_fmt",
                "yuv420p",  # Standard DVD pixel format
                "-b:v",
                self.VIDEO_BITRATE,
                "-s",
                resolution,
                "-r",
                framerate,
                "-aspect",
                self.settings.aspect_ratio,
                # Advanced video encoding settings
                "-flags",
                "+ilme+ildct",  # Enable interlaced motion estimation and DCT
                "-top",
                "1",  # Top field first for interlaced content
                "-g",
                gop_size,  # GOP size (15 for NTSC, 12 for PAL)
                "-bf",
                "2",  # B-frames
                "-flags2",
                "+bpyramid",  # B-frame pyramid (standard mode only)
                "-sc_threshold",
                "40",  # Scene change threshold
                "-colorspace",
                "bt470bg" if not is_ntsc else "smpte170m",  # Color space for PAL/NTSC
                "-color_primaries",
                "bt470bg" if not is_ntsc else "smpte170m",
                "-color_trc",
                "gamma28" if not is_ntsc else "smpte170m",
                # Audio settings
                "-c:a",
                self.AUDIO_CODEC,
                "-b:a",
                self.AUDIO_BITRATE,
                "-ac",
                "2",  # Stereo audio
                "-ar",
                "48000",  # 48kHz sample rate for DVD
                # DVD multiplexing settings
                "-f",
                "dvd",  # DVD format for proper multiplexing
                "-muxrate",
                "10080000",  # DVD mux rate (10.08 Mbps)
                "-maxrate",
                "8000000",  # Lower max rate for better compatibility
                "-minrate",
                "0",  # Minimum video bitrate
                "-bufsize",
                "1835008",  # DVD buffer size
                "-packetsize",
                "2048",  # DVD packet size
                "-muxpreload",
                "0.2",  # Preload time for multiplexer
                "-y",  # Overwrite output file
                str(output_path),
            ]

        self.logger.debug(f"Built conversion command: {' '.join(cmd)}")
        return cmd

    def _build_thumbnail_command(
        self,
        input_path: Path,
        output_path: Path,
        timestamp: int = 30,
    ) -> List[str]:
        """Build ffmpeg command for thumbnail generation.

        Args:
            input_path: Input video file path
            output_path: Output thumbnail file path
            timestamp: Timestamp in seconds to extract thumbnail

        Returns:
            List of command arguments
        """
        ffmpeg_cmd = self.tool_manager.get_tool_command("ffmpeg")

        cmd = ffmpeg_cmd + [
            "-i",
            str(input_path),
            "-ss",
            str(timestamp),
            "-vframes",
            "1",
            "-s",
            "160x120",  # Standard DVD menu thumbnail size
            "-y",  # Overwrite output file
            str(output_path),
        ]

        self.logger.debug(f"Built thumbnail command: {' '.join(cmd)}")
        return cmd

    def _run_conversion_command(
        self,
        cmd: List[str],
        operation_name: str,
        estimated_duration: int = 0,
    ) -> None:
        """Run a conversion command with progress reporting.

        Args:
            cmd: Command to run
            operation_name: Name of the operation for progress reporting
            estimated_duration: Estimated duration for progress calculation

        Raises:
            ConversionError: If command fails
        """
        self.logger.debug(f"Running {operation_name}: {' '.join(cmd[:3])}...")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
            )

            stderr_output = []
            while True:
                if process.poll() is not None:
                    break

                if process.stderr:
                    line = process.stderr.readline()
                    if line:
                        stderr_output.append(line)

                        # Extract progress from ffmpeg output
                        if (
                            self.progress_callback
                            and "time=" in line
                            and estimated_duration > 0
                        ):
                            try:
                                time_part = [
                                    part
                                    for part in line.split()
                                    if part.startswith("time=")
                                ]
                                if time_part:
                                    time_str = time_part[0].split("=")[1]
                                    # Parse time format HH:MM:SS.fff
                                    time_parts = time_str.split(":")
                                    if len(time_parts) == 3:
                                        hours = float(time_parts[0])
                                        minutes = float(time_parts[1])
                                        seconds = float(time_parts[2])
                                        current_seconds = (
                                            hours * 3600 + minutes * 60 + seconds
                                        )
                                        progress = min(
                                            (current_seconds / estimated_duration)
                                            * 100,
                                            100,
                                        )
                                        self.progress_callback(operation_name, progress)
                            except (ValueError, IndexError):
                                pass

            # Wait for process to complete
            stdout, stderr = process.communicate()

            if stderr:
                stderr_output.append(stderr)

            if process.returncode != 0:
                error_output = "".join(stderr_output)
                self.logger.error(f"{operation_name} failed: {error_output}")
                raise ConversionError(f"{operation_name} failed: {error_output}")

            self.logger.debug(f"{operation_name} completed successfully")

        except subprocess.SubprocessError as e:
            self.logger.error(f"{operation_name} failed with exception: {e}")
            raise ConversionError(f"{operation_name} failed: {e}")

    def is_video_converted(self, video_metadata: VideoMetadata) -> bool:
        """Check if a video has already been converted.

        Args:
            video_metadata: Video metadata to check

        Returns:
            True if video is already converted and cached
        """
        metadata = self._load_converted_metadata()
        video_id = video_metadata.video_id

        if video_id not in metadata:
            self.logger.debug(f"Video {video_id} not found in converted cache")
            return False

        video_data = metadata[video_id]
        video_file = Path(video_data["video_file"])

        # Check if file exists and has correct size/checksum
        if not video_file.exists():
            self.logger.debug(f"Converted file for {video_id} does not exist")
            return False

        # Verify file integrity
        actual_size = video_file.stat().st_size
        if actual_size != video_data["file_size"]:
            self.logger.warning(
                f"Size mismatch for converted {video_id}: "
                f"expected {video_data['file_size']}, got {actual_size}"
            )
            return False

        # Quick checksum verification might be too expensive, trust size for now
        self.logger.debug(f"Video {video_id} found in converted cache and verified")
        return True

    def get_converted_video(
        self, video_metadata: VideoMetadata
    ) -> Optional[ConvertedVideoFile]:
        """Get converted video file from cache.

        Args:
            video_metadata: Video metadata

        Returns:
            ConvertedVideoFile if available, None otherwise
        """
        if not self.is_video_converted(video_metadata):
            return None

        metadata = self._load_converted_metadata()
        video_data = metadata[video_metadata.video_id]

        return ConvertedVideoFile.from_dict(video_data, video_metadata)

    def convert_video(
        self,
        video_file: VideoFile,
        force_convert: bool = False,
    ) -> ConvertedVideoFile:
        """Convert a video to DVD-compatible format.

        Args:
            video_file: Video file to convert
            force_convert: Force conversion even if cached version exists

        Returns:
            ConvertedVideoFile with conversion results

        Raises:
            ConversionError: If conversion fails
        """
        video_id = video_file.metadata.video_id
        self.logger.debug(f"Starting conversion of video {video_id}")

        # Check cache first
        if not force_convert and self.is_video_converted(video_file.metadata):
            self.logger.debug(
                f"Video {video_id} already converted, using cached version"
            )
            converted = self.get_converted_video(video_file.metadata)
            if converted:
                return converted

        # Verify input file exists
        if not video_file.exists:
            raise ConversionError(
                f"Input video file does not exist: {video_file.file_path}"
            )

        # Get video information
        video_info = self._get_video_info(video_file.file_path)

        # Determine DVD format
        resolution, framerate = self._determine_dvd_format(video_info)

        # Create output paths
        output_dir = self.converted_cache_dir / video_id
        output_dir.mkdir(parents=True, exist_ok=True)

        converted_file = output_dir / f"{video_id}_dvd.mpg"
        thumbnail_file = output_dir / f"{video_id}_thumb.jpg"

        # Create temporary files for atomic operations
        with tempfile.NamedTemporaryFile(suffix=".mpg", delete=False) as temp_video:
            temp_video_path = Path(temp_video.name)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_thumb:
            temp_thumb_path = Path(temp_thumb.name)

        try:
            # Convert video
            conversion_cmd = self._build_conversion_command(
                video_file.file_path,
                temp_video_path,
                resolution,
                framerate,
            )

            self._run_conversion_command(
                conversion_cmd,
                f"Converting {video_id}",
                video_file.metadata.duration,
            )

            # Generate thumbnail
            thumbnail_cmd = self._build_thumbnail_command(
                video_file.file_path,
                temp_thumb_path,
                min(30, video_file.metadata.duration // 2),  # Middle of video or 30s
            )

            self._run_conversion_command(
                thumbnail_cmd,
                f"Generating thumbnail for {video_id}",
            )

            # Move files to final location atomically
            temp_video_path.rename(converted_file)
            temp_thumb_path.rename(thumbnail_file)

            # Calculate metadata for converted file
            file_size = converted_file.stat().st_size
            checksum = self._calculate_file_checksum(converted_file)

            # Get converted video info
            converted_info = self._get_video_info(converted_file)
            video_stream: Dict[str, Any] = next(
                (
                    s
                    for s in converted_info.get("streams", [])
                    if s.get("codec_type") == "video"
                ),
                {},
            )
            audio_stream: Dict[str, Any] = next(
                (
                    s
                    for s in converted_info.get("streams", [])
                    if s.get("codec_type") == "audio"
                ),
                {},
            )

            # Create converted video file object
            converted_video = ConvertedVideoFile(
                metadata=video_file.metadata,
                video_file=converted_file,
                thumbnail_file=thumbnail_file,
                file_size=file_size,
                checksum=checksum,
                duration=int(
                    float(converted_info.get("format", {}).get("duration", 0))
                ),
                resolution=(
                    f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}"
                ),
                video_codec=video_stream.get("codec_name", ""),
                audio_codec=audio_stream.get("codec_name", ""),
            )

            # Update metadata cache
            metadata = self._load_converted_metadata()
            metadata[video_id] = converted_video.to_dict()
            self._save_converted_metadata(metadata)

            self.logger.info(
                f"Successfully converted {video_id}: {converted_video.size_mb:.1f}MB "
                f"{converted_video.resolution} "
                f"{converted_video.video_codec}/{converted_video.audio_codec}"
            )

            return converted_video

        except Exception as e:
            # Clean up temporary files
            for temp_file in [temp_video_path, temp_thumb_path]:
                if temp_file.exists():
                    temp_file.unlink()

            # Clean up partial output files
            for output_file in [converted_file, thumbnail_file]:
                if output_file.exists():
                    output_file.unlink()

            self.logger.error(f"Video conversion failed for {video_id}: {e}")
            raise ConversionError(f"Failed to convert video {video_id}: {e}")

    def convert_videos(
        self,
        video_files: List[VideoFile],
        force_convert: bool = False,
    ) -> List[ConvertedVideoFile]:
        """Convert multiple videos to DVD format.

        Args:
            video_files: List of video files to convert
            force_convert: Force conversion even if cached versions exist

        Returns:
            List of converted video files

        Raises:
            ConversionError: If any conversion fails
        """
        self.logger.debug(f"Starting batch conversion of {len(video_files)} videos")

        converted_videos: List[ConvertedVideoFile] = []
        failed_conversions: List[str] = []

        for i, video_file in enumerate(video_files):
            try:
                if self.progress_callback:
                    overall_progress = (i / len(video_files)) * 100
                    self.progress_callback(
                        f"Converting videos ({i+1}/{len(video_files)})",
                        overall_progress,
                    )

                converted_video = self.convert_video(video_file, force_convert)
                converted_videos.append(converted_video)

                self.logger.debug(
                    f"Converted {i+1}/{len(video_files)}: "
                    f"{video_file.metadata.video_id}"
                )

            except ConversionError as e:
                error_msg = f"Failed to convert {video_file.metadata.video_id}: {e}"
                self.logger.error(error_msg)
                failed_conversions.append(error_msg)

        if self.progress_callback:
            self.progress_callback("Video conversion complete", 100)

        self.logger.info(
            f"Batch conversion complete: {len(converted_videos)} successful, "
            f"{len(failed_conversions)} failed"
        )

        if failed_conversions:
            self.logger.warning(f"Some conversions failed: {failed_conversions}")
            # For now, continue with successful conversions
            # In a future version, we might want to make this configurable

        return converted_videos

    def get_conversion_stats(self) -> Dict[str, Any]:
        """Get statistics about converted videos.

        Returns:
            Dictionary with conversion statistics
        """
        metadata = self._load_converted_metadata()

        if not metadata:
            return {
                "total_videos": 0,
                "total_size_mb": 0,
                "average_size_mb": 0,
                "formats": {},
            }

        total_size = sum(data["file_size"] for data in metadata.values())
        formats: Dict[str, int] = {}

        for data in metadata.values():
            codec = f"{data['video_codec']}/{data['audio_codec']}"
            formats[codec] = formats.get(codec, 0) + 1

        stats = {
            "total_videos": len(metadata),
            "total_size_mb": total_size / (1024 * 1024),
            "average_size_mb": (total_size / len(metadata)) / (1024 * 1024),
            "formats": formats,
        }

        self.logger.debug(f"Conversion statistics: {stats}")
        return stats

    def cleanup_cache(self, keep_recent: int = 10) -> None:
        """Clean up old converted files.

        Args:
            keep_recent: Number of recent conversions to keep
        """
        self.logger.info(
            f"Cleaning up conversion cache, keeping {keep_recent} recent files"
        )

        metadata = self._load_converted_metadata()

        if len(metadata) <= keep_recent:
            self.logger.debug("No cleanup needed")
            return

        # Sort by modification time (we'll use video_id as a proxy for now)
        sorted_videos = sorted(metadata.items(), key=lambda x: x[0])

        # Remove oldest files
        videos_to_remove = (
            sorted_videos[:-keep_recent] if keep_recent > 0 else sorted_videos
        )

        for video_id, data in videos_to_remove:
            try:
                video_file = Path(data["video_file"])
                thumbnail_file = data.get("thumbnail_file")

                # Remove files
                if video_file.exists():
                    video_file.unlink()
                    self.logger.debug(f"Removed converted video: {video_file}")

                if thumbnail_file:
                    thumb_path = Path(thumbnail_file)
                    if thumb_path.exists():
                        thumb_path.unlink()
                        self.logger.debug(f"Removed thumbnail: {thumb_path}")

                # Remove directory if empty
                if video_file.parent.exists() and not any(video_file.parent.iterdir()):
                    video_file.parent.rmdir()

                # Remove from metadata
                del metadata[video_id]

            except Exception as e:
                self.logger.warning(f"Failed to remove {video_id} during cleanup: {e}")

        # Save updated metadata
        self._save_converted_metadata(metadata)

        self.logger.info(f"Cleaned up {len(videos_to_remove)} old converted videos")
