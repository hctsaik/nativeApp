from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a logger that writes to both stdout and a file in CIM_LOG_DIR.

    Usage:
        from log_utils import get_logger
        log = get_logger(__name__)
        log.info("Processing started")
        log.warning("No result file yet")
        log.error("Failed: %s", exc)

    The log file is placed at:
        {CIM_LOG_DIR}/{name}.log   (when CIM_LOG_DIR env var is set)
        ./logs/{name}.log          (fallback)
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured in this process

    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # Stream handler (stdout — captured by Streamlit / engine logs)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # File handler
    log_dir = Path(os.environ.get("CIM_LOG_DIR", "./logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.propagate = False
    return logger
