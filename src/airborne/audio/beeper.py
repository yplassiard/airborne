"""Beep generator for proximity audio cues.

Generates actual beep sounds for proximity-based spatial awareness.
Integrates with the audio engine to play beeps at calculated frequencies.

Typical usage:
    from airborne.audio.beeper import BeepGenerator, BeepStyle

    beeper = BeepGenerator()
    beeper.generate_beep(frequency_hz=440, duration_s=0.1, style=BeepStyle.SINE)
"""

import logging
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class BeepStyle(Enum):
    """Beep sound style/waveform."""

    SINE = "sine"  # Smooth sine wave
    SQUARE = "square"  # Square wave (harsher sound)
    TRIANGLE = "triangle"  # Triangle wave (softer than square)
    SAWTOOTH = "sawtooth"  # Sawtooth wave
    CHIRP = "chirp"  # Frequency sweep (chirp sound)


class BeepGenerator:
    """Generates beep sounds for proximity cues.

    Creates audio waveforms for beeping proximity cues. Supports multiple
    waveform types and can generate beeps with various pitches and durations.

    Examples:
        >>> beeper = BeepGenerator(sample_rate=44100)
        >>> samples = beeper.generate_beep(frequency_hz=1000, duration_s=0.1)
        >>> print(f"Generated {len(samples)} samples")
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        """Initialize beep generator.

        Args:
            sample_rate: Audio sample rate in Hz (default 44100)
        """
        self.sample_rate = sample_rate
        logger.debug("BeepGenerator initialized with sample rate: %d Hz", sample_rate)

    def generate_beep(
        self,
        frequency_hz: float = 1000.0,
        duration_s: float = 0.1,
        style: BeepStyle = BeepStyle.SINE,
        amplitude: float = 0.3,
        fade_in_s: float = 0.01,
        fade_out_s: float = 0.01,
    ) -> np.ndarray:
        """Generate a beep sound.

        Args:
            frequency_hz: Beep frequency in Hz (pitch)
            duration_s: Beep duration in seconds
            style: Waveform style (SINE, SQUARE, etc.)
            amplitude: Volume (0.0 to 1.0)
            fade_in_s: Fade-in duration in seconds (to avoid clicks)
            fade_out_s: Fade-out duration in seconds

        Returns:
            Audio samples as numpy array (float32, range -1.0 to 1.0)

        Examples:
            >>> beeper = BeepGenerator()
            >>> beep = beeper.generate_beep(1000, 0.1, BeepStyle.SINE)
            >>> beep = beeper.generate_beep(2000, 0.05, BeepStyle.CHIRP)
        """
        num_samples = int(self.sample_rate * duration_s)
        t = np.linspace(0, duration_s, num_samples, dtype=np.float32)

        # Generate waveform based on style
        if style == BeepStyle.SINE:
            samples = self._generate_sine(t, frequency_hz)
        elif style == BeepStyle.SQUARE:
            samples = self._generate_square(t, frequency_hz)
        elif style == BeepStyle.TRIANGLE:
            samples = self._generate_triangle(t, frequency_hz)
        elif style == BeepStyle.SAWTOOTH:
            samples = self._generate_sawtooth(t, frequency_hz)
        elif style == BeepStyle.CHIRP:
            samples = self._generate_chirp(t, frequency_hz)
        else:
            samples = self._generate_sine(t, frequency_hz)  # Default to sine

        # Apply amplitude
        samples *= amplitude

        # Apply fade-in and fade-out to prevent clicks
        samples = self._apply_fade(samples, fade_in_s, fade_out_s, duration_s)

        return samples

    def generate_proximity_beep(
        self,
        distance_m: float,
        min_distance_m: float = 10.0,
        max_distance_m: float = 500.0,
        base_frequency_hz: float = 800.0,
        max_frequency_hz: float = 1200.0,
        duration_s: float = 0.08,
        style: BeepStyle = BeepStyle.SINE,
    ) -> np.ndarray:
        """Generate a proximity beep based on distance.

        Automatically adjusts beep frequency based on distance.
        Closer distances = higher pitch.

        Args:
            distance_m: Distance to target in meters
            min_distance_m: Minimum distance (m)
            max_distance_m: Maximum distance (m)
            base_frequency_hz: Base frequency at max distance (Hz)
            max_frequency_hz: Max frequency at min distance (Hz)
            duration_s: Beep duration in seconds
            style: Waveform style

        Returns:
            Audio samples as numpy array

        Examples:
            >>> beeper = BeepGenerator()
            >>> beep_far = beeper.generate_proximity_beep(distance_m=300)
            >>> beep_close = beeper.generate_proximity_beep(distance_m=50)
        """
        # Normalize distance to 0-1 range (1 = closest)
        distance_range = max_distance_m - min_distance_m
        if distance_range <= 0:
            normalized = 1.0
        else:
            normalized = (
                1.0
                - (max(min_distance_m, min(distance_m, max_distance_m)) - min_distance_m)
                / distance_range
            )

        # Map to frequency range
        frequency = base_frequency_hz + (normalized * (max_frequency_hz - base_frequency_hz))

        return self.generate_beep(frequency_hz=frequency, duration_s=duration_s, style=style)

    def _generate_sine(self, t: np.ndarray, frequency_hz: float) -> np.ndarray:
        """Generate sine wave.

        Args:
            t: Time array
            frequency_hz: Frequency in Hz

        Returns:
            Sine wave samples
        """
        return np.sin(2 * np.pi * frequency_hz * t).astype(np.float32)

    def _generate_square(self, t: np.ndarray, frequency_hz: float) -> np.ndarray:
        """Generate square wave.

        Args:
            t: Time array
            frequency_hz: Frequency in Hz

        Returns:
            Square wave samples
        """
        return np.sign(np.sin(2 * np.pi * frequency_hz * t)).astype(np.float32)

    def _generate_triangle(self, t: np.ndarray, frequency_hz: float) -> np.ndarray:
        """Generate triangle wave.

        Args:
            t: Time array
            frequency_hz: Frequency in Hz

        Returns:
            Triangle wave samples
        """
        # Triangle wave using arcsin(sin(x))
        return (2 / np.pi * np.arcsin(np.sin(2 * np.pi * frequency_hz * t))).astype(np.float32)

    def _generate_sawtooth(self, t: np.ndarray, frequency_hz: float) -> np.ndarray:
        """Generate sawtooth wave.

        Args:
            t: Time array
            frequency_hz: Frequency in Hz

        Returns:
            Sawtooth wave samples
        """
        # Sawtooth wave: 2*(t*f - floor(t*f + 0.5))
        phase = frequency_hz * t
        return (2 * (phase - np.floor(phase + 0.5))).astype(np.float32)

    def _generate_chirp(self, t: np.ndarray, base_frequency_hz: float) -> np.ndarray:
        """Generate chirp (frequency sweep).

        Args:
            t: Time array
            base_frequency_hz: Starting frequency in Hz

        Returns:
            Chirp wave samples
        """
        # Sweep from base frequency to 1.5x base frequency
        end_frequency_hz = base_frequency_hz * 1.5
        frequency_sweep = base_frequency_hz + (end_frequency_hz - base_frequency_hz) * (t / t[-1])

        # Instantaneous phase
        phase = 2 * np.pi * np.cumsum(frequency_sweep) / self.sample_rate

        return np.sin(phase).astype(np.float32)

    def _apply_fade(
        self,
        samples: np.ndarray,
        fade_in_s: float,
        fade_out_s: float,
        total_duration_s: float,
    ) -> np.ndarray:
        """Apply fade-in and fade-out to prevent clicks.

        Args:
            samples: Audio samples
            fade_in_s: Fade-in duration in seconds
            fade_out_s: Fade-out duration in seconds
            total_duration_s: Total audio duration in seconds

        Returns:
            Samples with fade applied
        """
        num_samples = len(samples)

        # Calculate fade sample counts
        fade_in_samples = int(self.sample_rate * fade_in_s)
        fade_out_samples = int(self.sample_rate * fade_out_s)

        # Clamp to valid range
        fade_in_samples = min(fade_in_samples, num_samples // 2)
        fade_out_samples = min(fade_out_samples, num_samples // 2)

        # Apply fade-in (linear ramp)
        if fade_in_samples > 0:
            fade_in_curve = np.linspace(0, 1, fade_in_samples, dtype=np.float32)
            samples[:fade_in_samples] *= fade_in_curve

        # Apply fade-out (linear ramp)
        if fade_out_samples > 0:
            fade_out_curve = np.linspace(1, 0, fade_out_samples, dtype=np.float32)
            samples[-fade_out_samples:] *= fade_out_curve

        return samples


class ProximityBeeper:
    """High-level beeping manager for proximity cues.

    Combines BeepGenerator with timing logic to manage beeping behavior.
    Handles beep intervals and generates appropriate sounds.

    Examples:
        >>> beeper = ProximityBeeper()
        >>> samples = beeper.get_beep_if_ready(
        ...     distance_m=100,
        ...     beep_frequency_hz=2.0,
        ...     delta_time=0.5
        ... )
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        """Initialize proximity beeper.

        Args:
            sample_rate: Audio sample rate in Hz
        """
        self.generator = BeepGenerator(sample_rate=sample_rate)
        self.last_beep_time = 0.0
        logger.debug("ProximityBeeper initialized")

    def get_beep_if_ready(
        self,
        distance_m: float,
        beep_frequency_hz: float,
        delta_time: float,
        style: BeepStyle = BeepStyle.SINE,
    ) -> np.ndarray | None:
        """Get a beep sound if it's time to beep.

        Args:
            distance_m: Current distance to target (m)
            beep_frequency_hz: Beep rate in Hz (beeps per second)
            delta_time: Time since last update (seconds)
            style: Waveform style

        Returns:
            Audio samples if beep should play, None otherwise

        Examples:
            >>> beeper = ProximityBeeper()
            >>> samples = beeper.get_beep_if_ready(100, 2.0, 0.5, BeepStyle.SINE)
            >>> if samples is not None:
            ...     play_audio(samples)
        """
        if beep_frequency_hz <= 0:
            return None

        beep_interval = 1.0 / beep_frequency_hz
        self.last_beep_time += delta_time

        if self.last_beep_time >= beep_interval:
            self.last_beep_time = 0.0
            return self.generator.generate_proximity_beep(
                distance_m=distance_m, duration_s=0.08, style=style
            )

        return None

    def reset_timing(self) -> None:
        """Reset beep timing.

        Examples:
            >>> beeper.reset_timing()
        """
        self.last_beep_time = 0.0
