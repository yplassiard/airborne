#!/usr/bin/env python3
"""TTS Cache Service Helper - Standalone executable entry point.

This module provides a standalone entry point for the TTS Cache Service
that can be bundled as a separate PyInstaller executable. This allows
the main application to spawn TTS as a true subprocess even when bundled.

Usage (development):
    python -m airborne.tts_cache_service.tts_helper [--port PORT]

Usage (bundled):
    ./tts_helper [--port PORT]
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

# Minimal imports to reduce executable size
# These are needed for the service to work
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from airborne.tts_cache_service.service import TTSCacheService, load_config, setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for TTS helper executable."""
    parser = argparse.ArgumentParser(description="TTS Cache Service Helper")
    parser.add_argument(
        "--port",
        type=int,
        default=51127,
        help="WebSocket port (default: 51127)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="WebSocket host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration YAML file",
    )
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Override host/port from command line
    config.setdefault("server", {})["host"] = args.host
    config.setdefault("server", {})["port"] = args.port

    # Setup logging
    setup_logging(config)

    logger.info("TTS Helper starting on %s:%d...", args.host, args.port)

    # Create service
    service = TTSCacheService(config)

    # Setup signal handlers
    def signal_handler(sig: int, frame: Any) -> None:
        logger.info("Signal %d received, shutting down...", sig)
        service._shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run service
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
