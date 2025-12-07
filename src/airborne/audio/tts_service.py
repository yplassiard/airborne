"""TTS Service facade for centralized text-to-speech management.

This module provides a clean synchronous API for TTS operations, hiding all
async/threading complexity from consumers. It ensures:
- Single TTSServiceClient instance across the application
- Single asyncio event loop for all TTS operations
- Priority-based request processing
- Proper callback/result binding via request IDs

Typical usage:
    from airborne.audio.tts_service import TTSService, TTSPriority

    # At application startup
    tts = TTSService()
    tts.start()
    registry.register("tts_service", tts)

    # In components
    tts.speak("altitude 3500", voice="cockpit", on_audio=play_audio)
    tts.speak("STALL", priority=TTSPriority.CRITICAL, on_audio=play_audio)

    # In main loop
    tts.update()  # Processes results, invokes callbacks

    # At shutdown
    tts.shutdown()
"""

from __future__ import annotations

import heapq
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio

    from airborne.tts_cache_service.client import TTSServiceClient

logger = logging.getLogger(__name__)


class TTSPriority(IntEnum):
    """TTS request priority levels.

    Higher values indicate higher priority. CRITICAL requests will
    interrupt and flush lower priority pending requests.
    """

    LOW = 0  # Pre-generation, ambient, non-urgent
    NORMAL = 1  # Standard callouts
    HIGH = 2  # Important (altitude, heading changes)
    CRITICAL = 3  # Safety-critical (stall, terrain, pull up)


@dataclass(order=True)
class TTSRequest:
    """Internal request structure for TTS generation.

    Ordered by priority (descending) then sequence (ascending) for heap.
    """

    # For heap ordering: negate priority so higher priority comes first
    sort_key: tuple[int, int] = field(compare=True, repr=False)
    # Actual data (not used for comparison)
    request_id: str = field(compare=False)
    text: str = field(compare=False)
    voice: str = field(compare=False)
    priority: TTSPriority = field(compare=False)
    # Optional explicit voice parameters (for language changes)
    voice_name: str | None = field(compare=False, default=None)
    rate: int = field(compare=False, default=180)
    language: str | None = field(compare=False, default=None)

    @classmethod
    def create(
        cls,
        request_id: str,
        text: str,
        voice: str,
        priority: TTSPriority,
        sequence: int,
        voice_name: str | None = None,
        rate: int = 180,
        language: str | None = None,
    ) -> TTSRequest:
        """Create a request with proper sort key.

        Args:
            request_id: Unique identifier for callback binding.
            text: Text to synthesize.
            voice: Voice name.
            priority: Request priority.
            sequence: Monotonic sequence number for FIFO within same priority.
            voice_name: Platform-specific voice name (e.g., "Samantha", "Amélie").
            rate: Speech rate in words per minute.
            language: Language code (e.g., "en", "fr").

        Returns:
            TTSRequest instance.
        """
        # Negate priority so higher priority = lower sort key = comes first
        sort_key = (-priority, sequence)
        return cls(
            sort_key=sort_key,
            request_id=request_id,
            text=text,
            voice=voice,
            priority=priority,
            voice_name=voice_name,
            rate=rate,
            language=language,
        )


@dataclass(order=True)
class TTSResult:
    """Internal result structure for completed TTS generation.

    Ordered by priority (descending) then sequence (ascending) for heap.
    """

    sort_key: tuple[int, int] = field(compare=True, repr=False)
    request_id: str = field(compare=False)
    audio: bytes = field(compare=False)
    priority: TTSPriority = field(compare=False)

    @classmethod
    def create(
        cls,
        request_id: str,
        audio: bytes,
        priority: TTSPriority,
        sequence: int,
    ) -> TTSResult:
        """Create a result with proper sort key.

        Args:
            request_id: Unique identifier for callback binding.
            audio: WAV audio bytes.
            priority: Result priority (inherited from request).
            sequence: Monotonic sequence number.

        Returns:
            TTSResult instance.
        """
        sort_key = (-priority, sequence)
        return cls(
            sort_key=sort_key,
            request_id=request_id,
            audio=audio,
            priority=priority,
        )


class TTSService:
    """TTS Service facade - the only interface components interact with.

    Provides a synchronous API for TTS operations while internally managing
    an async backend thread. All callbacks are invoked on the main thread
    during update() calls.

    Thread Safety:
        - speak() can be called from any thread
        - update() must be called from the main thread
        - Callbacks are always invoked on the main thread

    Priority Handling:
        - Requests are processed in priority order (CRITICAL first)
        - interrupt=True flushes lower priority pending requests
        - Results are delivered in priority order

    Attributes:
        is_running: Whether the service is currently running.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 51127) -> None:
        """Initialize the TTS service.

        Args:
            host: TTS cache service host.
            port: TTS cache service port.
        """
        self._host = host
        self._port = port

        # Threading primitives
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._ready_event = threading.Event()

        # Request queue (priority heap)
        self._request_queue: list[TTSRequest] = []
        self._request_sequence = 0

        # Result queue (priority heap)
        self._result_queue: list[TTSResult] = []
        self._result_sequence = 0

        # Callback registry: request_id -> callback
        self._pending_callbacks: dict[str, Callable[[bytes], None] | None] = {}

        # Backend thread and client
        self._backend_thread: threading.Thread | None = None
        self._backend_loop: asyncio.AbstractEventLoop | None = None
        self._client: TTSServiceClient | None = None

        # State
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._is_running

    def start(self, timeout: float = 10.0) -> bool:
        """Start the TTS service.

        Spawns the backend thread and waits for it to be ready.

        Args:
            timeout: Maximum time to wait for service to be ready.

        Returns:
            True if service started successfully, False otherwise.
        """
        if self._is_running:
            logger.warning("TTSService already running")
            return True

        logger.info("Starting TTSService...")

        # Clear events
        self._shutdown_event.clear()
        self._ready_event.clear()

        # Start backend thread
        self._backend_thread = threading.Thread(
            target=self._backend_worker,
            name="TTSServiceBackend",
            daemon=True,
        )
        self._backend_thread.start()

        # Wait for ready signal
        if not self._ready_event.wait(timeout=timeout):
            logger.error("TTSService failed to start within timeout")
            self._shutdown_event.set()
            return False

        self._is_running = True
        logger.info("TTSService started successfully")
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        """Shutdown the TTS service.

        Signals the backend thread to stop and waits for it to finish.

        Args:
            timeout: Maximum time to wait for graceful shutdown.
        """
        if not self._is_running:
            return

        logger.info("Shutting down TTSService...")
        self._is_running = False

        # Signal shutdown
        self._shutdown_event.set()

        # Wake up the backend if it's waiting
        with self._lock:
            # Push a dummy request to wake the backend
            dummy = TTSRequest.create(
                request_id="__shutdown__",
                text="",
                voice="",
                priority=TTSPriority.CRITICAL,
                sequence=self._request_sequence,
            )
            heapq.heappush(self._request_queue, dummy)
            self._request_sequence += 1

        # Wait for thread to finish
        if self._backend_thread and self._backend_thread.is_alive():
            self._backend_thread.join(timeout=timeout)
            if self._backend_thread.is_alive():
                logger.warning("TTSService backend thread did not stop cleanly")

        # Clear queues
        with self._lock:
            self._request_queue.clear()
            self._result_queue.clear()
            self._pending_callbacks.clear()

        self._backend_thread = None
        logger.info("TTSService shutdown complete")

    def speak(
        self,
        text: str,
        voice: str = "cockpit",
        priority: TTSPriority = TTSPriority.NORMAL,
        interrupt: bool = False,
        on_audio: Callable[[bytes], None] | None = None,
        voice_name: str | None = None,
        rate: int = 180,
        language: str | None = None,
    ) -> str:
        """Queue text for speech synthesis.

        Args:
            text: Text to synthesize.
            voice: Voice category name (cockpit, tower, atis, etc.).
            priority: Generation and delivery priority.
            interrupt: If True, flush lower priority pending requests.
            on_audio: Called with WAV bytes when ready (on main thread).
                      If None, audio is generated but discarded (pre-caching).
            voice_name: Platform-specific voice name (e.g., "Samantha", "Amélie").
                        If provided, overrides the voice category lookup.
            rate: Speech rate in words per minute.
            language: Language code (e.g., "en", "fr") for voice selection.

        Returns:
            Request ID for tracking (can be ignored).

        Raises:
            RuntimeError: If service is not running.
        """
        if not self._is_running:
            logger.warning("TTSService not running, ignoring speak request")
            return ""

        if not text:
            return ""

        request_id = str(uuid.uuid4())

        with self._lock:
            # Handle interrupt: flush lower priority items
            if interrupt:
                self._flush_lower_priority(priority)

            # Store callback
            self._pending_callbacks[request_id] = on_audio

            # Create and queue request
            request = TTSRequest.create(
                request_id=request_id,
                text=text,
                voice=voice,
                priority=priority,
                sequence=self._request_sequence,
                voice_name=voice_name,
                rate=rate,
                language=language,
            )
            heapq.heappush(self._request_queue, request)
            self._request_sequence += 1

        logger.debug(
            "TTSService queued: %s (priority=%s, voice_name=%s)",
            text[:30],
            priority.name,
            voice_name,
        )
        return request_id

    def set_context(
        self,
        context: str,
        voices: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Set flight context for pre-generation prioritization.

        Args:
            context: Flight context ("menu", "ground", "airborne").
            voices: Voice configurations for pre-generation.
        """
        if not self._is_running:
            logger.warning("TTSService not running, ignoring set_context")
            return

        # Queue context change request (special handling in backend)
        with self._lock:
            request = TTSRequest.create(
                request_id=f"__context__{context}",
                text=f"__SET_CONTEXT__:{context}",
                voice=str(voices) if voices else "",
                priority=TTSPriority.LOW,
                sequence=self._request_sequence,
            )
            heapq.heappush(self._request_queue, request)
            self._request_sequence += 1

    def update(self) -> int:
        """Process pending results and invoke callbacks.

        Must be called from the main thread (game loop or menu loop).
        Callbacks are invoked synchronously during this call.

        Returns:
            Number of callbacks invoked.
        """
        if not self._is_running:
            return 0

        invoked = 0

        while True:
            with self._lock:
                if not self._result_queue:
                    break

                result = heapq.heappop(self._result_queue)
                callback = self._pending_callbacks.pop(result.request_id, None)

            # Invoke callback outside lock
            if callback is not None:
                try:
                    callback(result.audio)
                    invoked += 1
                except Exception as e:
                    logger.error("TTSService callback error: %s", e)

        return invoked

    def get_pending_count(self) -> tuple[int, int]:
        """Get count of pending requests and results.

        Returns:
            Tuple of (pending_requests, pending_results).
        """
        with self._lock:
            return len(self._request_queue), len(self._result_queue)

    def _flush_lower_priority(self, priority: TTSPriority) -> None:
        """Flush pending items with priority lower than given.

        Must be called with lock held.

        Args:
            priority: Minimum priority to keep.
        """
        # Filter request queue
        new_requests = [r for r in self._request_queue if r.priority >= priority]
        removed_ids = {r.request_id for r in self._request_queue if r.priority < priority}

        if removed_ids:
            heapq.heapify(new_requests)
            self._request_queue = new_requests

            # Filter result queue
            new_results = [r for r in self._result_queue if r.priority >= priority]
            removed_ids.update(r.request_id for r in self._result_queue if r.priority < priority)
            heapq.heapify(new_results)
            self._result_queue = new_results

            # Remove orphaned callbacks
            for rid in removed_ids:
                self._pending_callbacks.pop(rid, None)

            logger.debug("TTSService flushed %d lower priority items", len(removed_ids))

    def _backend_worker(self) -> None:
        """Backend worker thread - runs the async event loop."""
        import asyncio

        from airborne.tts_cache_service import TTSServiceClient

        logger.info("TTSService backend thread starting...")

        # Create event loop for this thread
        self._backend_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._backend_loop)

        async def run_backend() -> None:
            """Async backend main loop."""
            # Initialize client
            self._client = TTSServiceClient(
                host=self._host,
                port=self._port,
                auto_start=True,
            )

            try:
                # Start client
                success = await self._client.start()
                if not success:
                    logger.error("TTSService client failed to start")
                    return

                logger.info("TTSService client connected")

                # Signal ready
                self._ready_event.set()

                # Process requests until shutdown
                while not self._shutdown_event.is_set():
                    request = self._get_next_request()

                    if request is None:
                        # No request, wait a bit
                        await asyncio.sleep(0.01)
                        continue

                    # Check for shutdown signal
                    if request.request_id == "__shutdown__":
                        break

                    # Check for context change
                    if request.text.startswith("__SET_CONTEXT__:"):
                        context = request.text.split(":", 1)[1]
                        voices = eval(request.voice) if request.voice else None  # noqa: S307
                        try:
                            await self._client.set_context(context, voices)
                        except Exception as e:
                            logger.error("TTSService set_context error: %s", e)
                        continue

                    # Generate audio
                    try:
                        audio = await self._client.generate(
                            text=request.text,
                            voice=request.voice,
                            rate=request.rate,
                            voice_name=request.voice_name,
                            language=request.language,
                        )

                        if audio:
                            self._push_result(request.request_id, audio, request.priority)
                        else:
                            # Generation failed, remove callback
                            with self._lock:
                                self._pending_callbacks.pop(request.request_id, None)
                            logger.warning(
                                "TTSService generation returned no audio: %s",
                                request.text[:30],
                            )

                    except Exception as e:
                        logger.error("TTSService generation error: %s", e)
                        with self._lock:
                            self._pending_callbacks.pop(request.request_id, None)

            finally:
                # Cleanup
                if self._client:
                    try:
                        await self._client.stop()
                    except Exception as e:
                        logger.error("TTSService client stop error: %s", e)
                    self._client = None

        # Run the backend
        try:
            self._backend_loop.run_until_complete(run_backend())
        except Exception as e:
            logger.error("TTSService backend error: %s", e)
        finally:
            self._backend_loop.close()
            self._backend_loop = None
            self._ready_event.set()  # Unblock start() if waiting
            logger.info("TTSService backend thread ended")

    def _get_next_request(self) -> TTSRequest | None:
        """Get the next request from the queue.

        Returns:
            Next request or None if queue is empty.
        """
        with self._lock:
            if self._request_queue:
                return heapq.heappop(self._request_queue)
            return None

    def _push_result(
        self,
        request_id: str,
        audio: bytes,
        priority: TTSPriority,
    ) -> None:
        """Push a result to the result queue.

        Args:
            request_id: Request ID for callback binding.
            audio: WAV audio bytes.
            priority: Result priority.
        """
        with self._lock:
            result = TTSResult.create(
                request_id=request_id,
                audio=audio,
                priority=priority,
                sequence=self._result_sequence,
            )
            heapq.heappush(self._result_queue, result)
            self._result_sequence += 1
