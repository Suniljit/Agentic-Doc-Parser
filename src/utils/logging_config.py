"""Shared loguru file-sink setup for all part scripts."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def setup_file_logging(name: str, log_dir: Path = Path("logs")) -> None:
    """Add a DEBUG-level file sink for this run.

    Filename: logs/YYYY-MM-DD_HH-mm-ss_<name>.log
    Stderr sink (already added by utils/llm.py or the part itself) is untouched.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{{time:YYYY-MM-DD_HH-mm-ss}}_{name}.log"
    logger.add(log_path, level="DEBUG", encoding="utf-8")
    logger.debug("File logging active: {}", log_dir / f"<timestamp>_{name}.log")
