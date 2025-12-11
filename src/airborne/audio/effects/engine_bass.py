"""Engine bass boost filter using FMOD DSP.

This module implements a bass boost filter for engine sounds to enhance
the low-frequency rumble and vibration feel of aircraft engines.

The effect consists of:
- Low-shelf EQ boost (adds bass below 200 Hz)
- Optional subtle compression for punch
- Optional low-pass vibration component

Typical usage example:
    from airborne.audio.effects.engine_bass import EngineBassFilter

    bass_filter = EngineBassFilter(fmod_system, config)
    bass_filter.apply_to_channel(channel)
"""

from typing import Any

try:
    import pyfmodex  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    pyfmodex = None

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class EngineBassFilter:
    """Applies bass boost to engine audio using FMOD DSP.

    Enhances the low-frequency content of engine sounds to simulate
    the visceral rumble and vibration of aircraft engines.

    Examples:
        >>> config = {
        ...     "bass_boost_db": 6.0,
        ...     "bass_frequency_hz": 150.0,
        ...     "compression_enabled": True,
        ... }
        >>> bass_filter = EngineBassFilter(fmod_system, config)
        >>> bass_filter.apply_to_channel(channel)
    """

    def __init__(self, system: Any, config: dict[str, Any] | None = None) -> None:
        """Initialize engine bass boost DSP.

        Args:
            system: FMOD System instance.
            config: Bass boost configuration dict with keys:
                - bass_boost_db: Amount of bass boost in dB (default: 6.0)
                - bass_frequency_hz: Center frequency for boost (default: 120.0)
                - compression_enabled: Enable subtle compression (default: True)
                - compression_ratio: Compression ratio (default: 3.0)

        Raises:
            ImportError: If pyfmodex is not available.
        """
        if not FMOD_AVAILABLE:
            raise ImportError("pyfmodex is required for engine bass effects")

        self._system = system
        self._config = config or {}
        self._dsp_chain: list[Any] = []
        self._enabled = True

        # Create DSP chain
        self._setup_dsp_chain()

    def _setup_dsp_chain(self) -> None:
        """Create DSP effects for sub-bass rumble.

        Builds DSP chain:
        1. Low-pass filter (~80Hz) to isolate sub-bass
        2. Gain boost to compensate for filtered content
        """
        try:
            # Use LOWPASS DSP to isolate only sub-bass frequencies
            # This creates a pure "rumble" layer without higher harmonics
            lowpass = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.LOWPASS)

            # Parameters for LOWPASS:
            # 0: Cutoff frequency (Hz), default 5000
            # 1: Resonance (Q), default 1.0

            cutoff_hz = self._config.get("lowpass_cutoff_hz", 80.0)
            resonance = self._config.get("lowpass_resonance", 1.0)

            lowpass.set_parameter_float(0, cutoff_hz)  # Only sub-bass passes through
            lowpass.set_parameter_float(1, resonance)

            self._dsp_chain.append(lowpass)
            logger.debug(f"Added sub-bass lowpass filter: cutoff={cutoff_hz}Hz")

            logger.info(f"Engine sub-bass DSP chain created with {len(self._dsp_chain)} effects")

        except Exception as e:
            logger.error(f"Error setting up engine bass DSP chain: {e}")
            # Clean up any created DSPs
            for dsp in self._dsp_chain:
                try:
                    dsp.release()
                except Exception:
                    pass
            self._dsp_chain.clear()
            self._enabled = False

    def apply_to_channel(self, channel: Any) -> None:
        """Apply bass boost effect to a channel.

        Args:
            channel: FMOD Channel to apply effect to.
        """
        if not self._enabled or not self._dsp_chain:
            return

        try:
            for dsp in self._dsp_chain:
                channel.add_dsp(0, dsp)
                dsp.active = True
            logger.debug(f"Applied engine bass boost ({len(self._dsp_chain)} DSPs)")
        except Exception as e:
            logger.error(f"Error applying engine bass boost: {e}")

    def remove_from_channel(self, channel: Any) -> None:
        """Remove bass boost effect from a channel.

        Args:
            channel: FMOD Channel to remove effect from.
        """
        if not self._dsp_chain:
            return

        try:
            for dsp in self._dsp_chain:
                try:
                    channel.remove_dsp(dsp)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error removing engine bass boost: {e}")

    def shutdown(self) -> None:
        """Release DSP resources."""
        for dsp in self._dsp_chain:
            try:
                dsp.release()
            except Exception as e:
                logger.warning(f"Error releasing engine bass DSP: {e}")
        self._dsp_chain.clear()
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if bass boost is enabled."""
        return self._enabled
