"""FMOD-based audio recording for voice input.

This module provides microphone recording using FMOD's recording API,
with Push-to-Talk (PTT) support for ATC V2 voice control.

Typical usage:
    recorder = AudioRecorder(fmod_system)
    recorder.initialize()

    # List devices
    devices = recorder.get_recording_devices()

    # PTT recording
    recorder.start_recording()
    # ... user speaks ...
    audio_data = recorder.stop_recording()

    # Process audio_data with ASR
"""

import ctypes
import logging
import struct
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

try:
    import pyfmodex
    from pyfmodex.flags import MODE
    from pyfmodex.structures import CREATESOUNDEXINFO

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    pyfmodex = None  # type: ignore[assignment]
    MODE = None  # type: ignore[assignment,misc]
    CREATESOUNDEXINFO = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Recording parameters
SAMPLE_RATE = 16000  # 16kHz for speech recognition
CHANNELS = 1  # Mono
BITS_PER_SAMPLE = 16
RECORD_BUFFER_SECONDS = 30  # Maximum recording length


class RecordingState(Enum):
    """State of the audio recorder."""

    UNINITIALIZED = "uninitialized"
    READY = "ready"
    RECORDING = "recording"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class RecordingDevice:
    """Information about a recording device.

    Attributes:
        index: Device index for FMOD.
        name: Human-readable device name.
        driver_guid: Device GUID.
        sample_rate: Native sample rate.
        channels: Number of channels.
        is_default: Whether this is the system default.
    """

    index: int
    name: str
    driver_guid: str
    sample_rate: int
    channels: int
    is_default: bool = False


class AudioRecorder:
    """FMOD-based audio recorder with PTT support.

    This class provides microphone recording functionality using FMOD's
    recording API. It supports Push-to-Talk operation for voice control.

    The recorder captures audio at 16kHz mono (optimal for speech recognition)
    and provides raw PCM data for ASR processing.
    """

    def __init__(self, fmod_system: Any = None) -> None:
        """Initialize the audio recorder.

        Args:
            fmod_system: FMOD System instance. If None, will be set later.
        """
        if not FMOD_AVAILABLE:
            raise ImportError("pyfmodex is required for audio recording")

        self._system = fmod_system
        self._state = RecordingState.UNINITIALIZED
        self._record_sound: Any = None
        self._device_index: int = 0
        self._recording_start_time: float = 0.0
        self._lock = threading.Lock()

        # Audio buffer info
        self._buffer_length_samples = SAMPLE_RATE * RECORD_BUFFER_SECONDS
        self._last_record_pos = 0

        # PTT audio cues
        self._ptt_start_sound: Any = None
        self._ptt_stop_sound: Any = None

    def set_fmod_system(self, system: Any) -> None:
        """Set the FMOD system instance.

        Args:
            system: FMOD System instance.
        """
        self._system = system

    def initialize(self, device_index: int | None = None) -> bool:
        """Initialize the recorder with the specified device.

        Args:
            device_index: Recording device index. None for default.

        Returns:
            True if initialization succeeded.
        """
        if not self._system:
            logger.error("FMOD system not set")
            self._state = RecordingState.ERROR
            return False

        try:
            # Get number of recording devices
            # record_num_drivers returns a Structobject with .drivers and .connected
            driver_info = self._system.record_num_drivers
            num_drivers = driver_info.drivers

            if num_drivers == 0:
                logger.warning("No recording devices found")
                self._state = RecordingState.ERROR
                return False

            # Use default device if not specified
            if device_index is None:
                device_index = 0

            if device_index >= num_drivers:
                logger.warning(f"Device index {device_index} out of range (max {num_drivers - 1})")
                device_index = 0

            self._device_index = device_index

            # Create recording sound buffer
            self._create_record_sound()

            self._state = RecordingState.READY
            logger.info(
                f"Audio recorder initialized: device={device_index}, "
                f"rate={SAMPLE_RATE}Hz, channels={CHANNELS}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize audio recorder: {e}")
            self._state = RecordingState.ERROR
            return False

    def _create_record_sound(self) -> None:
        """Create the sound buffer for recording."""
        if not self._system:
            return

        # Set up CREATESOUNDEXINFO for recording
        exinfo = CREATESOUNDEXINFO()
        exinfo.cbsize = ctypes.sizeof(CREATESOUNDEXINFO)
        exinfo.numchannels = CHANNELS
        exinfo.format = pyfmodex.enums.SOUND_FORMAT.PCM16
        exinfo.defaultfrequency = SAMPLE_RATE
        exinfo.length = self._buffer_length_samples * CHANNELS * (BITS_PER_SAMPLE // 8)

        # Create sound for recording
        # OPENUSER = create a user-defined sound
        # LOOP_NORMAL = loop the recording buffer
        mode = MODE.OPENUSER | MODE.LOOP_NORMAL
        self._record_sound = self._system.create_sound(
            name_or_data=None,
            mode=mode,
            exinfo=exinfo,
        )

        logger.debug(
            f"Created recording buffer: {self._buffer_length_samples} samples, "
            f"{RECORD_BUFFER_SECONDS}s max"
        )

    def get_recording_devices(self) -> list[RecordingDevice]:
        """Get list of available recording devices.

        Returns:
            List of RecordingDevice objects.
        """
        devices: list[RecordingDevice] = []

        if not self._system:
            return devices

        try:
            driver_info = self._system.record_num_drivers
            num_drivers = driver_info.drivers

            for i in range(num_drivers):
                info = self._system.get_record_driver_info(i)
                # info is a tuple: (name, guid, systemrate, speakermode, channels, state)
                name = info[0] if len(info) > 0 else f"Device {i}"
                guid = str(info[1]) if len(info) > 1 else ""
                rate = info[2] if len(info) > 2 else SAMPLE_RATE
                channels = info[4] if len(info) > 4 else CHANNELS

                devices.append(
                    RecordingDevice(
                        index=i,
                        name=name,
                        driver_guid=guid,
                        sample_rate=rate,
                        channels=channels,
                        is_default=(i == 0),
                    )
                )

        except Exception as e:
            logger.error(f"Failed to enumerate recording devices: {e}")

        return devices

    def start_recording(self) -> bool:
        """Start recording audio (PTT press).

        Returns:
            True if recording started successfully.
        """
        with self._lock:
            if self._state not in (RecordingState.READY, RecordingState.STOPPED):
                logger.warning(f"Cannot start recording in state: {self._state}")
                return False

            if not self._system or not self._record_sound:
                logger.error("Recorder not initialized")
                return False

            try:
                # Reset position tracking
                self._last_record_pos = 0
                self._recording_start_time = time.time()

                # Start recording to the sound buffer
                self._system.record_start(self._device_index, self._record_sound, loop=True)

                self._state = RecordingState.RECORDING
                logger.info("Recording started")
                return True

            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                self._state = RecordingState.ERROR
                return False

    def stop_recording(self) -> bytes | None:
        """Stop recording and return captured audio (PTT release).

        Returns:
            Raw PCM audio bytes (16-bit signed, mono, 16kHz),
            or None if recording failed.
        """
        with self._lock:
            if self._state != RecordingState.RECORDING:
                logger.warning(f"Cannot stop recording in state: {self._state}")
                return None

            if not self._system or not self._record_sound:
                return None

            try:
                # Get final recording position
                record_pos = self._system.get_record_position(self._device_index)

                # Stop recording
                self._system.record_stop(self._device_index)

                # Calculate how many samples were recorded
                recording_duration = time.time() - self._recording_start_time
                logger.info(f"Recording stopped: {recording_duration:.2f}s")

                # Extract audio data from sound buffer
                audio_data = self._extract_audio_data(record_pos)

                self._state = RecordingState.STOPPED
                return audio_data

            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")
                self._state = RecordingState.ERROR
                return None

    def _extract_audio_data(self, end_position: int) -> bytes:
        """Extract recorded audio data from the sound buffer.

        Args:
            end_position: Recording end position in samples.

        Returns:
            Raw PCM audio bytes.
        """
        if not self._record_sound:
            return b""

        try:
            # Lock the sound buffer for reading
            bytes_per_sample = CHANNELS * (BITS_PER_SAMPLE // 8)
            length_bytes = end_position * bytes_per_sample

            if length_bytes <= 0:
                logger.warning("No audio data recorded")
                return b""

            # Lock and read the buffer
            ptr1, len1, ptr2, len2 = self._record_sound.lock(0, length_bytes)

            # Copy data from the buffer
            audio_data = b""
            if ptr1 and len1 > 0:
                audio_data += ctypes.string_at(ptr1, len1)
            if ptr2 and len2 > 0:
                audio_data += ctypes.string_at(ptr2, len2)

            # Unlock the buffer
            self._record_sound.unlock(ptr1, ptr2, len1, len2)

            logger.debug(f"Extracted {len(audio_data)} bytes of audio data")
            return audio_data

        except Exception as e:
            logger.error(f"Failed to extract audio data: {e}")
            return b""

    def is_recording(self) -> bool:
        """Check if currently recording.

        Returns:
            True if recording is in progress.
        """
        return self._state == RecordingState.RECORDING

    def get_state(self) -> RecordingState:
        """Get current recorder state.

        Returns:
            Current RecordingState.
        """
        return self._state

    def get_recording_level(self) -> float:
        """Get current recording level (for VU meter display).

        Returns:
            RMS level from 0.0 to 1.0, or 0.0 if not recording.
        """
        if self._state != RecordingState.RECORDING:
            return 0.0

        if not self._system or not self._record_sound:
            return 0.0

        try:
            # Get current recording position
            record_pos = self._system.get_record_position(self._device_index)

            # Read a small window of recent samples for level calculation
            window_samples = min(1024, record_pos)
            if window_samples <= 0:
                return 0.0

            bytes_per_sample = CHANNELS * (BITS_PER_SAMPLE // 8)
            start_pos = max(0, record_pos - window_samples)
            length_bytes = window_samples * bytes_per_sample

            # Lock and read
            ptr1, len1, ptr2, len2 = self._record_sound.lock(
                start_pos * bytes_per_sample, length_bytes
            )

            # Calculate RMS
            rms = 0.0
            sample_count = 0

            if ptr1 and len1 > 0:
                data = ctypes.string_at(ptr1, len1)
                samples = struct.unpack(f"<{len(data) // 2}h", data)
                for sample in samples:
                    rms += sample * sample
                    sample_count += 1

            self._record_sound.unlock(ptr1, ptr2, len1, len2)

            if sample_count > 0:
                rms = (rms / sample_count) ** 0.5 / 32768.0
                return min(1.0, rms)

            return 0.0

        except Exception:
            return 0.0

    def shutdown(self) -> None:
        """Release recorder resources."""
        with self._lock:
            if self._state == RecordingState.RECORDING:
                try:
                    self._system.record_stop(self._device_index)
                except Exception:
                    pass

            if self._record_sound:
                try:
                    self._record_sound.release()
                except Exception:
                    pass
                self._record_sound = None

            self._state = RecordingState.UNINITIALIZED
            logger.info("Audio recorder shutdown")

    @staticmethod
    def convert_to_wav(pcm_data: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
        """Convert raw PCM to WAV format.

        Args:
            pcm_data: Raw PCM audio (16-bit signed, mono).
            sample_rate: Sample rate in Hz.

        Returns:
            WAV file bytes.
        """
        channels = CHANNELS
        bits_per_sample = BITS_PER_SAMPLE
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        data_size = len(pcm_data)
        file_size = 36 + data_size

        # Build WAV header
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            file_size,
            b"WAVE",
            b"fmt ",
            16,  # Subchunk1Size
            1,  # AudioFormat (PCM)
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )

        return header + pcm_data
