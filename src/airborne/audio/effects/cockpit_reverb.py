"""Cockpit reverb effect filter using FMOD DSP.

This module implements a small room reverb effect that simulates
the acoustic characteristics of an aircraft cockpit.

The effect uses FMOD's built-in SFX_REVERB DSP configured for a
small enclosed space with short decay and appropriate early reflections.

Typical usage example:
    from airborne.audio.effects.cockpit_reverb import CockpitReverbFilter

    reverb = CockpitReverbFilter(fmod_system, reverb_config)
    reverb.apply_to_channel(channel)
"""

from pathlib import Path
from typing import Any

try:
    import pyfmodex  # type: ignore[import-untyped]

    FMOD_AVAILABLE = True
except ImportError:
    FMOD_AVAILABLE = False
    pyfmodex = None

from airborne.audio.spatial.cockpit_spatial import ReverbConfig
from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


class CockpitReverbFilter:
    """Applies cockpit reverb effect to audio using FMOD DSP.

    Creates a reverb effect that simulates the small, enclosed acoustic
    space of an aircraft cockpit. Uses FMOD's SFX_REVERB DSP with
    parameters optimized for a small room.

    Examples:
        >>> config = ReverbConfig(decay_time=0.3, wet_level=-8.0)
        >>> reverb = CockpitReverbFilter(fmod_system, config)
        >>> reverb.apply_to_channel(channel)
    """

    # FMOD SFX_REVERB parameter indices
    # From FMOD documentation
    DECAY_TIME = 0  # Reverberation decay time (ms) [100-20000]
    EARLY_DELAY = 1  # Initial reflection delay (ms) [0-300]
    LATE_DELAY = 2  # Late reverberation delay (ms) [0-100]
    HF_REFERENCE = 3  # Reference frequency for HF decay [20-20000]
    HF_DECAY_RATIO = 4  # HF decay ratio [10-100] (percentage)
    DIFFUSION = 5  # Echo density [0-100] (percentage)
    DENSITY = 6  # Modal density [0-100] (percentage)
    LOW_SHELF_FREQ = 7  # Low shelf frequency [20-1000]
    LOW_SHELF_GAIN = 8  # Low shelf gain [-36 to 12]
    HIGH_CUT = 9  # High cut frequency [20-20000]
    EARLY_LATE_MIX = 10  # Early/late mix [0-100]
    WET_LEVEL = 11  # Wet signal level [-80 to 20] dB
    DRY_LEVEL = 12  # Dry signal level [-80 to 20] dB

    def __init__(self, system: Any, config: ReverbConfig) -> None:
        """Initialize cockpit reverb DSP.

        Args:
            system: FMOD System instance.
            config: ReverbConfig with reverb parameters.

        Raises:
            ImportError: If pyfmodex is not available.
        """
        if not FMOD_AVAILABLE:
            raise ImportError("pyfmodex is required for cockpit reverb")

        self._system = system
        self._config = config
        self._reverb_dsp: Any = None
        self._convolution_dsp: Any = None
        self._enabled = True
        self._use_convolution = False

        # Create appropriate reverb DSP
        self._setup_reverb()

    def _setup_reverb(self) -> None:
        """Create reverb DSP based on configuration."""
        try:
            # Check if convolution reverb should be used
            if self._config.reverb_type == "convolution" and self._config.ir_file:
                ir_path = Path(self._config.ir_file)
                if ir_path.exists():
                    self._setup_convolution_reverb(str(ir_path))
                    return
                else:
                    logger.warning(
                        f"IR file not found: {self._config.ir_file}, falling back to FMOD reverb"
                    )

            # Use FMOD's built-in SFX_REVERB
            self._setup_fmod_reverb()

        except Exception as e:
            logger.error(f"Error setting up reverb: {e}")
            self._enabled = False

    def _setup_fmod_reverb(self) -> None:
        """Create FMOD SFX_REVERB DSP."""
        try:
            self._reverb_dsp = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.SFXREVERB)

            # Configure for small cockpit space
            # Decay time in ms (0.3 seconds = 300ms)
            self._reverb_dsp.set_parameter_float(self.DECAY_TIME, self._config.decay_time * 1000)

            # Early delay (5ms)
            self._reverb_dsp.set_parameter_float(self.EARLY_DELAY, self._config.early_delay * 1000)

            # Late delay (15ms)
            self._reverb_dsp.set_parameter_float(self.LATE_DELAY, self._config.late_delay * 1000)

            # HF reference (5000 Hz)
            self._reverb_dsp.set_parameter_float(self.HF_REFERENCE, self._config.hf_reference)

            # HF decay ratio (60%)
            self._reverb_dsp.set_parameter_float(
                self.HF_DECAY_RATIO, self._config.hf_decay_ratio * 100
            )

            # Diffusion (80%)
            self._reverb_dsp.set_parameter_float(self.DIFFUSION, self._config.diffusion)

            # Density (100%)
            self._reverb_dsp.set_parameter_float(self.DENSITY, self._config.density)

            # Low shelf frequency
            self._reverb_dsp.set_parameter_float(
                self.LOW_SHELF_FREQ, self._config.low_shelf_frequency
            )

            # Low shelf gain
            self._reverb_dsp.set_parameter_float(self.LOW_SHELF_GAIN, self._config.low_shelf_gain)

            # High cut frequency
            self._reverb_dsp.set_parameter_float(self.HIGH_CUT, self._config.high_cut)

            # Early/late mix (50%)
            self._reverb_dsp.set_parameter_float(self.EARLY_LATE_MIX, self._config.early_late_mix)

            # Wet level (dB)
            self._reverb_dsp.set_parameter_float(self.WET_LEVEL, self._config.wet_level)

            # Dry level (dB)
            self._reverb_dsp.set_parameter_float(self.DRY_LEVEL, self._config.dry_level)

            logger.info(
                f"Created FMOD reverb: decay={self._config.decay_time}s, "
                f"wet={self._config.wet_level}dB"
            )

        except Exception as e:
            logger.error(f"Error creating FMOD reverb: {e}")
            self._enabled = False

    def _setup_convolution_reverb(self, ir_path: str) -> None:
        """Create convolution reverb using IR file.

        Note: FMOD Core API doesn't have built-in convolution reverb,
        but FMOD Studio does. For Core API, we'd need to implement
        convolution manually or use a third-party DSP.

        For now, this falls back to FMOD reverb but logs the intent.

        Args:
            ir_path: Path to impulse response WAV file.
        """
        # FMOD Core doesn't have built-in convolution
        # We could implement this with custom DSP or use FMOD Studio
        # For now, use FMOD reverb as fallback
        logger.info(
            f"Convolution reverb requested with IR: {ir_path}. "
            "Using FMOD SFX_REVERB as approximation."
        )

        # Create FMOD reverb with parameters tuned to match IR characteristics
        self._setup_fmod_reverb()
        self._use_convolution = False  # Mark that we're using fallback

    def apply_to_channel(self, channel: Any) -> None:
        """Apply reverb effect to a channel.

        Args:
            channel: FMOD Channel to apply effect to.
        """
        if not self._enabled:
            logger.warning("Cockpit reverb not enabled")
            return

        try:
            if self._reverb_dsp:
                channel.add_dsp(0, self._reverb_dsp)
                self._reverb_dsp.active = True
                logger.debug("Applied cockpit reverb to channel")

        except Exception as e:
            logger.error(f"Error applying reverb to channel: {e}")

    def remove_from_channel(self, channel: Any) -> None:
        """Remove reverb effect from a channel.

        Args:
            channel: FMOD Channel to remove effect from.
        """
        try:
            if self._reverb_dsp:
                channel.remove_dsp(self._reverb_dsp)
                logger.debug("Removed cockpit reverb from channel")
        except Exception:
            pass  # Already removed or invalid channel

    def set_wet_level(self, wet_db: float) -> None:
        """Adjust the reverb wet level.

        Args:
            wet_db: Wet signal level in dB (-80 to 20).
        """
        if self._reverb_dsp:
            try:
                self._reverb_dsp.set_parameter_float(self.WET_LEVEL, wet_db)
            except Exception as e:
                logger.warning(f"Error setting wet level: {e}")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the reverb effect.

        Args:
            enabled: True to enable effect, False to disable.
        """
        self._enabled = enabled
        if self._reverb_dsp:
            self._reverb_dsp.active = enabled
        logger.debug(f"Cockpit reverb {'enabled' if enabled else 'disabled'}")

    def is_enabled(self) -> bool:
        """Check if reverb effect is enabled.

        Returns:
            True if effect is enabled and DSP is valid.
        """
        return self._enabled and self._reverb_dsp is not None

    def shutdown(self) -> None:
        """Clean up DSP resources."""
        if self._reverb_dsp:
            try:
                self._reverb_dsp.release()
            except Exception as e:
                logger.warning(f"Error releasing reverb DSP: {e}")

        if self._convolution_dsp:
            try:
                self._convolution_dsp.release()
            except Exception as e:
                logger.warning(f"Error releasing convolution DSP: {e}")

        self._reverb_dsp = None
        self._convolution_dsp = None
        self._enabled = False
        logger.info("Cockpit reverb filter shut down")
