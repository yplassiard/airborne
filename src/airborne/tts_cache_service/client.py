"""TTS Cache Service client for Airborne.

This module provides a client that manages the TTS Cache Service subprocess,
handles communication via WebSocket, and provides automatic restart with backoff.

Typical usage:
    from airborne.tts_cache_service.client import TTSServiceClient

    client = TTSServiceClient()
    await client.start()

    # Request TTS
    audio_bytes = await client.generate("altitude 3500")

    # Change settings
    await client.invalidate(rate=200, voice_name="Alex")

    await client.stop()
"""

import asyncio
import base64
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

try:
    import websockets
    from websockets.client import connect
except ImportError:
    websockets = None  # type: ignore

from airborne.tts_cache_service.protocol import (
    ContextRequest,
    ContextResponse,
    GenerateRequest,
    GenerateResponse,
    InvalidateRequest,
    InvalidateResponse,
    ListEnginesRequest,
    ListEnginesResponse,
    ListVoicesRequest,
    ListVoicesResponse,
    PingRequest,
    PingResponse,
    QueueRequest,
    QueueResponse,
    StatsRequest,
    StatsResponse,
    parse_response,
)

logger = logging.getLogger(__name__)


def _is_bundled() -> bool:
    """Check if running from a PyInstaller bundle."""
    return hasattr(sys, "_MEIPASS")


def _get_tts_helper_path() -> Path | None:
    """Get path to TTS helper executable in bundled app.

    Returns:
        Path to tts_helper executable, or None if not found.
    """
    if not _is_bundled():
        return None

    # In a macOS .app bundle:
    # sys._MEIPASS is Contents/Frameworks
    # Helper is at Contents/Helpers/tts_helper
    bundle_dir = Path(sys._MEIPASS)
    logger.debug("Looking for TTS helper, _MEIPASS=%s", bundle_dir)

    # Try macOS app bundle location
    if sys.platform == "darwin":
        # Contents/Frameworks -> Contents/Helpers
        helpers_dir = bundle_dir.parent / "Helpers"
        helper_path = helpers_dir / "tts_helper"
        logger.debug("Checking helper path: %s (exists=%s)", helper_path, helper_path.exists())
        if helper_path.exists():
            return helper_path

        # Alternative: derive from sys.executable
        # sys.executable is Contents/MacOS/airborne
        exe_path = Path(sys.executable)
        if exe_path.parent.name == "MacOS":
            contents_dir = exe_path.parent.parent
            helper_path = contents_dir / "Helpers" / "tts_helper"
            logger.debug("Checking helper path (from exe): %s (exists=%s)", helper_path, helper_path.exists())
            if helper_path.exists():
                return helper_path

    # Try Windows/Linux location (helpers alongside main executable)
    helper_path = bundle_dir / "helpers" / "tts_helper"
    if sys.platform == "win32":
        helper_path = helper_path.with_suffix(".exe")
    if helper_path.exists():
        return helper_path

    # Fallback: check alongside the bundle dir
    helper_path = bundle_dir.parent / "helpers" / "tts_helper"
    if sys.platform == "win32":
        helper_path = helper_path.with_suffix(".exe")
    if helper_path.exists():
        return helper_path

    logger.warning("TTS helper not found in bundle")
    return None


class TTSServiceClient:
    """Client for TTS Cache Service with subprocess management.

    Manages the TTS Cache Service subprocess lifecycle including:
    - Starting the service on demand
    - Health monitoring with periodic pings
    - Automatic restart with exponential backoff
    - Graceful shutdown

    Attributes:
        host: WebSocket server host.
        port: WebSocket server port.
        connected: True if currently connected to service.
    """

    # Backoff settings
    MIN_BACKOFF_S = 0.5
    MAX_BACKOFF_S = 5.0
    BACKOFF_MULTIPLIER = 2.0

    # Health check settings
    HEALTH_CHECK_INTERVAL_S = 30.0
    HEALTH_CHECK_TIMEOUT_S = 5.0

    # Connection settings
    CONNECT_TIMEOUT_S = 10.0
    REQUEST_TIMEOUT_S = 30.0

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 51127,
        config_path: Path | None = None,
        auto_start: bool = True,
    ) -> None:
        """Initialize client.

        Args:
            host: WebSocket server host.
            port: WebSocket server port.
            config_path: Path to service config file.
            auto_start: If True, start service automatically on first request.
        """
        if websockets is None:
            raise ImportError("websockets package required. Install with: uv add websockets")

        self.host = host
        self.port = port
        self.config_path = config_path
        self.auto_start = auto_start

        self._process: subprocess.Popen | None = None
        self._websocket: Any = None
        self._connected = False
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Backoff state
        self._current_backoff = self.MIN_BACKOFF_S
        self._last_restart_time = 0.0
        self._restart_count = 0

        # Pending requests
        self._pending: dict[str, asyncio.Future] = {}
        self._receive_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

        # Lock for thread safety
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Check if connected to service."""
        return self._connected and self._websocket is not None

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL."""
        return f"ws://{self.host}:{self.port}"

    async def start(self) -> bool:
        """Start the service and connect.

        Returns:
            True if service started and connected successfully.
        """
        if self._running:
            return self.connected

        self._running = True
        self._shutdown_event.clear()

        # Start subprocess
        if not await self._start_subprocess():
            return False

        # Connect to WebSocket with retries (service may take time to start)
        max_retries = 10
        retry_delay = 0.5
        for attempt in range(max_retries):
            if await self._connect():
                break
            if attempt < max_retries - 1:
                logger.debug("Connection attempt %d failed, retrying in %.1fs...", attempt + 1, retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 2.0)  # Cap at 2 seconds
        else:
            logger.error("Failed to connect after %d attempts", max_retries)
            return False

        # Start background tasks
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._monitor_task = asyncio.create_task(self._process_monitor_loop())

        logger.info("TTS Service client started")
        return True

    async def stop(self) -> None:
        """Stop the service and disconnect."""
        logger.info("Stopping TTS Service client")
        self._running = False
        self._shutdown_event.set()

        # Cancel background tasks
        for task in [self._receive_task, self._health_task, self._monitor_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Disconnect WebSocket
        await self._disconnect()

        # Stop subprocess
        await self._stop_subprocess()

        logger.info("TTS Service client stopped")

    async def _start_subprocess(self) -> bool:
        """Start the service subprocess (or helper executable if bundled)."""
        # Check if already running
        if self._process and self._process.poll() is None:
            logger.debug("Service process already running")
            return True

        try:
            # Check for bundled helper executable first
            helper_path = _get_tts_helper_path()
            if helper_path:
                cmd = [
                    str(helper_path),
                    "--host", self.host,
                    "--port", str(self.port),
                ]
                logger.info("Starting TTS helper executable: %s", " ".join(cmd))
            else:
                # Development mode: use python -m
                cmd = [
                    sys.executable,
                    "-m",
                    "airborne.tts_cache_service.service",
                ]
                if self.config_path:
                    cmd.extend(["--config", str(self.config_path)])
                logger.info("Starting TTS service subprocess: %s", " ".join(cmd))

            # For bundled helper executables, redirect stderr to a log file for debugging
            if helper_path:
                import tempfile
                log_dir = Path.home() / "Library" / "Logs" / "AirBorne"
                log_dir.mkdir(parents=True, exist_ok=True)
                helper_log = log_dir / "tts_helper.log"
                self._helper_log_file = open(helper_log, "w")
                logger.debug("TTS helper stderr -> %s", helper_log)
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=self._helper_log_file,
                )
            else:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

            # Wait for service to be ready (bundled helper needs more time)
            await asyncio.sleep(2.0 if helper_path else 1.0)

            if self._process.poll() is not None:
                if helper_path:
                    logger.error("TTS helper process exited immediately (exit code: %d)", self._process.returncode)
                else:
                    stdout, stderr = self._process.communicate()
                    logger.error(
                        "Service process exited immediately. stdout: %s, stderr: %s",
                        stdout.decode()[:500],
                        stderr.decode()[:500],
                    )
                return False

            logger.info("Service subprocess started (PID: %d)", self._process.pid)
            return True

        except Exception as e:
            logger.error("Failed to start service subprocess: %s", e)
            return False

    async def _stop_subprocess(self) -> None:
        """Stop the service subprocess."""
        if not self._process:
            return

        if self._process.poll() is None:
            logger.info("Terminating service subprocess (PID: %d)", self._process.pid)
            self._process.terminate()

            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                logger.warning("Service didn't terminate, killing")
                self._process.kill()
                self._process.wait()

        self._process = None

    async def _connect(self) -> bool:
        """Connect to WebSocket server."""
        if self._websocket:
            return True

        try:
            logger.info("Connecting to %s", self.ws_url)
            self._websocket = await asyncio.wait_for(
                connect(self.ws_url),
                timeout=self.CONNECT_TIMEOUT_S,
            )
            self._connected = True
            self._current_backoff = self.MIN_BACKOFF_S
            logger.info("Connected to TTS service")
            return True

        except TimeoutError:
            logger.error("Connection timeout")
            return False
        except Exception as e:
            logger.error("Connection failed: %s", e)
            return False

    async def _disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        self._connected = False
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

    async def _reconnect(self) -> bool:
        """Reconnect with backoff."""
        await self._disconnect()

        # Apply backoff
        logger.info("Reconnecting in %.1fs...", self._current_backoff)
        await asyncio.sleep(self._current_backoff)

        self._current_backoff = min(
            self._current_backoff * self.BACKOFF_MULTIPLIER,
            self.MAX_BACKOFF_S,
        )

        # Restart subprocess if needed
        if self._process is None or self._process.poll() is not None:
            if not await self._start_subprocess():
                return False

        return await self._connect()

    async def _receive_loop(self) -> None:
        """Background loop to receive responses."""
        while self._running and not self._shutdown_event.is_set():
            if not self._websocket:
                await asyncio.sleep(0.1)
                continue

            try:
                message = await self._websocket.recv()
                data = json.loads(message)
                req_id = data.get("id", "")

                if req_id in self._pending:
                    self._pending[req_id].set_result(data)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed")
                self._connected = False
                if self._running:
                    await self._reconnect()

            except Exception as e:
                logger.error("Receive error: %s", e)
                await asyncio.sleep(0.1)

    async def _health_check_loop(self) -> None:
        """Periodic health check."""
        while self._running and not self._shutdown_event.is_set():
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL_S)

            if not self._running:
                break

            try:
                response = await self.ping()
                if response:
                    logger.debug("Health check OK: uptime=%.1fs", response.uptime_s)
                else:
                    logger.warning("Health check failed, reconnecting")
                    await self._reconnect()

            except Exception as e:
                logger.error("Health check error: %s", e)

    async def _process_monitor_loop(self) -> None:
        """Monitor subprocess and restart if needed."""
        while self._running and not self._shutdown_event.is_set():
            await asyncio.sleep(5.0)

            if not self._running:
                break

            if self._process and self._process.poll() is not None:
                logger.warning("Service process died, restarting")
                self._restart_count += 1
                await self._reconnect()

    async def _send_request(self, request_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Send request and wait for response.

        Args:
            request_dict: Request dictionary.

        Returns:
            Response dictionary or None if failed.
        """
        # Auto-start if needed
        if self.auto_start and not self._running:
            await self.start()

        if not self._websocket:
            logger.error("Not connected")
            return None

        req_id = request_dict.get("id", str(uuid.uuid4()))
        request_dict["id"] = req_id

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            # Send request
            await self._websocket.send(json.dumps(request_dict))

            # Wait for response
            response = await asyncio.wait_for(future, timeout=self.REQUEST_TIMEOUT_S)
            return response

        except TimeoutError:
            logger.error("Request timeout for: %s", request_dict.get("cmd"))
            return None

        except Exception as e:
            logger.error("Request failed: %s", e)
            return None

        finally:
            self._pending.pop(req_id, None)

    async def generate(
        self,
        text: str,
        voice: str = "cockpit",
        rate: int = 180,
        voice_name: str | None = None,
        language: str | None = None,
        priority: int = 0,
    ) -> bytes | None:
        """Generate TTS audio with voice-specific settings.

        Args:
            text: Text to synthesize.
            voice: Logical voice name (e.g., "cockpit", "tower").
            rate: Speech rate in words per minute.
            voice_name: Platform-specific voice name (e.g., "Samantha").
            language: Language code for voice selection (e.g., "fr", "en").
            priority: Generation priority.

        Returns:
            WAV audio bytes or None if failed.
        """
        request = GenerateRequest(
            id=str(uuid.uuid4()),
            text=text,
            voice=voice,
            rate=rate,
            voice_name=voice_name,
            language=language,
            priority=priority,
        )

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if not isinstance(response, GenerateResponse):
            logger.error("Unexpected response type")
            return None

        if not response.ok:
            logger.error("Generate failed: %s", response.error)
            return None

        # Decode base64 audio data
        try:
            return base64.b64decode(response.data)
        except Exception as e:
            logger.error("Failed to decode audio data: %s", e)
            return None

    async def invalidate(
        self, rate: int = 180, voice_name: str | None = None
    ) -> InvalidateResponse | None:
        """Invalidate queue and switch settings.

        Args:
            rate: New speech rate.
            voice_name: New voice name.

        Returns:
            Response or None if failed.
        """
        request = InvalidateRequest(
            id=str(uuid.uuid4()),
            rate=rate,
            voice_name=voice_name,
        )

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, InvalidateResponse):
            return response
        return None

    async def queue(
        self,
        texts: list[str],
        voice: str = "cockpit",
        rate: int = 180,
        voice_name: str | None = None,
        priority: int = 1,
    ) -> QueueResponse | None:
        """Queue items for background generation.

        Args:
            texts: List of texts to queue.
            voice: Logical voice name.
            rate: Speech rate.
            voice_name: Platform-specific voice name.
            priority: Generation priority.

        Returns:
            Response or None if failed.
        """
        request = QueueRequest(
            id=str(uuid.uuid4()),
            texts=texts,
            voice=voice,
            rate=rate,
            voice_name=voice_name,
            priority=priority,
        )

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, QueueResponse):
            return response
        return None

    async def ping(self) -> PingResponse | None:
        """Health check ping.

        Returns:
            Response or None if failed.
        """
        request = PingRequest(id=str(uuid.uuid4()))

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, PingResponse):
            return response
        return None

    async def stats(self) -> StatsResponse | None:
        """Get cache statistics.

        Returns:
            Response or None if failed.
        """
        request = StatsRequest(id=str(uuid.uuid4()))

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, StatsResponse):
            return response
        return None

    async def set_context(
        self,
        context: str,
        voices: dict[str, dict[str, Any]] | None = None,
    ) -> ContextResponse | None:
        """Set the current flight context for pre-generation prioritization.

        Tells the service what context the sim is in so it can prioritize
        pre-generating the most likely needed TTS items.

        Args:
            context: Flight context ("menu", "ground", "airborne").
            voices: Dict of voice configs {voice_name: {rate, voice_name}}.
                    Used for pre-generation with correct settings.

        Returns:
            Response with number of items queued for pre-generation.
        """
        request = ContextRequest(
            id=str(uuid.uuid4()),
            context=context,
            voices=voices or {},
        )

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, ContextResponse):
            return response
        return None

    async def queue_priority_items(self) -> int:
        """Queue standard priority items for background generation.

        Returns:
            Number of items queued.
        """
        total_queued = 0

        # Priority 1: Numbers 0-999 + common words
        texts = [str(i) for i in range(1000)]
        texts.extend(
            [
                "heading",
                "altitude",
                "airspeed",
                "knots",
                "feet",
                "degrees",
                "flight level",
                "runway",
                "cleared",
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "niner",
                "ten",
                "hundred",
                "thousand",
                "decimal",
                "point",
            ]
        )

        response = await self.queue(texts, priority=1)
        if response:
            total_queued += response.queued
            logger.info("Queued priority 1: %d items", response.queued)

        # Priority 2: Numbers 1000-5000
        texts = [str(i) for i in range(1000, 5001)]
        response = await self.queue(texts, priority=2)
        if response:
            total_queued += response.queued
            logger.info("Queued priority 2: %d items", response.queued)

        return total_queued

    async def list_engines(self) -> ListEnginesResponse | None:
        """List available TTS engines.

        Returns:
            Response with list of available engines, or None if failed.
        """
        request = ListEnginesRequest(id=str(uuid.uuid4()))

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, ListEnginesResponse):
            return response
        return None

    async def list_voices(
        self,
        engine: str | None = None,
        language: str | None = None,
    ) -> ListVoicesResponse | None:
        """List available TTS voices.

        Args:
            engine: Optional engine filter (e.g., "apple", "edge").
            language: Optional language filter (e.g., "en", "fr").

        Returns:
            Response with list of available voices, or None if failed.
        """
        request = ListVoicesRequest(
            id=str(uuid.uuid4()),
            engine=engine,
            language=language,
        )

        response_data = await self._send_request(request.to_dict())
        if not response_data:
            return None

        response = parse_response(response_data)
        if isinstance(response, ListVoicesResponse):
            return response
        return None
