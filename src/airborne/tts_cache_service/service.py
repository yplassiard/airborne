"""TTS Cache Service - WebSocket server for TTS generation.

This module provides the main service entry point that runs as a subprocess.
It runs pyttsx3 in its main thread (avoiding macOS threading issues) and
serves requests via WebSocket.

Usage:
    python -m airborne.tts_cache_service.service [--config path/to/config.yaml]
"""

import argparse
import asyncio
import base64
import json
import logging
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

try:
    import websockets
    from websockets.server import serve
except ImportError:
    print("ERROR: websockets package required. Install with: uv add websockets")
    sys.exit(1)

from airborne.tts_cache_service.cache import TTSDiskCache, VoiceSettings
from airborne.tts_cache_service.protocol import (
    ContextRequest,
    ContextResponse,
    EngineInfo,
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
    Response,
    ShutdownRequest,
    StatsRequest,
    StatsResponse,
    VoiceInfo,
    parse_request,
)

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    """Item in background generation queue."""

    text: str
    priority: int


@dataclass
class VoiceQueueItem:
    """Item in background generation queue with voice settings."""

    text: str
    voice: str
    rate: int
    voice_name: str | None
    priority: int


# Pre-generation items by context
# Each context defines what items should be pre-generated and their priority
# Lower priority number = higher priority (generated first)
PREGEN_ITEMS: dict[str, list[tuple[int, list[str]]]] = {
    "menu": [
        # Menu context - just basic numbers for UI
        (1, [str(i) for i in range(100)]),
    ],
    "ground": [
        # Ground context - taxi and pre-takeoff phrases
        (1, [str(i) for i in range(40)]),  # Runway numbers, gates
        (1, ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner"]),
        (1, ["runway", "taxi", "hold short", "cleared", "position", "hold"]),
        (1, ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]),
        (1, ["india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa"]),
        (1, ["quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey"]),
        (1, ["x-ray", "yankee", "zulu"]),
        (2, [str(i) for i in range(100, 370, 10)]),  # Headings by 10
        (3, [str(i) for i in range(40, 100)]),  # More runway numbers, speeds
    ],
    "airborne": [
        # Airborne context - altitudes, headings, speeds, frequencies
        (1, [str(i) for i in range(100)]),  # Basic numbers for readouts
        (1, ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner"]),
        (1, ["altitude", "heading", "airspeed", "vertical speed"]),
        (1, ["feet", "knots", "degrees", "flight level"]),
        (1, ["hundred", "thousand", "decimal", "point"]),
        (2, [str(i) for i in range(100, 400)]),  # Speeds 100-400
        (2, [str(i) for i in range(1000, 10000, 500)]),  # Altitudes by 500
        (2, [str(i) for i in range(0, 360, 10)]),  # Headings by 10
        (3, [str(i) for i in range(10000, 45000, 1000)]),  # Higher altitudes
        (3, [str(i) for i in range(400, 1000)]),  # Additional numbers
    ],
}


class TTSCacheService:
    """WebSocket-based TTS cache service.

    Handles TTS generation requests, manages disk cache, and runs
    background generation of queued items. Supports multiple voice
    configurations with separate cache directories per voice.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize service.

        Args:
            config: Configuration dictionary from YAML.
        """
        self.config = config
        self.start_time = time.time()

        # Server settings
        server_config = config.get("server", {})
        self.host = server_config.get("host", "127.0.0.1")
        self.port = server_config.get("port", 51127)

        # Cache settings
        cache_config = config.get("cache", {})
        cache_base = cache_config.get("base_dir")
        self._cache_base: Path | None = Path(cache_base) if cache_base else None

        # Multi-voice cache - one cache per voice settings
        self._caches: dict[str, TTSDiskCache] = {}

        # Cleanup settings
        cleanup_config = cache_config.get("cleanup", {})
        self.cleanup_enabled = cleanup_config.get("enabled", True)
        self.cleanup_interval_minutes = cleanup_config.get("interval_minutes", 60)
        self.grace_period_days = cleanup_config.get("grace_period_days", 2)

        # Generation settings
        gen_config = config.get("generation", {})
        self.gen_delay = gen_config.get("delay_between_items", 0.1)
        self.max_queue_size = gen_config.get("max_queue_size", 50000)

        # Background queue for pre-generation (with voice settings)
        self._queue: deque[VoiceQueueItem] = deque()
        self._queued_keys: set[str] = set()  # "voice:text" keys
        self._queue_lock = asyncio.Lock()

        # Generation request queue - for main thread to process
        # Items are (text, voice, rate, voice_name, language, result_future) tuples
        self._generation_request_queue: asyncio.Queue[
            tuple[str, str, int, str | None, str | None, asyncio.Future[bytes | None]]
        ] = asyncio.Queue()

        # State
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._user_request_event = asyncio.Event()

        # Context state for pre-generation prioritization
        self._current_context = "menu"
        self._voice_configs: dict[str, dict[str, Any]] = {}  # voice -> {rate, voice_name}

        # Load user voice settings from saved settings file
        self._user_voice_settings: dict[str, dict[str, Any]] = {}
        self._load_user_voice_settings()

        # Pre-load caches for all configured voices so existing cached items are available
        self._preload_caches()

        logger.info(
            "TTSCacheService initialized: %s:%d (multi-voice)",
            self.host,
            self.port,
        )

    def _load_user_voice_settings(self) -> None:
        """Load user's saved TTS voice settings from settings file.

        Loads voice preferences (voice_name, rate) for each voice category
        from the user's settings.json file. This is used to apply user
        preferences when generating TTS without explicit voice parameters.
        """
        try:
            from airborne.settings import get_tts_settings

            tts_settings = get_tts_settings()

            # Map voice categories to user settings categories
            # Some voice types don't have direct user settings,
            # so we use related categories as fallbacks
            category_mapping = {
                "cockpit": "cockpit",
                "pilot": "cockpit",
                "tower": "tower",
                "ground": "ground",
                "approach": "approach",
                "atis": "atis",
                "steward": "ui",
                "refuel": "ground",
                "tug": "ground",
                "boarding": "ground",
                "ops": "ground",
                "instructor": "cockpit",
                "atc": "atc",
                "ui": "ui",
            }

            for voice_type, settings_category in category_mapping.items():
                user_voice = tts_settings.get_voice(settings_category)
                self._user_voice_settings[voice_type] = {
                    "voice_name": user_voice.voice_name,
                    "rate": user_voice.rate,
                }

            logger.info(
                "Loaded user TTS settings for %d voice categories",
                len(self._user_voice_settings),
            )

        except Exception as e:
            logger.warning("Failed to load user voice settings: %s", e)
            # Continue without user settings - will use defaults

    def _get_user_voice_settings(self, voice: str) -> dict[str, Any] | None:
        """Get user's saved voice settings for a voice category.

        Args:
            voice: Voice category name (e.g., "cockpit", "tower").

        Returns:
            Dict with "voice_name" and "rate" keys, or None if not found.
        """
        return self._user_voice_settings.get(voice)

    def _preload_caches(self) -> None:
        """Pre-load caches for all user-configured voices.

        This ensures that existing cached TTS files are available immediately
        on startup, rather than waiting for the first request for each voice.
        """
        total_items = 0

        for voice_type, settings in self._user_voice_settings.items():
            voice_name = settings.get("voice_name")
            rate = settings.get("rate", 180)

            # Create cache for this voice (this will load manifest from disk)
            cache = self._get_cache(voice_type, rate, voice_name)
            stats = cache.get_stats()
            cached_items = stats.get("cached_items", 0)
            total_items += cached_items

            if cached_items > 0:
                logger.info(
                    "Pre-loaded cache for '%s' (%s @ %d wpm): %d items",
                    voice_type,
                    voice_name,
                    rate,
                    cached_items,
                )

        logger.info(
            "Pre-loaded %d caches with %d total cached items",
            len(self._caches),
            total_items,
        )

    def _get_cache(
        self, voice: str, rate: int, voice_name: str | None, language: str | None = None
    ) -> TTSDiskCache:
        """Get or create cache for voice settings.

        Args:
            voice: Logical voice name (e.g., "cockpit", "tower").
            rate: Speech rate.
            voice_name: Platform-specific voice name.
            language: Language code for voice selection (e.g., "fr", "en").

        Returns:
            TTSDiskCache instance for these settings.
        """
        settings = VoiceSettings(voice=voice, rate=rate, voice_name=voice_name, language=language)
        cache_key = settings.get_hash()

        if cache_key not in self._caches:
            self._caches[cache_key] = TTSDiskCache(settings, self._cache_base)
            logger.info(
                "Created cache for voice=%s, rate=%d, lang=%s: %s", voice, rate, language, cache_key
            )

        return self._caches[cache_key]

    async def handle_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming request.

        Args:
            request_data: Parsed JSON request.

        Returns:
            Response dictionary.
        """
        request = parse_request(request_data)
        if not request:
            return Response(
                id=request_data.get("id", ""),
                ok=False,
                error=f"Unknown command: {request_data.get('cmd')}",
            ).to_dict()

        try:
            if isinstance(request, GenerateRequest):
                return await self._handle_generate(request)
            elif isinstance(request, InvalidateRequest):
                return await self._handle_invalidate(request)
            elif isinstance(request, QueueRequest):
                return await self._handle_queue(request)
            elif isinstance(request, PingRequest):
                return await self._handle_ping(request)
            elif isinstance(request, StatsRequest):
                return await self._handle_stats(request)
            elif isinstance(request, ShutdownRequest):
                return await self._handle_shutdown(request)
            elif isinstance(request, ContextRequest):
                return await self._handle_context(request)
            elif isinstance(request, ListEnginesRequest):
                return await self._handle_list_engines(request)
            elif isinstance(request, ListVoicesRequest):
                return await self._handle_list_voices(request)
            else:
                return Response(
                    id=request.id,
                    ok=False,
                    error=f"Unhandled command: {request.cmd}",
                ).to_dict()

        except Exception as e:
            logger.exception("Error handling request: %s", e)
            return Response(
                id=request.id,
                ok=False,
                error=str(e),
            ).to_dict()

    async def _handle_generate(self, request: GenerateRequest) -> dict[str, Any]:
        """Handle generate request with voice-specific caching."""
        start_time = time.time()

        # If voice_name not provided, look up user's saved settings
        rate = request.rate
        voice_name = request.voice_name
        if voice_name is None:
            user_settings = self._get_user_voice_settings(request.voice)
            if user_settings:
                voice_name = user_settings.get("voice_name")
                rate = user_settings.get("rate", rate)
                logger.debug(
                    "Using user settings for voice '%s': %s @ %d wpm",
                    request.voice,
                    voice_name,
                    rate,
                )

        # Get cache for this voice configuration
        cache = self._get_cache(request.voice, rate, voice_name, request.language)

        # Remove from background queue if present
        queue_key = f"{request.voice}:{request.text}"
        async with self._queue_lock:
            self._queued_keys.discard(queue_key)

        # Check cache first (this is fast and safe in any thread)
        audio_bytes = cache.get(request.text)
        if audio_bytes:
            duration_ms = (time.time() - start_time) * 1000
            return GenerateResponse(
                id=request.id,
                ok=True,
                size=len(audio_bytes),
                cached=True,
                duration_ms=duration_ms,
                data=base64.b64encode(audio_bytes).decode("ascii"),
            ).to_dict()

        # Cache miss - queue for generation in main thread
        # Put request in generation queue and wait for result
        result_future: asyncio.Future[bytes | None] = asyncio.get_event_loop().create_future()
        await self._generation_request_queue.put(
            (
                request.text,
                request.voice,
                rate,  # Use resolved rate (may be from user settings)
                voice_name,  # Use resolved voice_name (may be from user settings)
                request.language,
                result_future,
            )
        )

        try:
            audio_bytes = await asyncio.wait_for(result_future, timeout=30.0)
        except TimeoutError:
            return GenerateResponse(
                id=request.id,
                ok=False,
                error="Generation timeout",
                duration_ms=(time.time() - start_time) * 1000,
            ).to_dict()

        duration_ms = (time.time() - start_time) * 1000

        if audio_bytes:
            return GenerateResponse(
                id=request.id,
                ok=True,
                size=len(audio_bytes),
                cached=False,
                duration_ms=duration_ms,
                data=base64.b64encode(audio_bytes).decode("ascii"),
            ).to_dict()
        else:
            return GenerateResponse(
                id=request.id,
                ok=False,
                error="Generation failed",
                duration_ms=duration_ms,
            ).to_dict()

    async def _handle_invalidate(self, request: InvalidateRequest) -> dict[str, Any]:
        """Handle invalidate request - clear queue (voice switching not needed with multi-voice)."""
        # Clear queue
        async with self._queue_lock:
            cleared = len(self._queue)
            self._queue.clear()
            self._queued_keys.clear()

        return InvalidateResponse(
            id=request.id,
            ok=True,
            cleared_queue=cleared,
            new_settings_hash="multi-voice",
        ).to_dict()

    async def _handle_queue(self, request: QueueRequest) -> dict[str, Any]:
        """Handle queue request - add items for background generation."""
        queued = 0
        skipped = 0

        # Get cache for this voice
        cache = self._get_cache(request.voice, request.rate, request.voice_name)

        async with self._queue_lock:
            for text in request.texts:
                if not text or not text.strip():
                    continue

                queue_key = f"{request.voice}:{text}"

                # Skip if already cached or queued
                if cache.contains(text):
                    skipped += 1
                    continue

                if queue_key in self._queued_keys:
                    skipped += 1
                    continue

                if len(self._queue) >= self.max_queue_size:
                    break

                self._queue.append(
                    VoiceQueueItem(
                        text=text,
                        voice=request.voice,
                        rate=request.rate,
                        voice_name=request.voice_name,
                        priority=request.priority,
                    )
                )
                self._queued_keys.add(queue_key)
                queued += 1

        return QueueResponse(
            id=request.id,
            ok=True,
            queued=queued,
            skipped=skipped,
        ).to_dict()

    async def _handle_ping(self, request: PingRequest) -> dict[str, Any]:
        """Handle ping request - health check."""
        return PingResponse(
            id=request.id,
            ok=True,
            uptime_s=time.time() - self.start_time,
            queue_size=len(self._queue),
        ).to_dict()

    async def _handle_stats(self, request: StatsRequest) -> dict[str, Any]:
        """Handle stats request - aggregate stats from all caches."""
        total_hits = 0
        total_misses = 0
        total_generated = 0
        total_items = 0
        total_size_mb = 0.0

        for cache in self._caches.values():
            stats = cache.get_stats()
            total_hits += stats["hits"]
            total_misses += stats["misses"]
            total_generated += stats["generated"]
            total_items += stats["cached_items"]
            total_size_mb += stats["cache_size_mb"]

        return StatsResponse(
            id=request.id,
            ok=True,
            cache_hits=total_hits,
            cache_misses=total_misses,
            generated=total_generated,
            cached_items=total_items,
            queue_size=len(self._queue),
            cache_size_mb=total_size_mb,
            settings_hash=f"multi-voice ({len(self._caches)} voices)",
        ).to_dict()

    async def _handle_shutdown(self, request: ShutdownRequest) -> dict[str, Any]:
        """Handle shutdown request."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()
        return Response(id=request.id, ok=True).to_dict()

    async def _handle_context(self, request: ContextRequest) -> dict[str, Any]:
        """Handle context change request.

        Updates the current flight context and queues pre-generation items
        for the new context. Clears the existing queue first to prioritize
        the new context's items.

        Args:
            request: Context request with context type and voice configs.

        Returns:
            Response with number of items queued.
        """
        old_context = self._current_context
        self._current_context = request.context
        self._voice_configs = request.voices

        logger.info(
            "Context changed: %s -> %s (voices: %s)",
            old_context,
            request.context,
            list(request.voices.keys()),
        )

        # Clear existing queue to prioritize new context
        async with self._queue_lock:
            self._queue.clear()
            self._queued_keys.clear()

        # Queue pre-generation items for the new context
        total_queued = 0
        pregen_items = PREGEN_ITEMS.get(request.context, [])

        # For each voice configuration, queue the pre-generation items
        for voice_name, voice_config in request.voices.items():
            rate = voice_config.get("rate", 180)
            platform_voice = voice_config.get("voice_name")

            # Get or create cache for this voice
            cache = self._get_cache(voice_name, rate, platform_voice)

            async with self._queue_lock:
                for priority, texts in pregen_items:
                    for text in texts:
                        if not text or not text.strip():
                            continue

                        queue_key = f"{voice_name}:{text}"

                        # Skip if already cached or queued
                        if cache.contains(text):
                            continue
                        if queue_key in self._queued_keys:
                            continue
                        if len(self._queue) >= self.max_queue_size:
                            break

                        self._queue.append(
                            VoiceQueueItem(
                                text=text,
                                voice=voice_name,
                                rate=rate,
                                voice_name=platform_voice,
                                priority=priority,
                            )
                        )
                        self._queued_keys.add(queue_key)
                        total_queued += 1

        # Sort queue by priority (lower = higher priority)
        async with self._queue_lock:
            sorted_items = sorted(self._queue, key=lambda x: x.priority)
            self._queue = deque(sorted_items)

        logger.info(
            "Queued %d pre-generation items for context '%s'",
            total_queued,
            request.context,
        )

        return ContextResponse(
            id=request.id,
            ok=True,
            context=request.context,
            queued=total_queued,
        ).to_dict()

    async def _handle_list_engines(self, request: ListEnginesRequest) -> dict[str, Any]:
        """Handle list_engines request - return available TTS engines.

        Currently only Apple TTS is supported. Future engines: Edge TTS, Kokoro.
        """
        engines = [
            EngineInfo(
                name="apple",
                display_name="Apple TTS",
                available=True,
                description="macOS built-in text-to-speech using NSSpeechSynthesizer",
            ),
            EngineInfo(
                name="edge",
                display_name="Microsoft Edge TTS",
                available=False,  # Not implemented yet
                description="Microsoft Edge online TTS service (requires internet)",
            ),
            EngineInfo(
                name="kokoro",
                display_name="Kokoro TTS",
                available=False,  # Not implemented yet
                description="Local neural TTS engine (requires model download)",
            ),
        ]

        return ListEnginesResponse(
            id=request.id,
            ok=True,
            engines=engines,
        ).to_dict()

    async def _handle_list_voices(self, request: ListVoicesRequest) -> dict[str, Any]:
        """Handle list_voices request - return available voices.

        Queries macOS `say -v ?` to get available voices, optionally filtered
        by engine and/or language.
        """
        import re
        import subprocess

        voices: list[VoiceInfo] = []

        # For now, only Apple engine is supported
        if request.engine is None or request.engine == "apple":
            try:
                # Get voices from macOS say command
                result = subprocess.run(
                    ["say", "-v", "?"],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                # Voice format examples:
                # "Albert              en_US    # Hello! ..."
                # "Alex (Anglais (É.-U.)) en_US    # Hello! ..."
                # "(null) - Adam (Anglais) en_US    # ..."
                # We want to extract: voice_name, lang_code
                # Skip lines starting with "(null)"

                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue

                    # Skip personal/premium voices that aren't installed
                    if line.startswith("(null)"):
                        continue

                    # Find language code pattern (xx_XX) before the #
                    lang_match = re.search(r"\b([a-z]{2}_[A-Z]{2})\b", line)
                    if not lang_match:
                        continue

                    lang_code = lang_match.group(1)

                    # Extract voice name - everything before the language code
                    # or before the parenthetical description
                    name_part = line[: lang_match.start()].strip()

                    # Handle "Name (Description)" format - extract just the name
                    paren_match = re.match(r"^([A-Za-zÀ-ÿ\-]+)", name_part)
                    if paren_match:
                        name = paren_match.group(1).strip()
                    else:
                        name = name_part.split()[0] if name_part.split() else ""

                    if not name:
                        continue

                    # Apply language filter if specified
                    if request.language:
                        # Match prefix (e.g., "en" matches "en_US", "en_GB")
                        if not lang_code.lower().startswith(request.language.lower()):
                            continue

                    # Infer gender from voice name (rough heuristic)
                    female_names = {
                        "Samantha",
                        "Victoria",
                        "Siri",
                        "Karen",
                        "Moira",
                        "Tessa",
                        "Fiona",
                        "Veena",
                        "Ava",
                        "Allison",
                        "Susan",
                        "Kate",
                        "Serena",
                        "Emily",
                        "Zoe",
                        "Ellen",
                        "Paulina",
                        "Monica",
                        "Luciana",
                        "Joana",
                        "Amélie",
                        "Amelie",
                        "Anna",
                        "Carmit",
                        "Damayanti",
                        "Helena",
                        "Ioana",
                        "Kanya",
                        "Kyoko",
                        "Laura",
                        "Lekha",
                        "Mariska",
                        "Mei-Jia",
                        "Melina",
                        "Milena",
                        "Nora",
                        "Sara",
                        "Satu",
                        "Sin-ji",
                        "Thi-Mai",
                        "Ting-Ting",
                        "Yuna",
                        "Zosia",
                        "Lesya",
                        "Alice",
                        "Amira",
                        "Alva",
                        "Linh",
                        "Lana",
                        "Soumya",
                    }
                    male_names = {
                        "Alex",
                        "Daniel",
                        "Fred",
                        "Tom",
                        "Oliver",
                        "Evan",
                        "Aaron",
                        "Rishi",
                        "Thomas",
                        "Gordon",
                        "Luca",
                        "Maged",
                        "Xander",
                        "Jacques",
                        "Yuri",
                        "Diego",
                        "Jorge",
                        "Juan",
                        "Martin",
                        "Nicolas",
                        "Albert",
                        "Aman",
                        "Lekha",
                        "Bruce",
                        "Lee",
                        "Ralph",
                    }

                    if name in female_names:
                        gender = "female"
                    elif name in male_names:
                        gender = "male"
                    else:
                        gender = "neutral"

                    voices.append(
                        VoiceInfo(
                            name=name,
                            engine="apple",
                            language=lang_code,
                            gender=gender,
                        )
                    )

            except subprocess.CalledProcessError as e:
                logger.error("Failed to list voices: %s", e)
                return ListVoicesResponse(
                    id=request.id,
                    ok=False,
                    error=f"Failed to list voices: {e}",
                ).to_dict()

        return ListVoicesResponse(
            id=request.id,
            ok=True,
            voices=voices,
            engine_filter=request.engine,
            language_filter=request.language,
        ).to_dict()

    async def websocket_handler(self, websocket: Any) -> None:
        """Handle WebSocket connection."""
        client_addr = websocket.remote_address
        logger.info("Client connected: %s", client_addr)

        try:
            async for message in websocket:
                try:
                    request_data = json.loads(message)
                    response = await self.handle_request(request_data)
                    await websocket.send(json.dumps(response))

                except json.JSONDecodeError as e:
                    error_response = Response(
                        id="",
                        ok=False,
                        error=f"Invalid JSON: {e}",
                    ).to_dict()
                    await websocket.send(json.dumps(error_response))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected: %s", client_addr)

    async def generation_processor_loop(self) -> None:
        """Process generation requests in the main thread.

        This loop handles both user requests (priority) and background
        generation. pyttsx3 must run in the main thread on macOS.
        """
        logger.info("Generation processor loop started")

        while not self._shutdown_event.is_set():
            # First, check for user generation requests (priority)
            try:
                text, voice, rate, voice_name, language, result_future = (
                    self._generation_request_queue.get_nowait()
                )
                logger.debug(
                    "Processing user request: %s (voice=%s, lang=%s)", text[:30], voice, language
                )

                # Get cache for this voice
                cache = self._get_cache(voice, rate, voice_name, language)

                # Generate synchronously in main thread
                audio_bytes = cache.generate(text)
                if audio_bytes:
                    cache.put(text, audio_bytes)

                # Return result
                if not result_future.done():
                    result_future.set_result(audio_bytes)

                await asyncio.sleep(0.01)  # Yield to event loop
                continue

            except asyncio.QueueEmpty:
                pass

            # Then, process background queue
            item: VoiceQueueItem | None = None
            async with self._queue_lock:
                if self._queue:
                    item = self._queue.popleft()
                    queue_key = f"{item.voice}:{item.text}"
                    self._queued_keys.discard(queue_key)

            if item:
                # Get cache for this voice
                cache = self._get_cache(item.voice, item.rate, item.voice_name)

                # Skip if already cached
                if not cache.contains(item.text):
                    try:
                        audio_bytes = cache.generate(item.text)
                        if audio_bytes:
                            cache.put(item.text, audio_bytes)
                            logger.debug(
                                "Background generated: %s (voice=%s)",
                                item.text[:30],
                                item.voice,
                            )
                    except Exception as e:
                        logger.error("Background generation error: %s", e)

                    # Delay between background items
                    await asyncio.sleep(self.gen_delay)
                else:
                    await asyncio.sleep(0.01)
            else:
                # No work, wait a bit
                await asyncio.sleep(0.1)

        logger.info("Generation processor loop ended")

    async def cleanup_loop(self) -> None:
        """Periodic cleanup of old cache entries."""
        if not self.cleanup_enabled:
            logger.info("Cache cleanup disabled")
            return

        logger.info("Cleanup loop started (interval: %d min)", self.cleanup_interval_minutes)

        # Run cleanup on startup
        await asyncio.sleep(5)  # Wait for service to stabilize

        async def run_cleanup():
            for cache in self._caches.values():
                cache.cleanup_lru(self.grace_period_days)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: None)  # Placeholder for sync cleanup
        # Cleanup all caches
        for cache in self._caches.values():
            await loop.run_in_executor(None, cache.cleanup_lru, self.grace_period_days)

        # Periodic cleanup
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self.cleanup_interval_minutes * 60)
            if self._shutdown_event.is_set():
                break
            for cache in self._caches.values():
                await loop.run_in_executor(None, cache.cleanup_lru, self.grace_period_days)

        logger.info("Cleanup loop ended")

    async def run(self) -> None:
        """Run the service."""
        self._running = True

        # Start background tasks
        generation_task = asyncio.create_task(self.generation_processor_loop())
        cleanup_task = asyncio.create_task(self.cleanup_loop())

        # Start WebSocket server
        logger.info("Starting WebSocket server on %s:%d", self.host, self.port)

        try:
            async with serve(self.websocket_handler, self.host, self.port):
                logger.info("TTS Cache Service ready")
                await self._shutdown_event.wait()

        except Exception as e:
            logger.error("Server error: %s", e)
            raise

        finally:
            # Cleanup
            logger.info("Shutting down...")
            self._shutdown_event.set()

            # Wait for background tasks
            generation_task.cancel()
            cleanup_task.cancel()

            try:
                await asyncio.gather(generation_task, cleanup_task, return_exceptions=True)
            except asyncio.CancelledError:
                pass

            # Save all caches
            for cache in self._caches.values():
                cache.save()
            logger.info("TTS Cache Service stopped")


def setup_logging(config: dict[str, Any]) -> None:
    """Setup logging from config."""
    log_config = config.get("logging", {})
    log_file = log_config.get("file", "tts_cache_service.log")
    log_level = log_config.get("level", "INFO")
    max_size_mb = log_config.get("max_size_mb", 10)
    backup_count = log_config.get("backup_count", 3)

    # Ensure log file is in the correct directory (not relative to cwd)
    log_path = Path(log_file)
    if not log_path.is_absolute():
        # Use ~/Library/Logs/AirBorne on macOS, or ~/.airborne on others
        import sys
        if sys.platform == "darwin":
            log_dir = Path.home() / "Library" / "Logs" / "AirBorne"
        else:
            log_dir = Path.home() / ".airborne" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_path.name

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
    )
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def load_config(config_path: Path | None) -> dict[str, Any]:
    """Load configuration from YAML file."""
    default_paths = [
        Path("config/tts_cache_service.yaml"),
        Path(__file__).parent.parent.parent.parent / "config" / "tts_cache_service.yaml",
    ]

    if config_path:
        paths = [config_path]
    else:
        paths = default_paths

    for path in paths:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info("Loaded config from: %s", path)
            return config

    # Return defaults if no config found
    logger.warning("No config file found, using defaults")
    return {}


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TTS Cache Service")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override WebSocket port",
    )
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Override port if specified
    if args.port:
        config.setdefault("server", {})["port"] = args.port

    # Setup logging
    setup_logging(config)

    logger.info("TTS Cache Service starting...")

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


def run_service(
    host: str = "127.0.0.1",
    port: int = 51127,
    stop_event: "threading.Event | None" = None,
) -> None:
    """Run the TTS service (for use from a thread in bundled mode).

    Args:
        host: WebSocket server host.
        port: WebSocket server port.
        stop_event: Threading event to signal shutdown.
    """
    import threading

    # Load config
    config = load_config(None)

    # Override host/port
    config.setdefault("server", {})["host"] = host
    config.setdefault("server", {})["port"] = port

    # Setup logging (minimal for thread mode)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("TTS Cache Service starting in thread mode...")

    # Create service
    service = TTSCacheService(config)

    # Monitor stop_event in a thread
    if stop_event:
        def monitor_stop() -> None:
            stop_event.wait()
            logger.info("Stop event received, shutting down service...")
            service._shutdown_event.set()

        monitor_thread = threading.Thread(target=monitor_stop, daemon=True)
        monitor_thread.start()

    # Run service
    try:
        asyncio.run(service.run())
    except Exception as e:
        logger.exception("TTS service error: %s", e)


if __name__ == "__main__":
    main()
