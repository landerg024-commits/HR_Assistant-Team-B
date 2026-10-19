"""Private company-scoped storage for announcement cover images."""

from pathlib import Path
import re
from uuid import uuid4


_ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


class AnnouncementImageStorage:
    """Validate and persist announcement images outside the database."""

    def __init__(
        self,
        root_dir: str | Path,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Remove path data and unsafe filename characters."""

        original = Path(filename).name.strip()
        stem = re.sub(
            r"[^a-zA-Z0-9._-]+",
            "_",
            Path(original).stem,
        ).strip("._")
        suffix = Path(original).suffix.lower()

        return f"{stem or 'announcement'}{suffix}"

    @staticmethod
    def _has_valid_signature(
        suffix: str,
        file_bytes: bytes,
    ) -> bool:
        """Check common image signatures instead of trusting extension only."""

        if suffix == ".png":
            return file_bytes.startswith(
                b"\x89PNG\r\n\x1a\n"
            )

        if suffix in {".jpg", ".jpeg"}:
            return file_bytes.startswith(
                b"\xff\xd8\xff"
            )

        if suffix == ".webp":
            return (
                len(file_bytes) >= 12
                and file_bytes[:4] == b"RIFF"
                and file_bytes[8:12] == b"WEBP"
            )

        return False

    def validate(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        maximum_size_bytes: int,
    ) -> None:
        """Reject unsupported, empty, oversized, or disguised files."""

        suffix = Path(filename).suffix.lower()

        if suffix not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                "Announcement image must be JPG, JPEG, PNG, or WEBP."
            )

        if not file_bytes:
            raise ValueError(
                "The announcement image is empty."
            )

        if len(file_bytes) > maximum_size_bytes:
            raise ValueError(
                "The announcement image exceeds the maximum size."
            )

        if not self._has_valid_signature(
            suffix,
            file_bytes,
        ):
            raise ValueError(
                "The uploaded file is not a valid supported image."
            )

    def write(
        self,
        *,
        company_id: int,
        filename: str,
        file_bytes: bytes,
    ) -> str:
        """Store one image beneath a company-specific directory."""

        relative_path = (
            Path(f"company_{company_id}")
            / (
                f"{uuid4().hex}_"
                f"{self._safe_filename(filename)}"
            )
        )
        destination = (
            self.root_dir / relative_path
        ).resolve()

        if self.root_dir not in destination.parents:
            raise ValueError(
                "Invalid announcement image path."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        destination.write_bytes(file_bytes)

        return relative_path.as_posix()

    def read(
        self,
        storage_path: str,
    ) -> bytes:
        """Read one authorized image path."""

        path = (
            self.root_dir / storage_path
        ).resolve()

        if (
            self.root_dir not in path.parents
            or not path.is_file()
        ):
            raise FileNotFoundError(
                "Announcement image is unavailable."
            )

        return path.read_bytes()

    def delete(
        self,
        storage_path: str | None,
    ) -> None:
        """Remove one stored image when it is replaced or discarded."""

        if not storage_path:
            return

        path = (
            self.root_dir / storage_path
        ).resolve()

        if (
            self.root_dir in path.parents
            and path.is_file()
        ):
            path.unlink()
