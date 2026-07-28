from config.settings import get_settings


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.app_name
    assert settings.default_theme in {'light', 'dark'}
