"""ATC V2 voice control coordinator.

This module provides the main coordinator for ATC V2 voice control,
orchestrating the flow from PTT → Recording → ASR → NLU → Response → TTS.

Typical usage:
    controller = ATCV2Controller(audio_engine, tts_service)
    controller.initialize(settings)

    # In update loop:
    controller.update(dt)

    # Handle PTT:
    controller.on_ptt_pressed()
    controller.on_ptt_released()
"""

import logging
import threading
from collections.abc import Callable
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from airborne.audio.recording.audio_recorder import AudioRecorder
from airborne.services.atc.atc_handler import ATCHandler, ATCResponse
from airborne.services.atc.intent_processor import FlightContext, IntentProcessor
from airborne.services.atc.providers.base import ATCIntent, IASRProvider, INLUProvider
from airborne.services.atc.providers.local_asr import LocalASRProvider
from airborne.services.atc.providers.local_nlu import LocalNLUProvider
from airborne.settings import PROVIDER_LOCAL, get_atc_v2_settings

if TYPE_CHECKING:
    from airborne.audio.tts_service import TTSService

logger = logging.getLogger(__name__)


class V2State(Enum):
    """State machine for ATC V2 voice control."""

    DISABLED = auto()  # V2 not enabled
    IDLE = auto()  # Ready for PTT
    RECORDING = auto()  # Recording audio (PTT held)
    TRANSCRIBING = auto()  # Processing with ASR
    UNDERSTANDING = auto()  # Processing with NLU
    RESPONDING = auto()  # ATC is responding via TTS
    ERROR = auto()  # Error state


class ATCV2Controller:
    """Coordinator for ATC V2 voice control.

    This class manages the complete voice control pipeline:
    1. PTT input handling
    2. Audio recording via FMOD
    3. Speech recognition via ASR provider
    4. Intent extraction via NLU provider
    5. Response generation via IntentProcessor
    6. Response playback via TTS

    The controller uses a state machine to track progress through
    the pipeline and can handle async processing.
    """

    def __init__(
        self,
        audio_engine: Any = None,
        tts_service: "TTSService | None" = None,
        atc_handler: ATCHandler | None = None,
    ) -> None:
        """Initialize the V2 controller.

        Args:
            audio_engine: FMOD audio engine for recording.
            tts_service: TTS service for response playback.
            atc_handler: ATC handler for response generation.
        """
        self._audio_engine = audio_engine
        self._tts_service = tts_service
        self._atc_handler = atc_handler

        # State
        self._state = V2State.DISABLED
        self._initialized = False
        self._lock = threading.Lock()

        # Components
        self._recorder: AudioRecorder | None = None
        self._asr_provider: IASRProvider | None = None
        self._nlu_provider: INLUProvider | None = None
        self._intent_processor: IntentProcessor | None = None

        # Flight context (updated externally)
        self._flight_context = FlightContext()

        # Processing state
        self._pending_audio: bytes | None = None
        self._processing_thread: threading.Thread | None = None
        self._last_error: str = ""

        # Callbacks
        self._on_state_change: Callable[[V2State], None] | None = None
        self._on_transcription: Callable[[str], None] | None = None
        self._on_intent: Callable[[ATCIntent], None] | None = None
        self._on_response: Callable[[ATCResponse], None] | None = None

        # Audio cues
        self._ptt_start_callback: Callable[[], None] | None = None
        self._ptt_stop_callback: Callable[[], None] | None = None

    def set_audio_engine(self, engine: Any) -> None:
        """Set the audio engine."""
        self._audio_engine = engine

    def set_tts_service(self, service: "TTSService") -> None:
        """Set the TTS service."""
        self._tts_service = service

    def set_atc_handler(self, handler: ATCHandler) -> None:
        """Set the ATC handler."""
        self._atc_handler = handler
        if self._intent_processor:
            self._intent_processor.set_atc_handler(handler)

    def set_flight_context(self, context: FlightContext) -> None:
        """Update the flight context.

        Args:
            context: Current flight context.
        """
        self._flight_context = context

    def set_callbacks(
        self,
        on_state_change: Callable[[V2State], None] | None = None,
        on_transcription: Callable[[str], None] | None = None,
        on_intent: Callable[[ATCIntent], None] | None = None,
        on_response: Callable[[ATCResponse], None] | None = None,
        ptt_start: Callable[[], None] | None = None,
        ptt_stop: Callable[[], None] | None = None,
    ) -> None:
        """Set callbacks for V2 events.

        Args:
            on_state_change: Called when state changes.
            on_transcription: Called with transcribed text.
            on_intent: Called with extracted intent.
            on_response: Called with ATC response.
            ptt_start: Called to play PTT start sound.
            ptt_stop: Called to play PTT stop sound.
        """
        self._on_state_change = on_state_change
        self._on_transcription = on_transcription
        self._on_intent = on_intent
        self._on_response = on_response
        self._ptt_start_callback = ptt_start
        self._ptt_stop_callback = ptt_stop

    def initialize(self) -> bool:
        """Initialize the V2 controller based on settings.

        Returns:
            True if initialization succeeded (at least NLU for text input).
        """
        settings = get_atc_v2_settings()

        if not settings.enabled:
            logger.info("ATC V2 is disabled in settings")
            self._state = V2State.DISABLED
            return False

        voice_input_available = False
        text_input_available = False

        try:
            # Initialize audio recorder (optional - text input still works without it)
            if self._audio_engine:
                fmod_system = self._audio_engine.get_system()
                if fmod_system:
                    self._recorder = AudioRecorder(fmod_system)
                    if self._recorder.initialize(settings.input_device_index):
                        voice_input_available = True
                        logger.info("Audio recorder initialized - voice input available")
                    else:
                        logger.warning("Audio recorder failed - voice input disabled, text input still available")
                        self._recorder = None
                else:
                    logger.warning("FMOD system not available - voice input disabled")
            else:
                logger.warning("Audio engine not set - voice input disabled")

            # Initialize ASR provider (only if voice input available)
            if voice_input_available and settings.asr_provider == PROVIDER_LOCAL:
                self._asr_provider = LocalASRProvider()
                self._asr_provider.initialize(
                    {
                        "model": settings.whisper_model,
                    }
                )
                logger.info("ASR provider initialized")
            elif voice_input_available:
                logger.warning("Remote ASR provider not implemented - voice input disabled")
                voice_input_available = False

            # Initialize NLU provider (required for both voice and text input)
            if settings.nlu_provider == PROVIDER_LOCAL:
                if not settings.llama_model_path:
                    logger.error("Llama model path not configured")
                    return False

                self._nlu_provider = LocalNLUProvider()
                self._nlu_provider.initialize(
                    {
                        "model_path": settings.llama_model_path,
                    }
                )
                text_input_available = True
                logger.info("NLU provider initialized - text input available")
            else:
                logger.warning("Remote NLU provider not implemented")
                return False

            # Initialize intent processor
            self._intent_processor = IntentProcessor(self._atc_handler)

            # Success if at least text input is available
            if text_input_available:
                self._initialized = True
                self._state = V2State.IDLE
                self._set_state(V2State.IDLE)

                if voice_input_available:
                    logger.info("ATC V2 initialized: voice + text input available")
                else:
                    logger.info("ATC V2 initialized: text input only (voice unavailable)")
                return True
            else:
                logger.error("Neither voice nor text input available")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize ATC V2: {e}")
            self._last_error = str(e)
            self._state = V2State.ERROR
            return False

    def shutdown(self) -> None:
        """Shutdown the V2 controller and release resources."""
        with self._lock:
            # Wait for processing to complete
            if self._processing_thread and self._processing_thread.is_alive():
                self._processing_thread.join(timeout=5.0)

            # Shutdown components
            if self._recorder:
                self._recorder.shutdown()
                self._recorder = None

            if self._asr_provider:
                self._asr_provider.shutdown()
                self._asr_provider = None

            if self._nlu_provider:
                self._nlu_provider.shutdown()
                self._nlu_provider = None

            self._initialized = False
            self._state = V2State.DISABLED

        logger.info("ATC V2 controller shutdown")

    def is_enabled(self) -> bool:
        """Check if V2 is enabled and initialized."""
        return self._initialized and self._state != V2State.DISABLED

    def get_state(self) -> V2State:
        """Get current controller state."""
        return self._state

    def get_last_error(self) -> str:
        """Get last error message."""
        return self._last_error

    def on_ptt_pressed(self) -> bool:
        """Handle PTT button press.

        Returns:
            True if recording started.
        """
        with self._lock:
            if not self._initialized:
                return False

            if self._state != V2State.IDLE:
                logger.debug(f"Cannot start recording in state: {self._state}")
                return False

            if not self._recorder:
                return False

            # Play PTT start sound
            if self._ptt_start_callback:
                self._ptt_start_callback()

            # Start recording
            if self._recorder.start_recording():
                self._set_state(V2State.RECORDING)
                logger.info("PTT pressed - recording started")
                return True
            else:
                logger.error("Failed to start recording")
                return False

    def on_ptt_released(self) -> bool:
        """Handle PTT button release.

        Returns:
            True if processing started.
        """
        with self._lock:
            if not self._initialized:
                return False

            if self._state != V2State.RECORDING:
                logger.debug(f"Cannot stop recording in state: {self._state}")
                return False

            if not self._recorder:
                return False

            # Play PTT stop sound
            if self._ptt_stop_callback:
                self._ptt_stop_callback()

            # Stop recording and get audio
            audio_data = self._recorder.stop_recording()

            if not audio_data or len(audio_data) < 1000:  # ~30ms minimum
                logger.warning("Recording too short, ignoring")
                self._set_state(V2State.IDLE)
                return False

            # Store audio for processing
            self._pending_audio = audio_data

            # Start async processing
            self._set_state(V2State.TRANSCRIBING)
            self._processing_thread = threading.Thread(
                target=self._process_audio_async,
                daemon=True,
            )
            self._processing_thread.start()

            logger.info(f"PTT released - processing {len(audio_data)} bytes")
            return True

    def process_text_input(self, text: str) -> bool:
        """Process text input directly (bypasses ASR).

        This allows typed input to be processed by NLU without
        going through speech recognition. Useful for testing
        and accessibility.

        Args:
            text: The text to process (simulated pilot speech).

        Returns:
            True if processing started.
        """
        with self._lock:
            if not self._initialized:
                logger.warning("V2 not initialized for text input")
                return False

            if self._state != V2State.IDLE:
                logger.debug(f"Cannot process text in state: {self._state}")
                return False

            if not text or not text.strip():
                logger.warning("Empty text input")
                return False

            # Start async processing with text (skip ASR)
            self._set_state(V2State.UNDERSTANDING)
            self._processing_thread = threading.Thread(
                target=self._process_text_async,
                args=(text.strip(),),
                daemon=True,
            )
            self._processing_thread.start()

            logger.info(f"Text input - processing: '{text}'")
            return True

    def _process_text_async(self, text: str) -> None:
        """Process text input asynchronously (runs in thread).

        Args:
            text: The text to process.
        """
        try:
            # Notify transcription callback (even though it's typed)
            if self._on_transcription:
                self._on_transcription(text)

            logger.info(f"Text input: '{text}'")

            # Extract intent via NLU
            if not self._nlu_provider or not self._nlu_provider.is_available():
                logger.error("NLU provider not available")
                self._handle_error("Intent recognition not available")
                return

            intent = self._nlu_provider.extract_intent(text)

            if self._on_intent:
                self._on_intent(intent)

            logger.info(f"Intent: {intent.intent_type.value} (confidence={intent.confidence:.2f})")

            # Process intent and generate response
            self._set_state(V2State.RESPONDING)

            if not self._intent_processor:
                self._handle_error("Intent processor not available")
                return

            response = self._intent_processor.process_intent(intent, self._flight_context)

            if response:
                if self._on_response:
                    self._on_response(response)

                # Speak response via TTS
                self._speak_response(response)
            else:
                # No response needed (e.g., acknowledgement)
                self._set_state(V2State.IDLE)

        except Exception as e:
            logger.error(f"Error processing text input: {e}")
            self._handle_error(str(e))

    def _process_audio_async(self) -> None:
        """Process recorded audio asynchronously (runs in thread)."""
        try:
            audio_data = self._pending_audio
            if not audio_data:
                self._set_state(V2State.IDLE)
                return

            # Step 1: Transcribe audio
            if not self._asr_provider or not self._asr_provider.is_available():
                logger.error("ASR provider not available")
                self._handle_error("Speech recognition not available")
                return

            transcription = self._asr_provider.transcribe(audio_data)

            if self._on_transcription:
                self._on_transcription(transcription)

            if not transcription or not transcription.strip():
                logger.warning("Empty transcription")
                self._handle_say_again()
                return

            logger.info(f"Transcription: '{transcription}'")

            # Step 2: Extract intent
            self._set_state(V2State.UNDERSTANDING)

            if not self._nlu_provider or not self._nlu_provider.is_available():
                logger.error("NLU provider not available")
                self._handle_error("Intent recognition not available")
                return

            intent = self._nlu_provider.extract_intent(transcription)

            if self._on_intent:
                self._on_intent(intent)

            logger.info(f"Intent: {intent.intent_type.value} (confidence={intent.confidence:.2f})")

            # Step 3: Process intent and generate response
            self._set_state(V2State.RESPONDING)

            if not self._intent_processor:
                self._handle_error("Intent processor not available")
                return

            response = self._intent_processor.process_intent(intent, self._flight_context)

            if response:
                if self._on_response:
                    self._on_response(response)

                # Step 4: Speak response via TTS
                self._speak_response(response)
            else:
                # No response needed (e.g., acknowledgement)
                self._set_state(V2State.IDLE)

        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            self._handle_error(str(e))

        finally:
            self._pending_audio = None

    def _speak_response(self, response: ATCResponse) -> None:
        """Speak the ATC response via TTS.

        Args:
            response: ATC response to speak.
        """
        if not self._tts_service:
            logger.warning("TTS service not available")
            self._set_state(V2State.IDLE)
            return

        try:
            # Determine voice based on current controller type
            # Could be tower, ground, approach, etc.
            voice = "tower"  # Default to tower voice

            self._tts_service.speak(
                text=response.text,
                voice=voice,
                on_complete=lambda: self._set_state(V2State.IDLE),
            )

        except Exception as e:
            logger.error(f"Failed to speak response: {e}")
            self._set_state(V2State.IDLE)

    def _handle_say_again(self) -> None:
        """Handle case where we need ATC to say 'say again'."""
        self._set_state(V2State.RESPONDING)

        if self._intent_processor:
            response = self._intent_processor._generate_say_again_response(self._flight_context)
            if self._on_response:
                self._on_response(response)
            self._speak_response(response)
        else:
            self._set_state(V2State.IDLE)

    def _handle_error(self, error: str) -> None:
        """Handle processing error.

        Args:
            error: Error message.
        """
        self._last_error = error
        logger.error(f"V2 error: {error}")

        # Still try to say "say again"
        self._handle_say_again()

    def _set_state(self, new_state: V2State) -> None:
        """Set the controller state and notify listeners.

        Args:
            new_state: New state.
        """
        old_state = self._state
        self._state = new_state

        if old_state != new_state:
            logger.debug(f"V2 state: {old_state.name} -> {new_state.name}")
            if self._on_state_change:
                self._on_state_change(new_state)

    def update(self, dt: float) -> None:
        """Update the controller (call every frame).

        Args:
            dt: Delta time in seconds.
        """
        # Currently no per-frame updates needed
        # Could add timeout handling, VU meter updates, etc.
        pass

    def get_recording_level(self) -> float:
        """Get current recording level for VU meter.

        Returns:
            Level from 0.0 to 1.0.
        """
        if self._recorder and self._state == V2State.RECORDING:
            return self._recorder.get_recording_level()
        return 0.0
