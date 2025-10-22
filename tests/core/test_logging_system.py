"""Unit tests for the logging system with platform-aware paths and rotation."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from airborne.core.logging_system import (
    LoggingError,
    get_logger,
    get_platform_log_dir,
    initialize_logging,
    rotate_logs,
    shutdown_logging,
)


class TestPlatformLogDir:
    """Tests for get_platform_log_dir function."""

    def test_macos_log_dir(self) -> None:
        """Test macOS log directory path."""
        with patch("platform.system", return_value="Darwin"):
            log_dir = get_platform_log_dir()
            assert "Library/Logs/AirBorne" in str(log_dir)
            assert log_dir == Path.home() / "Library" / "Logs" / "AirBorne"

    def test_linux_log_dir(self) -> None:
        """Test Linux log directory path."""
        with patch("platform.system", return_value="Linux"):
            log_dir = get_platform_log_dir()
            assert ".airborne/logs" in str(log_dir)
            assert log_dir == Path.home() / ".airborne" / "logs"

    def test_windows_log_dir(self) -> None:
        """Test Windows log directory path."""
        with patch("platform.system", return_value="Windows"):
            with patch.dict("os.environ", {"APPDATA": "C:/Users/Test/AppData/Roaming"}):
                log_dir = get_platform_log_dir()
                assert "AirBorne" in str(log_dir)
                assert "Logs" in str(log_dir)

    def test_unknown_platform_defaults_to_linux(self) -> None:
        """Test unknown platform defaults to Linux-style path."""
        with patch("platform.system", return_value="FreeBSD"):
            log_dir = get_platform_log_dir()
            assert ".airborne/logs" in str(log_dir)


class TestLogRotation:
    """Tests for log rotation functionality."""

    def test_rotate_logs_no_existing_log(self) -> None:
        """Test rotation when no log file exists - should do nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            # Should not raise error when log doesn't exist
            rotate_logs(log_dir, "test.log", 5)
            # No files should be created
            assert len(list(log_dir.glob("*"))) == 0

    def test_rotate_logs_single_file(self) -> None:
        """Test rotation with single existing log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_file = log_dir / "test.log"
            log_file.write_text("old log content")

            rotate_logs(log_dir, "test.log", 5)

            # Original file should be renamed to .1
            assert not log_file.exists()
            rotated = log_dir / "test.log.1"
            assert rotated.exists()
            assert rotated.read_text() == "old log content"

    def test_rotate_logs_multiple_files(self) -> None:
        """Test rotation with multiple existing log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Create current log and 3 old logs
            (log_dir / "test.log").write_text("current")
            (log_dir / "test.log.1").write_text("previous-1")
            (log_dir / "test.log.2").write_text("previous-2")
            (log_dir / "test.log.3").write_text("previous-3")

            rotate_logs(log_dir, "test.log", 5)

            # Check rotation happened correctly
            assert not (log_dir / "test.log").exists()
            assert (log_dir / "test.log.1").read_text() == "current"
            assert (log_dir / "test.log.2").read_text() == "previous-1"
            assert (log_dir / "test.log.3").read_text() == "previous-2"
            assert (log_dir / "test.log.4").read_text() == "previous-3"

    def test_rotate_logs_deletes_oldest(self) -> None:
        """Test that oldest log beyond keep_count is deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Create logs up to the limit
            (log_dir / "test.log").write_text("current")
            for i in range(1, 6):
                (log_dir / f"test.log.{i}").write_text(f"old-{i}")

            rotate_logs(log_dir, "test.log", keep_count=5)

            # The oldest (test.log.5) should be deleted
            assert not (log_dir / "test.log.6").exists()
            # But .1 through .5 should exist
            assert (log_dir / "test.log.1").exists()
            assert (log_dir / "test.log.5").exists()

    def test_rotate_logs_custom_keep_count(self) -> None:
        """Test rotation with custom keep_count parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Create current log and 2 old logs
            (log_dir / "test.log").write_text("current")
            (log_dir / "test.log.1").write_text("old-1")
            (log_dir / "test.log.2").write_text("old-2")

            # Rotate with keep_count=2
            rotate_logs(log_dir, "test.log", keep_count=2)

            # Should have .1 and .2, but .3 deleted if it existed
            assert (log_dir / "test.log.1").exists()
            assert (log_dir / "test.log.2").exists()
            assert not (log_dir / "test.log.3").exists()


class TestLoggingInitialization:
    """Tests for logging system initialization."""

    def test_initialize_with_platform_dir(self) -> None:
        """Test initialization uses platform-specific directory."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            initialize_logging(use_platform_dir=True)

            # Check logger works
            logger = get_logger("test")
            logger.info("Test message")

            # Log file should be created in platform dir
            log_file = Path(tmpdir) / "airborne.log"
            assert log_file.exists()

            shutdown_logging()

    def test_initialize_without_platform_dir(self) -> None:
        """Test initialization uses config directory when use_platform_dir=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize with custom log dir
            initialize_logging(use_platform_dir=False)

            # Should use 'logs' directory from config
            logger = get_logger("test")
            logger.info("Test message")

            shutdown_logging()

    def test_initialize_with_missing_config(self) -> None:
        """Test initialization fails gracefully with missing config file."""
        with pytest.raises(LoggingError, match="Logging config file not found"):
            initialize_logging(config_path="/nonexistent/config.yaml")

    def test_multiple_initialization_calls(self) -> None:
        """Test that multiple initialization calls don't cause errors."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            initialize_logging(use_platform_dir=True)
            # Second call should work fine (though typically avoided)
            initialize_logging(use_platform_dir=True)

            logger = get_logger("test")
            logger.info("Test message")

            shutdown_logging()


class TestLoggerFunctionality:
    """Tests for logger creation and usage."""

    def test_get_logger_creates_logger(self) -> None:
        """Test that get_logger returns a valid logger."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            initialize_logging(use_platform_dir=True)

            logger = get_logger("test_component")
            assert isinstance(logger, logging.Logger)
            assert logger.name == "test_component"

            shutdown_logging()

    def test_get_logger_caches_loggers(self) -> None:
        """Test that loggers are cached and reused."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            initialize_logging(use_platform_dir=True)

            logger1 = get_logger("test")
            logger2 = get_logger("test")

            # Should be the same object
            assert logger1 is logger2

            shutdown_logging()

    def test_logger_writes_to_file(self) -> None:
        """Test that logger messages are written to log file."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            initialize_logging(use_platform_dir=True)

            logger = get_logger("test")
            logger.info("Test log message")
            logger.debug("Debug message")
            logger.error("Error message")

            shutdown_logging()

            # Check log file contains messages
            log_file = Path(tmpdir) / "airborne.log"
            content = log_file.read_text()
            assert "Test log message" in content
            assert "Debug message" in content
            assert "Error message" in content

    def test_auto_initialize_on_first_logger(self) -> None:
        """Test that getting a logger auto-initializes if not done explicitly."""
        # This should not raise an error
        logger = get_logger("auto_init_test")
        assert isinstance(logger, logging.Logger)

        shutdown_logging()


class TestLogRotationIntegration:
    """Integration tests for log rotation on startup."""

    def test_startup_rotates_existing_log(self) -> None:
        """Test that initialization rotates existing log from previous session."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            # First session - create a log
            initialize_logging(use_platform_dir=True)
            logger = get_logger("test")
            logger.info("First session")
            shutdown_logging()

            # Verify log exists
            log_file = Path(tmpdir) / "airborne.log"
            assert log_file.exists()
            first_content = log_file.read_text()
            assert "First session" in first_content

            # Second session - should rotate previous log
            initialize_logging(use_platform_dir=True)
            logger = get_logger("test")
            logger.info("Second session")
            shutdown_logging()

            # Previous log should be rotated to .1
            rotated_log = Path(tmpdir) / "airborne.log.1"
            assert rotated_log.exists()
            assert "First session" in rotated_log.read_text()

            # Current log should have new content
            assert "Second session" in log_file.read_text()
            assert "First session" not in log_file.read_text()

    def test_multiple_sessions_keep_five_logs(self) -> None:
        """Test that only 5 most recent logs are kept across multiple sessions."""
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "airborne.core.logging_system.get_platform_log_dir", return_value=Path(tmpdir)
        ):
            # Run 7 sessions
            for i in range(7):
                initialize_logging(use_platform_dir=True)
                logger = get_logger("test")
                logger.info(f"Session {i}")
                shutdown_logging()

            # Should have current log + 5 rotated logs
            log_files = list(Path(tmpdir).glob("airborne.log*"))
            assert len(log_files) == 6  # airborne.log + .1 through .5

            # Oldest sessions should be gone (sessions 0 and 1)
            rotated_5 = Path(tmpdir) / "airborne.log.5"
            assert rotated_5.exists()
            content_5 = rotated_5.read_text()
            # .5 should have session 1 (0 was deleted, 1->2->3->4->5)
            assert "Session 1" in content_5
