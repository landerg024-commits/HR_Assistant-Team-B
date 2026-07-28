from pathlib import Path
import logging


def configure_logging(level: str = 'INFO') -> None:
    Path('logs').mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[logging.StreamHandler(), logging.FileHandler('logs/hr_assistant.log', encoding='utf-8')],
        force=True,
    )
