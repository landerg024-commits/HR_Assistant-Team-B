import logging
from config.logging_config import configure_logging
from config.settings import get_settings


def get_logger(name: str) -> logging.Logger:
    configure_logging(get_settings().log_level)
    return logging.getLogger(name)
