"""Private storage for optional leave handover-plan files."""

from pathlib import Path
import re
from uuid import uuid4


ALLOWED_LEAVE_PLAN_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".txt",
}


class LeaveFileStorage:
    """Write, read, and remove company-scoped handover-plan files."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip()
        stem = re.sub(
            r"[^a-zA-Z0-9._-]+",
            "_",
            Path(name).stem,
        ).strip("._")
        suffix = Path(name).suffix.lower()
        return f"{stem or 'handover_plan'}{suffix}"

    def validate(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        maximum_size_bytes: int,
    ) -> None:
        """Validate an optional work handover-plan file."""

        suffix = Path(filename).suffix.lower()

        if suffix not in ALLOWED_LEAVE_PLAN_EXTENSIONS:
            raise ValueError(
                "Handover plan file must be PDF, DOCX, XLSX, CSV, or TXT."
            )

        if not file_bytes:
            raise ValueError(
                "The handover plan file is empty."
            )

        if len(file_bytes) > maximum_size_bytes:
            raise ValueError(
                "The handover plan file exceeds the maximum size."
            )

    def write(
        self,
        *,
        company_id: int,
        filename: str,
        file_bytes: bytes,
    ) -> str:
        """Store one file beneath its company directory."""

        relative = (
            Path(f"company_{company_id}")
            / f"{uuid4().hex}_{self._safe_filename(filename)}"
        )
        destination = (
            self.root_dir / relative
        ).resolve()

        if self.root_dir not in destination.parents:
            raise ValueError(
                "Invalid handover plan file path."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        destination.write_bytes(file_bytes)

        return relative.as_posix()

    def read(self, storage_path: str) -> bytes:
        """Read one authorized stored plan file."""

        path = (
            self.root_dir / storage_path
        ).resolve()

        if (
            self.root_dir not in path.parents
            or not path.is_file()
        ):
            raise FileNotFoundError(
                "Handover plan file is unavailable."
            )

        return path.read_bytes()

    def delete(self, storage_path: str | None) -> None:
        """Remove a partially written file after transaction failure."""

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
