"""Private local storage for form templates and employee submissions."""

from dataclasses import dataclass
from pathlib import Path
import os
import re
from uuid import uuid4

from config.settings import get_settings


@dataclass(slots=True)
class StoredCompanyFormFile:
    """Relative storage details saved in the database."""

    stored_filename: str
    relative_path: str


class CompanyFormFileStorage:
    """Store authorized company form files under one protected root."""

    def __init__(self, root_directory: str | Path | None = None) -> None:
        settings = get_settings()
        self.root = Path(
            root_directory or settings.company_form_upload_dir
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_name(original_filename: str, fallback: str) -> str:
        original = Path(original_filename).name
        stem = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            Path(original).stem,
        ).strip("._") or fallback
        extension = Path(original).suffix.lower()
        return f"{uuid4().hex}_{stem[:80]}{extension}"

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise ValueError("Invalid company-form storage path.") from error
        return candidate

    def save_template(
        self,
        *,
        company_id: int,
        original_filename: str,
        file_bytes: bytes,
    ) -> StoredCompanyFormFile:
        folder = self.root / f"company_{company_id}" / "templates"
        return self._save(
            folder=folder,
            original_filename=original_filename,
            file_bytes=file_bytes,
            fallback="company_form",
        )

    def save_submission(
        self,
        *,
        company_id: int,
        employee_id: int,
        original_filename: str,
        file_bytes: bytes,
    ) -> StoredCompanyFormFile:
        folder = (
            self.root
            / f"company_{company_id}"
            / "submissions"
            / f"employee_{employee_id}"
        )
        return self._save(
            folder=folder,
            original_filename=original_filename,
            file_bytes=file_bytes,
            fallback="completed_form",
        )

    def _save(
        self,
        *,
        folder: Path,
        original_filename: str,
        file_bytes: bytes,
        fallback: str,
    ) -> StoredCompanyFormFile:
        folder.mkdir(parents=True, exist_ok=True)
        stored_filename = self._safe_name(original_filename, fallback)
        destination = folder / stored_filename
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(file_bytes)
        os.replace(temporary, destination)
        return StoredCompanyFormFile(
            stored_filename=stored_filename,
            relative_path=destination.relative_to(self.root).as_posix(),
        )

    def read(self, relative_path: str) -> bytes:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise FileNotFoundError("The stored company-form file was not found.")
        return path.read_bytes()

    def delete(self, relative_path: str) -> None:
        path = self._resolve(relative_path)
        if path.exists():
            path.unlink()
