"""
JARVIS Logging Configuration

Provides structured, colorful logging with file rotation and console output.
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(config) -> None:
    """
    Configure logging based on configuration.
    
    Args:
        config: Configuration object
    """
    # Remove default handler
    logger.remove()
    
    log_level = config.get("logging.level", "INFO")
    log_format = config.get(
        "logging.format",
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    
    # Console handler with colors
    logger.add(
        sys.stderr,
        format=log_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    
    # File handler with rotation
    log_file = config.get("logging.file", "data/logs/jarvis.log")
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} - {message}",
        level=log_level,
        rotation=config.get("logging.rotation", "10 MB"),
        retention=config.get("logging.retention", "7 days"),
        compression="zip",
        backtrace=True,
        diagnose=True,
    )
    
    logger.info(f"Logging initialized at {log_level} level")
    logger.debug(f"Log file: {log_path}")


class LogMixin:
    """Mixin class to add logging capability to any class."""
    
    @property
    def log(self):
        """Get logger instance for this class."""
        return logger.bind(name=self.__class__.__name__)
