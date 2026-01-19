"""
Utility functions for AHPRA scraper.
"""

import random
import time
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger

from config.settings import (
    MIN_DELAY,
    MAX_DELAY,
    UI_MIN_DELAY,
    UI_MAX_DELAY,
    SIDEBAR_FILTER_MIN_DELAY,
    SIDEBAR_FILTER_MAX_DELAY,
    LOGS_DIR,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_ROTATION,
    LOG_RETENTION,
)


def setup_logging(log_name: str = "ahpra_scraper") -> None:
    """
    Configure logging with loguru.

    Args:
        log_name: Name for the log file
    """
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=LOG_LEVEL,
        colorize=True,
    )

    # Add file handler with rotation
    log_file = LOGS_DIR / f"{log_name}_{{time:YYYY-MM-DD}}.log"
    logger.add(
        str(log_file),
        format=LOG_FORMAT,
        level=LOG_LEVEL,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression="zip",
    )

    logger.info(f"Logging initialized. Log file: {log_file}")


def random_delay(min_delay: float = None, max_delay: float = None) -> float:
    """
    Sleep for a random duration between min and max delay.

    This is used for PRIMARY delays between server requests (30-40 seconds default).
    For quick UI interactions within the same page, use ui_delay() instead.

    Args:
        min_delay: Minimum delay in seconds (default from settings: 30s)
        max_delay: Maximum delay in seconds (default from settings: 40s)

    Returns:
        Actual delay duration
    """
    min_d = min_delay if min_delay is not None else MIN_DELAY
    max_d = max_delay if max_delay is not None else MAX_DELAY

    delay = random.uniform(min_d, max_d)
    time.sleep(delay)
    return delay


def ui_delay(min_delay: float = None, max_delay: float = None) -> float:
    """
    Sleep for a short duration for UI interactions (form filling, button clicks).

    This is for quick interactions within the same page that don't generate
    additional server requests. Use random_delay() for actual API calls.

    Args:
        min_delay: Minimum delay in seconds (default: 0.2s)
        max_delay: Maximum delay in seconds (default: 0.6s)

    Returns:
        Actual delay duration
    """
    min_d = min_delay if min_delay is not None else UI_MIN_DELAY
    max_d = max_delay if max_delay is not None else UI_MAX_DELAY

    delay = random.uniform(min_d, max_d)
    time.sleep(delay)
    return delay


def sidebar_filter_delay(min_delay: float = None, max_delay: float = None) -> float:
    """
    Sleep for a medium duration between sidebar filter changes.

    This is used in optimized discovery mode when applying sidebar filters.
    Longer than UI delays but shorter than full request delays to help
    avoid triggering CAPTCHA while still being faster than full page navigation.

    Args:
        min_delay: Minimum delay in seconds (default: 10s)
        max_delay: Maximum delay in seconds (default: 15s)

    Returns:
        Actual delay duration
    """
    min_d = min_delay if min_delay is not None else SIDEBAR_FILTER_MIN_DELAY
    max_d = max_delay if max_delay is not None else SIDEBAR_FILTER_MAX_DELAY

    delay = random.uniform(min_d, max_d)
    logger.debug(f"Sidebar filter delay: {delay:.1f}s")
    time.sleep(delay)
    return delay


def get_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        Timestamp string
    """
    return datetime.now().isoformat()


def get_date_string() -> str:
    """
    Get current date as string for filenames.

    Returns:
        Date string in YYYY-MM-DD format
    """
    return datetime.now().strftime("%Y-%m-%d")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string for use as a filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def estimate_remaining_time(processed: int, total: int, elapsed_seconds: float) -> str:
    """
    Estimate remaining time based on progress.

    Args:
        processed: Number of items processed
        total: Total number of items
        elapsed_seconds: Time elapsed so far

    Returns:
        Estimated remaining time string
    """
    if processed == 0:
        return "calculating..."

    rate = processed / elapsed_seconds
    remaining = total - processed
    remaining_seconds = remaining / rate

    return format_duration(remaining_seconds)


def chunks(lst: list, n: int):
    """
    Yield successive n-sized chunks from a list.

    Args:
        lst: List to chunk
        n: Chunk size

    Yields:
        Chunks of the list
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def safe_get(data: dict, *keys, default=None):
    """
    Safely get nested dictionary values.

    Args:
        data: Dictionary to search
        *keys: Keys to traverse
        default: Default value if not found

    Returns:
        Value or default
    """
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data
