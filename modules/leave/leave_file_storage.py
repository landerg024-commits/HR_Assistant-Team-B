"""Private storage for optional leave-request supporting documents."""

from pathlib import Path
import re
from uuid import uuid4


ALLOWED_LEAVE_ATTACHMENT_EXTENSIONS = {
    ".pdf", ".docx", ".png", ".jpg", ".jpeg"
}


class LeaveFileStorage:
    """Write, read, and remove company-scoped leave attachments."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        name = Path(filename).name.strip()
        stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(name).stem).strip("._")
        suffix = Path(name).suffix.lower()
        return f"{stem or 'attachment'}{suffix}"

    def validate(self, *, filename: str, file_bytes: bytes, maximum_size_bytes: int) -> None:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_LEAVE_ATTACHMENT_EXTENSIONS:
            raise ValueError(
                "Leave attachment must be PDF, DOCX, PNG, JPG, or JPEG."
            )
        if not file_bytes:
            raise ValueError("The leave attachment is empty.")
        if len(file_bytes) > maximum_size_bytes:
            raise ValueError("The leave attachment exceeds the maximum size.")

    def write(self, *, company_id: int, filename: str, file_bytes: bytes) -> str:
        relative = Path(f"company_{company_id}") / f"{uuid4().hex}_{self._safe_filename(filename)}"
        destination = (self.root_dir / relative).resolve()
        if self.root_dir not in destination.parents:
            raise ValueError("Invalid leave attachment path.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file_bytes)
        return relative.as_posix()

    def read(self, storage_path: str) -> bytes:
        path = (self.root_dir / storage_path).resolve()
        if self.root_dir not in path.parents or not path.is_file():
            raise FileNotFoundError("Leave attachment is unavailable.")
        return path.read_bytes()

    def delete(self, storage_path: str | None) -> None:
        if not storage_path:
            return
        path = (self.root_dir / storage_path).resolve()
        if self.root_dir in path.parents and path.is_file():
            path.unlink()
