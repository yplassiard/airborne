"""Advanced logging system for plugins and core components.

This module provides a flexible logging system with YAML configuration,
per-plugin loggers, and optimization for high-volume logging.

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
import time
from pathlib import Path
from typing import Any

import yaml

# Global configuration
_logging_config: dict[str, Any] = {}
_loggers_cache: dict[str, logging.Logger] = {}
_initialized = False


class LoggingError(Exception):
    """Raised when logging system operations fail."""


def initialize_logging(config_path: str | Path | None = None) -> None:
    """Initialize the logging system from YAML configuration.

    This should be called once at application startup before any logging occurs.

    Args:
        config_path: Path to logging configuration YAML file.
            If None, uses default configuration.

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

    # Create log directories
    _setup_directories()

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

    # Combined log file handler
    if _logging_config.get("combined_log", {}).get("enabled", True):
        combined_config = _logging_config["combined_log"]
        log_dir = Path(_logging_config.get("log_dir", "logs"))
        log_file = log_dir / combined_config.get("filename", "airborne.log")

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=combined_config.get("max_bytes", 10485760),
            backupCount=combined_config.get("backup_count", 5),
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
