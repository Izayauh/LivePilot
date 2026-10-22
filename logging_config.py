"""
Centralized Logging Configuration for Jarvis

This module provides a unified logging setup for the entire Jarvis system.
All modules should use this configuration to ensure consistent logging behavior.

Usage:
    from logging_config import setup_logging
    setup_logging()

    # Then in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Your message here")
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_file="logs/jarvis.log", console_level=logging.INFO, file_level=logging.DEBUG):
    """
    Configure logging for the entire Jarvis system.

    Args:
        log_file: Path to the log file (default: logs/jarvis.log)
        console_level: Log level for console output (default: INFO)
        file_level: Log level for file output (default: DEBUG for full transparency)

    Returns:
        logging.Logger: The root logger instance
    """
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create root logger
    root_logger = logging.getLogger("jarvis")
    root_logger.setLevel(logging.DEBUG)  # Capture everything at root level

    # Remove any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Define standard format with timestamp, module name, level, and message
    log_format = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File Handler: DEBUG level, rotates at 10MB, keeps 5 backups
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # Console Handler: INFO level (clean UI)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # Log initialization message
    root_logger.info("=" * 80)
    root_logger.info("Jarvis Logging System Initialized")
    root_logger.info(f"Log file: {os.path.abspath(log_file)}")
    root_logger.info(f"Console level: {logging.getLevelName(console_level)}")
    root_logger.info(f"File level: {logging.getLevelName(file_level)}")
    root_logger.info("=" * 80)

    return root_logger


def get_logger(name):
    """
    Get a logger instance for a specific module.

    Args:
        name: Module name (typically __name__)

    Returns:
        logging.Logger: Logger instance for the module
    """
    # Ensure the logger is under the jarvis hierarchy
    if not name.startswith("jarvis."):
        name = f"jarvis.{name}"
    return logging.getLogger(name)
