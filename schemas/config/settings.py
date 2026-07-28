"""Central application configuration.

Purpose:
- Load values from the local `.env` file.
- Provide one consistent Settings object to the entire project.
- Keep database, company, admin, UI, and logging configuration
  outside the business logic.

Debugging note:
If a configuration value looks incorrect, check `.env` first.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings.

    Each class field can be overridden by a matching environment variable.
    Example:
        database_url -> DATABASE_URL
        initial_admin_email -> INITIAL_ADMIN_EMAIL
    """

    # Application identity and runtime behavior.
    app_name: str = "AI HR Assistant"
    app_version: str = "0.3.1"
    environment: str = "development"
    debug: bool = True

    # SQLAlchemy database connection string.
    # SQLite is used for local development.
    # PostgreSQL can be used later by changing only this value.
    database_url: str = "sqlite:///./data/hr_assistant.db"

    # Shared UI and branding defaults.
    default_theme: str = "light"
    company_name: str = "Sample Company"
    assistant_name: str = "AI HR Assistant"

    # Logging level used by the application logger.
    log_level: str = "INFO"

    # Initial company values used by the seed script.
    initial_company_code: str = "DEFAULT"
    initial_company_name: str = "Default Company"

    # Initial company administrator values.
    # SecretStr hides the password when the Settings object is printed.
    initial_admin_username: str = "admin"
    initial_admin_email: str = "admin@example.com"
    initial_admin_password: SecretStr = SecretStr("ChangeMe123!")
    initial_admin_employee_number: str = "ADMIN-001"
    initial_admin_first_name: str = "System"
    initial_admin_last_name: str = "Administrator"

    # Tell Pydantic Settings how to read the environment file.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached Settings instance.

    Caching prevents the application from repeatedly reading `.env`.
    During debugging, restart Streamlit after changing `.env`.
    """

    return Settings()
