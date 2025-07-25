"""DVD-related data models."""

from dataclasses import dataclass
from typing import List

from .video import VideoFile


@dataclass(frozen=True)
class DVDChapter:
    """Represents a single chapter in a DVD title."""

    chapter_number: int
    video_file: VideoFile
    start_time: int  # Start time in concatenated video (seconds)

    def __post_init__(self) -> None:
        """Validate DVD chapter after initialization."""
        if self.chapter_number <= 0:
            raise ValueError("chapter_number must be positive")
        if self.start_time < 0:
            raise ValueError("start_time must be non-negative")

    @property
    def duration(self) -> int:
        """Get the duration of the video file in seconds."""
        return self.video_file.metadata.duration

    @property
    def end_time(self) -> int:
        """Calculate the end time of this chapter."""
        return self.start_time + self.duration

    @property
    def size_mb(self) -> float:
        """Get the size of the video file in MB."""
        return self.video_file.size_mb

    @property
    def title(self) -> str:
        """Get the title of the video."""
        return self.video_file.metadata.title


@dataclass
class DVDStructure:
    """Represents a DVD with a single title containing multiple chapters."""

    chapters: List[DVDChapter]  # Single title with multiple chapters
    menu_title: str
    total_size: int  # Total size in bytes

    def __post_init__(self) -> None:
        """Validate DVD structure after initialization."""
        if not self.chapters:
            raise ValueError("DVD must have at least one chapter")
        if not self.menu_title:
            raise ValueError("menu_title cannot be empty")
        if self.total_size < 0:
            raise ValueError("total_size must be non-negative")

        # Validate chapter numbers are unique and sequential
        chapter_numbers = [chapter.chapter_number for chapter in self.chapters]
        if len(set(chapter_numbers)) != len(chapter_numbers):
            raise ValueError("Chapter numbers must be unique")

        expected_numbers = list(range(1, len(self.chapters) + 1))
        if sorted(chapter_numbers) != expected_numbers:
            raise ValueError("Chapter numbers must be sequential starting from 1")

        # Validate start times are in ascending order
        for i in range(1, len(self.chapters)):
            current_chapter = self.get_chapter_by_number(i + 1)
            previous_chapter = self.get_chapter_by_number(i)

            if current_chapter.start_time < previous_chapter.end_time:
                raise ValueError(
                    f"Chapter {i + 1} start time conflicts with chapter {i} end time"
                )

    @property
    def chapter_count(self) -> int:
        """Get the number of chapters in the DVD."""
        return len(self.chapters)

    @property
    def total_duration(self) -> int:
        """Get the total duration of all chapters in seconds."""
        if not self.chapters:
            return 0
        # Duration is from start of first chapter to end of last chapter
        last_chapter = max(self.chapters, key=lambda c: c.chapter_number)
        return last_chapter.end_time

    @property
    def size_mb(self) -> float:
        """Get the total size in MB."""
        return self.total_size / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        """Get the total size in GB."""
        return self.total_size / (1024 * 1024 * 1024)

    def fits_on_dvd(self, dvd_capacity_gb: float = 4.7) -> bool:
        """Check if the DVD structure fits on a standard DVD.

        Args:
            dvd_capacity_gb: DVD capacity in GB (default 4.7GB for single layer)

        Returns:
            True if DVD structure fits, False otherwise
        """
        return self.size_gb <= dvd_capacity_gb

    def get_chapter_by_number(self, chapter_number: int) -> DVDChapter:
        """Get a chapter by its number.

        Args:
            chapter_number: The chapter number to find

        Returns:
            The DVDChapter with the specified number

        Raises:
            ValueError: If chapter number is not found
        """
        for chapter in self.chapters:
            if chapter.chapter_number == chapter_number:
                return chapter
        raise ValueError(f"Chapter number {chapter_number} not found")

    def get_chapters_ordered(self) -> List[DVDChapter]:
        """Get chapters ordered by chapter number."""
        return sorted(self.chapters, key=lambda c: c.chapter_number)

    def get_chapter_times(self) -> List[int]:
        """Get list of chapter start times for DVD authoring."""
        ordered_chapters = self.get_chapters_ordered()
        return [chapter.start_time for chapter in ordered_chapters]
