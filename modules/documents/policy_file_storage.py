"""Private local storage for uploaded company policy files."""

from dataclasses import dataclass
from pathlib import Path
import os
import re
from uuid import uuid4

from config.settings import get_settings


@dataclass(slots=True)
class StoredPolicyFile:
    """Relative storage details saved in the database."""

    stored_filename: str
    relative_path: str


class PolicyFileStorage:
    """Store and retrieve policy files below one protected root directory."""

    def __init__(
        self,
        root_directory: str | Path | None = None,
    ) -> None:
        settings = get_settings()

        self.root = Path(
            root_directory
            or settings.policy_upload_dir
        ).resolve()

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _safe_storage_name(original_filename: str) -> str:
        """Remove unsafe characters while retaining a useful extension."""

        original = Path(original_filename).name
        stem = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            Path(original).stem,
        ).strip("._") or "policy"
        extension = Path(original).suffix.lower()

        return f"{uuid4().hex}_{stem[:80]}{extension}"

    def _resolve_relative(
        self,
        relative_path: str,
    ) -> Path:
        """Resolve and verify that a path remains below the storage root."""

        candidate = (
            self.root / relative_path
        ).resolve()

        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise ValueError(
                "Invalid policy storage path."
            ) from error

        return candidate

    def save(
        self,
        *,
        company_id: int,
        original_filename: str,
        file_bytes: bytes,
    ) -> StoredPolicyFile:
        """Atomically save one file inside the company folder."""

        company_folder = (
            self.root / f"company_{company_id}"
        )
        company_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_filename = self._safe_storage_name(
            original_filename
        )
        destination = company_folder / stored_filename
        temporary = destination.with_suffix(
            destination.suffix + ".tmp"
        )

        temporary.write_bytes(file_bytes)
        os.replace(temporary, destination)

        relative_path = destination.relative_to(
            self.root
        ).as_posix()

        return StoredPolicyFile(
            stored_filename=stored_filename,
            relative_path=relative_path,
        )

    def read(self, relative_path: str) -> bytes:
        """Read one authorized file after service-level tenant checks."""

        path = self._resolve_relative(relative_path)

        if not path.is_file():
            raise FileNotFoundError(
                "The stored policy file was not found."
            )

        return path.read_bytes()

    def delete(self, relative_path: str) -> None:
        """Delete a saved file during a failed database transaction."""

        path = self._resolve_relative(relative_path)

        if path.exists():
            path.unlink()
