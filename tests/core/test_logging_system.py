"""Tests for the logging system."""

import logging
from pathlib import Path

import pytest

from airborne.core.logging_system import (
    LoggerMixin,
    LoggingError,
    get_logger,
    initialize_logging,
    shutdown_logging,
)


class TestLoggingInitialization:
    """Test suite for logging initialization."""

    def test_initialize_with_defaults(self) -> None:
        """Test initializing with default configuration."""
        initialize_logging()
        log = get_logger("test")
        assert log is not None
        assert isinstance(log, logging.Logger)
        shutdown_logging()

    def test_initialize_with_missing_config(self) -> None:
        """Test that missing config file raises error."""
        with pytest.raises(LoggingError, match="not found"):
            initialize_logging("nonexistent.yaml")

    def test_initialize_creates_log_directory(self, tmp_path: Path) -> None:
        """Test that log directory is created."""
        config_content = f"""
version: 1
level: INFO
log_dir: "{tmp_path / "test_logs"}"
console:
  enabled: false
combined_log:
  enabled: false
"""
        config_file = tmp_path / "logging_test.yaml"
        config_file.write_text(config_content)

        initialize_logging(config_file)

        log_dir = tmp_path / "test_logs"
        assert log_dir.exists()
        shutdown_logging()


class TestGetLogger:
    """Test suite for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a logger instance."""
        initialize_logging()
        log = get_logger("test_component")
        assert isinstance(log, logging.Logger)
        assert log.name == "test_component"
        shutdown_logging()

    def test_get_logger_caches_instances(self) -> None:
        """Test that loggers are cached and reused."""
        initialize_logging()
        log1 = get_logger("cached_test")
        log2 = get_logger("cached_test")
        assert log1 is log2
        shutdown_logging()

    def test_get_logger_auto_initializes(self) -> None:
        """Test that get_logger auto-initializes if needed."""
        shutdown_logging()
        log = get_logger("auto_init_test")
        assert isinstance(log, logging.Logger)
        shutdown_logging()


class TestLoggerMixin:
    """Test suite for LoggerMixin."""

    def test_mixin_attach_logger(self) -> None:
        """Test attaching logger via mixin."""
        initialize_logging()

        class TestClass(LoggerMixin):
            def __init__(self) -> None:
                super().__init__()
                self.attach_logger("test_mixin")

        obj = TestClass()
        assert hasattr(obj, "_log")
        assert isinstance(obj._log, logging.Logger)
        shutdown_logging()

    def test_mixin_log_methods(self) -> None:
        """Test mixin logging methods."""
        initialize_logging()

        class TestClass(LoggerMixin):
            def __init__(self) -> None:
                super().__init__()
                self.attach_logger("test_mixin_methods")

        obj = TestClass()

        # These should not raise
        obj.log_debug("Debug message: %s", "test")
        obj.log_info("Info message")
        obj.log_warning("Warning message")
        obj.log_error("Error message")
        obj.log_critical("Critical message")

        shutdown_logging()

    def test_mixin_without_logger_attached(self) -> None:
        """Test that mixin methods don't crash without logger."""

        class TestClass(LoggerMixin):
            pass

        obj = TestClass()

        # Should not raise even without attached logger
        obj.log_info("This should not crash")


class TestLoggingConfiguration:
    """Test suite for logging configuration."""

    def test_plugin_specific_level(self, tmp_path: Path) -> None:
        """Test plugin-specific log level configuration."""
        config_content = """
version: 1
level: INFO
console:
  enabled: false
combined_log:
  enabled: false
plugins:
  test_plugin:
    enabled: true
    level: DEBUG
"""
        config_file = tmp_path / "plugin_level_test.yaml"
        config_file.write_text(config_content)

        initialize_logging(config_file)
        log = get_logger("test_plugin")

        assert log.level == logging.DEBUG
        shutdown_logging()

    def test_disabled_plugin_logger(self, tmp_path: Path) -> None:
        """Test disabling a plugin's logger."""
        config_content = """
version: 1
level: INFO
console:
  enabled: false
combined_log:
  enabled: false
plugins:
  disabled_plugin:
    enabled: false
"""
        config_file = tmp_path / "disabled_test.yaml"
        config_file.write_text(config_content)

        initialize_logging(config_file)
        log = get_logger("disabled_plugin")

        assert log.disabled is True
        shutdown_logging()


class TestLoggingPerformance:
    """Test suite for logging performance characteristics."""

    def test_lazy_formatting(self) -> None:
        """Test that lazy formatting works correctly."""
        initialize_logging()
        log = get_logger("performance_test")

        # This should use lazy formatting (%) not f-strings
        log.debug("Test message with args: %s, %d", "string", 42)

        # Should work without crashing
        shutdown_logging()


class TestLoggingShutdown:
    """Test suite for logging shutdown."""

    def test_shutdown_clears_cache(self) -> None:
        """Test that shutdown clears logger cache."""
        initialize_logging()
        get_logger("test_shutdown")

        shutdown_logging()

        # After shutdown, getting a logger should work (auto-reinitialize)
        log = get_logger("test_after_shutdown")
        assert isinstance(log, logging.Logger)
        shutdown_logging()
