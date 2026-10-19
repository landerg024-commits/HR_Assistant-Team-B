"""Initialize shared Streamlit session-state values."""

from authentication.session_manager import AuthSessionManager
from config.settings import get_settings
from ui.navigation_state import initialize_navigation_state
from ui.theme.theme_state import initialize_theme_state


def initialize_session_state() -> None:
    """Restore theme, navigation, and authentication state."""

    settings = get_settings()

    initialize_theme_state(settings.default_theme)
    initialize_navigation_state()
    AuthSessionManager.initialize()
