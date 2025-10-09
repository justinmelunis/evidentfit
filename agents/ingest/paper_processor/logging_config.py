import logging
import sys
from pathlib import Path
from logging import Logger
from evidentfit_shared.utils import PROJECT_ROOT
from logging.handlers import RotatingFileHandler

def setup_logging(level: str | None = None) -> Logger:
    log_dir = PROJECT_ROOT / "logs" / "paper_processor"
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / "paper_processor.log"

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, (level or "INFO").upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    fh = RotatingFileHandler(logfile, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
