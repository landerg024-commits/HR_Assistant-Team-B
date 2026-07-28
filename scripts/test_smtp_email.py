"""Send a real SMTP test email from the command line.

Usage:

    python scripts/test_smtp_email.py recipient@example.com
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from integrations.email.email_sender import (
    EmailDeliveryError,
)
from services.email_integration_service import (
    EmailIntegrationService,
)


def main() -> None:
    """Send one internet test email to the supplied recipient."""

    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/test_smtp_email.py "
            "recipient@example.com"
        )

    recipient = sys.argv[1]
    service = EmailIntegrationService()
    status = service.get_status()

    print(f"Mode: {status.mode}")
    print(f"Host: {status.host or 'Not configured'}")
    print(f"Port: {status.port or 'Not configured'}")
    print(f"Encryption: {status.encryption}")

    try:
        result = service.send_test_email(
            recipient
        )
    except EmailDeliveryError as error:
        raise SystemExit(str(error)) from error

    print(
        f"Test email sent successfully to "
        f"{result.recipient}."
    )


if __name__ == "__main__":
    main()
