"""Company-logo upload, storage, tenant isolation, and UI tests."""

from io import BytesIO
from pathlib import Path

from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from config.settings import Settings
from database.base import Base
from database.schema_upgrade import upgrade_existing_schema
from modules.company_branding.company_logo_storage import CompanyLogoStorage
from scripts.create_initial_data import seed_initial_data
from services.organization_service import OrganizationService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _png_bytes(
    size: tuple[int, int] = (640, 200),
) -> bytes:
    buffer = BytesIO()
    Image.new(
        "RGBA",
        size,
        (30, 120, 210, 180),
    ).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg_bytes(
    size: tuple[int, int] = (800, 300),
) -> bytes:
    buffer = BytesIO()
    Image.new(
        "RGB",
        size,
        (235, 235, 235),
    ).save(buffer, format="JPEG")
    return buffer.getvalue()


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        initial_company_code="LOGO",
        initial_company_name="Logo Company",
        initial_admin_username="admin",
        initial_admin_email="admin@logo.example",
        initial_admin_password=SecretStr("Temporary123!"),
        initial_admin_employee_number="ADMIN-001",
        initial_admin_first_name="Logo",
        initial_admin_last_name="Admin",
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_company_model_contains_nullable_logo_reference() -> None:
    source = (
        PROJECT_ROOT / "models/company.py"
    ).read_text(encoding="utf-8")

    assert "logo_filename" in source
    assert "String(255)" in source
    assert "nullable=True" in source


def test_runtime_upgrade_adds_logo_column_to_older_database() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE companies ("
            "id INTEGER PRIMARY KEY, "
            "code VARCHAR(50), "
            "name VARCHAR(200), "
            "theme_primary_color VARCHAR(7), "
            "is_active BOOLEAN)"
        )

    upgrade_existing_schema(engine)
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("companies")
    }

    assert "logo_filename" in columns


def test_storage_normalizes_jpeg_to_company_scoped_png(tmp_path: Path) -> None:
    storage = CompanyLogoStorage(tmp_path, max_mb=5)
    filename = storage.save(
        company_id=7,
        file_name="brand.jpg",
        content=_jpeg_bytes(),
        content_type="image/jpeg",
    )

    assert filename == "company_logo.png"
    assert (tmp_path / "7" / filename).is_file()
    assert not (tmp_path / "8" / filename).exists()

    stored = storage.read(
        company_id=7,
        filename=filename,
    )
    assert stored is not None

    with Image.open(BytesIO(stored)) as image:
        assert image.format == "PNG"
        assert image.width <= 1600
        assert image.height <= 800
        assert image.width / image.height == 800 / 300


def test_storage_rejects_invalid_or_oversized_content(tmp_path: Path) -> None:
    storage = CompanyLogoStorage(tmp_path, max_mb=1)

    try:
        storage.save(
            company_id=1,
            file_name="not-image.png",
            content=b"not an image",
            content_type="image/png",
        )
    except ValueError as error:
        assert "valid image" in str(error)
    else:
        raise AssertionError("Invalid image should be rejected")

    try:
        storage.save(
            company_id=1,
            file_name="large.png",
            content=b"x" * (1024 * 1024 + 1),
            content_type="image/png",
        )
    except ValueError as error:
        assert "file-size limit" in str(error)
    else:
        raise AssertionError("Oversized image should be rejected")


def test_service_updates_and_removes_logo_reference(tmp_path: Path) -> None:
    _, factory = _factory()

    with factory() as session:
        seed = seed_initial_data(session, _settings())
        company_id = seed["company"].id
        storage = CompanyLogoStorage(tmp_path, max_mb=5)
        service = OrganizationService(session, logo_storage=storage)

        updated = service.update_company_logo(
            company_id=company_id,
            file_name="logo.png",
            content=_png_bytes(),
            content_type="image/png",
        )

        assert updated.logo_filename == "company_logo.png"
        assert service.get_company_logo_bytes(company_id)

        removed = service.remove_company_logo(company_id)
        assert removed.logo_filename is None
        assert service.get_company_logo_bytes(company_id) is None


def test_admin_company_profile_has_logo_management() -> None:
    source = (
        PROJECT_ROOT / "ui/pages/admin/company_page.py"
    ).read_text(encoding="utf-8")

    assert 'st.subheader("Company Logo")' in source
    assert '"Save Company Logo"' in source
    assert '"Remove Company Logo"' in source
    assert "company_logo_upload_max_mb" in source
    assert "prepare_responsive_image" in source


def test_admin_and_employee_sidebars_render_company_logo() -> None:
    for relative in (
        "ui/components/admin_sidebar.py",
        "ui/components/sidebar.py",
    ):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "render_company_sidebar_logo(current_user)" in source


def test_sidebar_logo_css_preserves_aspect_ratio_and_centering() -> None:
    source = (
        PROJECT_ROOT / "ui/theme/theme_loader.py"
    ).read_text(encoding="utf-8")
    block = source.split("COMPANY LOGO — v8.8.7", 1)[1]

    assert ".hr-sidebar-logo-shell" in block
    assert "align-items: center" in block
    assert "justify-content: center" in block
    assert "object-fit: contain !important" in block
    assert "max-height: 128px !important" in block
    assert "height: 132px" in block
    assert "padding: 0;" in block
    assert "width: 100% !important" in block
    assert "height: 100% !important" in block


def test_logo_upload_directory_is_excluded_from_runtime_package_data() -> None:
    settings_source = (
        PROJECT_ROOT / "config/settings.py"
    ).read_text(encoding="utf-8")
    requirements = (
        PROJECT_ROOT / "requirements.txt"
    ).read_text(encoding="utf-8")

    assert "company_logo_upload_dir" in settings_source
    assert "Pillow" in requirements
