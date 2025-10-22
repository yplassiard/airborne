"""Advanced logging system for plugins and core components.

This module provides a flexible logging system with YAML configuration,
per-plugin loggers, platform-aware log locations, and startup-based rotation.

Platform-specific log locations:
    - macOS: ~/Library/Logs/AirBorne/airborne.log
    - Linux: ~/.airborne/logs/airborne.log
    - Windows: %AppData%/AirBorne/Logs/airborne.log

Each game start rotates logs, keeping the last 5 launches.

Typical usage example:
    from airborne.core.logging_system import get_logger

    class MyPlugin:
        def __init__(self):
            self._log = get_logger("my_plugin")

        def process(self):
            self._log.info("Processing started")
            self._log.debug("Debug details: %s", data)
"""

import logging
import logging.handlers
import os
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Global configuration
_logging_config: dict[str, Any] = {}
_loggers_cache: dict[str, logging.Logger] = {}
_initialized = False


class LoggingError(Exception):
    """Raised when logging system operations fail."""


def get_platform_log_dir() -> Path:
    """Get platform-specific log directory.

    Returns:
        Path to the platform-appropriate log directory:
        - macOS: ~/Library/Logs/AirBorne
        - Linux: ~/.airborne/logs
        - Windows: %AppData%/AirBorne/Logs

    Examples:
        >>> log_dir = get_platform_log_dir()
        >>> print(log_dir)
        PosixPath('/Users/username/Library/Logs/AirBorne')
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Logs" / "AirBorne"
    elif system == "Windows":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "AirBorne" / "Logs"
    else:  # Linux and other Unix-like systems
        return Path.home() / ".airborne" / "logs"


def rotate_logs(log_dir: Path, log_filename: str = "airborne.log", keep_count: int = 5) -> None:
    """Rotate logs on startup, keeping the last N launches.

    Renames current log to airborne.log.1, shifts older logs, and deletes
    logs beyond keep_count.

    Args:
        log_dir: Directory containing log files.
        log_filename: Base name of the log file (default: "airborne.log").
        keep_count: Number of old logs to keep (default: 5).

    Examples:
        >>> rotate_logs(Path("logs"), "airborne.log", 5)
        # airborne.log -> airborne.log.1
        # airborne.log.1 -> airborne.log.2
        # ...
        # airborne.log.5 -> deleted
    """
    log_file = log_dir / log_filename

    # If current log doesn't exist, nothing to rotate
    if not log_file.exists():
        return

    # Delete oldest log if it exists (beyond keep_count)
    oldest_log = log_dir / f"{log_filename}.{keep_count}"
    if oldest_log.exists():
        oldest_log.unlink()

    # Shift existing numbered logs
    for i in range(keep_count - 1, 0, -1):
        old_log = log_dir / f"{log_filename}.{i}"
        new_log = log_dir / f"{log_filename}.{i + 1}"
        if old_log.exists():
            old_log.rename(new_log)

    # Rename current log to .1
    log_file.rename(log_dir / f"{log_filename}.1")


def initialize_logging(config_path: str | Path | None = None, use_platform_dir: bool = True) -> None:
    """Initialize the logging system from YAML configuration.

    This should be called once at application startup before any logging occurs.
    Automatically rotates logs on startup, keeping the last 5 launches.

    Args:
        config_path: Path to logging configuration YAML file.
            If None, uses default configuration.
        use_platform_dir: If True, use platform-specific log directory.
            If False, use directory from config (for development/testing).

    Raises:
        LoggingError: If initialization fails.

    Examples:
        >>> initialize_logging("config/logging.yaml")
        >>> log = get_logger("my_component")
        >>> log.info("Logging initialized")
    """
    global _logging_config, _initialized

    if config_path:
        try:
            config_path = Path(config_path)
            if not config_path.exists():
                raise LoggingError(f"Logging config file not found: {config_path}")

            with config_path.open("r", encoding="utf-8") as f:
                _logging_config = yaml.safe_load(f) or {}

        except Exception as e:
            raise LoggingError(f"Failed to load logging config: {e}") from e
    else:
        _logging_config = _get_default_config()

    # Override log directory with platform-specific location if requested
    if use_platform_dir:
        _logging_config["log_dir"] = str(get_platform_log_dir())

    # Create log directories
    _setup_directories()

    # Rotate logs from previous sessions
    log_dir = Path(_logging_config.get("log_dir", "logs"))
    log_filename = _logging_config.get("combined_log", {}).get("filename", "airborne.log")
    keep_count = _logging_config.get("combined_log", {}).get("backup_count", 5)
    rotate_logs(log_dir, log_filename, keep_count)

    # Configure root logger
    _configure_root_logger()

    _initialized = True


def _get_default_config() -> dict[str, Any]:
    """Get default logging configuration.

    Returns:
        Default logging configuration dictionary.
    """
    return {
        "version": 1,
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "date_format": "%Y-%m-%d %H:%M:%S.%f",
        "log_dir": "logs",
        "combined_log": {
            "enabled": True,
            "filename": "airborne.log",
            "max_bytes": 10485760,  # 10 MB
            "backup_count": 5,
        },
        "console": {
            "enabled": True,
            "level": "INFO",
        },
        "plugins": {},
    }


def _setup_directories() -> None:
    """Create log directories if they don't exist."""
    log_dir = Path(_logging_config.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)


def _configure_root_logger() -> None:
    """Configure the root logger with handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, filter in handlers

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if _logging_config.get("console", {}).get("enabled", True):
        console_handler = logging.StreamHandler()
        console_level = _logging_config.get("console", {}).get("level", "INFO")
        console_handler.setLevel(getattr(logging, console_level))
        console_handler.setFormatter(_get_formatter())
        root_logger.addHandler(console_handler)

    # Combined log file handler (simple FileHandler, rotation done on startup)
    if _logging_config.get("combined_log", {}).get("enabled", True):
        combined_config = _logging_config["combined_log"]
        log_dir = Path(_logging_config.get("log_dir", "logs"))
        log_file = log_dir / combined_config.get("filename", "airborne.log")

        # Use simple FileHandler since we rotate on startup, not by size
        file_handler = logging.FileHandler(
            log_file,
            mode='w',  # Overwrite - we already rotated old log
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_get_formatter())
        root_logger.addHandler(file_handler)


class MillisecondFormatter(logging.Formatter):
    """Custom formatter that shows milliseconds with dot separator."""

    def formatTime(self, record, datefmt=None):
        """Format time with milliseconds using dot separator."""
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = time.strftime("%Y-%m-%d %H:%M:%S", ct)
        # Add milliseconds with dot separator
        s = f"{s}.{int(record.msecs):03d}"
        return s


def _get_formatter() -> logging.Formatter:
    """Get the configured log formatter.

    Returns:
        Configured logging.Formatter instance.
    """
    fmt = _logging_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    datefmt = _logging_config.get("date_format", "%Y-%m-%d %H:%M:%S")

    # Create formatter with millisecond precision
    formatter = MillisecondFormatter(fmt, datefmt)
    return formatter


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a plugin or component.

    Loggers are cached and reused. Each logger can have its own configuration
    specified in the logging config YAML under the 'plugins' section.

    Args:
        name: Logger name (typically plugin/component name).

    Returns:
        Configured logger instance.

    Examples:
        >>> log = get_logger("engine_plugin")
        >>> log.info("Engine started")
        >>> log.debug("RPM: %d", rpm)
        >>> log.error("Engine failure: %s", error)

    Note:
        Use lazy formatting (%) instead of f-strings for better performance.
    """
    if not _initialized:
        # Auto-initialize with defaults if not done explicitly
        initialize_logging()

    if name in _loggers_cache:
        return _loggers_cache[name]

    logger = logging.getLogger(name)

    # Check for plugin-specific configuration
    plugin_config = _logging_config.get("plugins", {}).get(name, {})

    if plugin_config.get("enabled", True):
        # Set plugin-specific level if configured
        if "level" in plugin_config:
            level = plugin_config["level"]
            logger.setLevel(getattr(logging, level))

        # Add dedicated file handler if configured
        if plugin_config.get("dedicated_file", False):
            log_dir = Path(_logging_config.get("log_dir", "logs"))
            log_file = log_dir / f"{name}.log"

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=plugin_config.get("max_bytes", 10485760),
                backupCount=plugin_config.get("backup_count", 5),
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(_get_formatter())
            logger.addHandler(file_handler)
    else:
        # Disable logger if explicitly disabled
        logger.disabled = True

    _loggers_cache[name] = logger
    return logger


def shutdown_logging() -> None:
    """Shutdown the logging system gracefully.

    Flushes all handlers and closes log files. Should be called at
    application shutdown.

    Examples:
        >>> shutdown_logging()
    """
    logging.shutdown()
    _loggers_cache.clear()


class LoggerMixin:
    """Mixin class to easily add logging to any class.

    Classes can inherit from this mixin to automatically get a logger
    instance available as self._log.

    Examples:
        >>> class MyPlugin(LoggerMixin):
        ...     def __init__(self):
        ...         super().__init__()
        ...         self.attach_logger("my_plugin")
        ...
        ...     def process(self):
        ...         self._log.info("Processing")
    """

    def attach_logger(self, name: str) -> None:
        """Attach a logger to this instance.

        Args:
            name: Logger name to use.

        Examples:
            >>> self.attach_logger("my_component")
            >>> self._log.info("Component initialized")
        """
        self._log = get_logger(name)

    def log_debug(self, message: str, *args: Any) -> None:
        """Log a debug message.

        Args:
            message: Message format string.
            *args: Arguments for formatting.
        """
        if hasattr(self, "_log"):
            self._log.debug(message, *args)

    def log_info(self, message: str, *args: Any) -> None:
        """Log an info message.

        Args:
            message: Message format string.
            *args: Arguments for formatting.
        """
        if hasattr(self, "_log"):
            self._log.info(message, *args)

    def log_warning(self, message: str, *args: Any) -> None:
        """Log a warning message.

        Args:
            message: Message format string.
            *args: Arguments for formatting.
        """
        if hasattr(self, "_log"):
            self._log.warning(message, *args)

    def log_error(self, message: str, *args: Any, exc_info: bool = False) -> None:
        """Log an error message.

        Args:
            message: Message format string.
            *args: Arguments for formatting.
            exc_info: Include exception traceback if True.
        """
        if hasattr(self, "_log"):
            self._log.error(message, *args, exc_info=exc_info)

    def log_critical(self, message: str, *args: Any, exc_info: bool = False) -> None:
        """Log a critical message.

        Args:
            message: Message format string.
            *args: Arguments for formatting.
            exc_info: Include exception traceback if True.
        """
        if hasattr(self, "_log"):
            self._log.critical(message, *args, exc_info=exc_info)
