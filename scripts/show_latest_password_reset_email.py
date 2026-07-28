"""Display the newest local password-reset email during development.

Run:

    python scripts/show_latest_password_reset_email.py

This script reads the private local outbox configured through
PASSWORD_RESET_OUTBOX_DIR. Do not expose this folder in production.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from config.settings import get_settings


def main() -> None:
    """Print the latest locally generated `.eml` reset message."""

    settings = get_settings()
    outbox = Path(
        settings.password_reset_outbox_dir
    )

    messages = sorted(
        outbox.glob("password_reset_*.eml"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not messages:
        print("No local password-reset email was found.")
        return

    latest = messages[0]

    print(f"Latest reset email: {latest.resolve()}")
    print("-" * 72)
    print(
        latest.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )


if __name__ == "__main__":
    main()
