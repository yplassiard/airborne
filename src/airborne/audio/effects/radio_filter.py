"""Radio effect filter using FMOD DSP.

This module implements an aviation radio effect filter that simulates
the characteristic sound of aircraft radio communications (VHF AM).

The effect consists of:
- Bandwidth limiting (300 Hz - 3400 Hz)
- Heavy compression (AGC simulation)
- Optional subtle distortion
- Optional low-level static noise

Typical usage example:
    from airborne.audio.effects.radio_filter import RadioEffectFilter

    radio_filter = RadioEffectFilter(fmod_system, config)
    radio_filter.apply_to_channel(channel)
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


class RadioEffectFilter:
    """Applies aviation radio effect to audio using FMOD DSP chain.

    Creates a chain of DSP effects that simulate the characteristic
    sound of aviation VHF AM radio communications:
    - High-pass filter at 300 Hz (remove low rumble)
    - Low-pass filter at 3400 Hz (AM radio bandwidth limit)
    - Heavy compression (10:1 ratio, simulates AGC)
    - Optional subtle distortion (saturation)
    - Optional white noise (static)

    Examples:
        >>> config = {
        ...     "highpass": {"enabled": True, "cutoff_hz": 300.0},
        ...     "lowpass": {"enabled": True, "cutoff_hz": 3400.0},
        ...     "compressor": {"enabled": True, "ratio": 10.0}
        ... }
        >>> radio_filter = RadioEffectFilter(fmod_system, config)
        >>> radio_filter.apply_to_channel(channel)
    """

    def __init__(self, system: Any, config: dict[str, Any]) -> None:
        """Initialize radio effect DSP chain.

        Args:
            system: FMOD System instance.
            config: Radio effect configuration dict with keys:
                - highpass: {enabled, cutoff_hz}
                - lowpass: {enabled, cutoff_hz}
                - compressor: {enabled, threshold_db, ratio, attack_ms, release_ms}
                - distortion: {enabled, level}
                - static_noise: {enabled, level}

        Raises:
            ImportError: If pyfmodex is not available.
        """
        if not FMOD_AVAILABLE:
            raise ImportError("pyfmodex is required for radio effects")

        self._system = system
        self._config = config
        self._dsp_chain: list[Any] = []
        self._enabled = True

        # Create DSP chain
        self._setup_dsp_chain()

    def _setup_dsp_chain(self) -> None:
        """Create DSP effects based on configuration.

        Builds the DSP chain in the following order:
        1. High-pass filter (remove low frequencies)
        2. Low-pass filter (bandwidth limit)
        3. Compressor (AGC simulation)
        4. Distortion (optional saturation)
        5. Static noise (optional)

        Each effect is only added if enabled in configuration.
        """
        try:
            # High-pass filter (remove low frequencies)
            if self._config.get("highpass", {}).get("enabled", True):
                highpass = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.HIGHPASS)
                cutoff = self._config.get("highpass", {}).get("cutoff_hz", 300.0)
                highpass.set_parameter_float(0, cutoff)  # Cutoff frequency parameter
                self._dsp_chain.append(highpass)
                logger.debug(f"Added high-pass filter at {cutoff} Hz")

            # Low-pass filter (bandwidth limit)
            if self._config.get("lowpass", {}).get("enabled", True):
                lowpass = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.LOWPASS)
                cutoff = self._config.get("lowpass", {}).get("cutoff_hz", 3400.0)
                lowpass.set_parameter_float(0, cutoff)  # Cutoff frequency parameter
                self._dsp_chain.append(lowpass)
                logger.debug(f"Added low-pass filter at {cutoff} Hz")

            # Compressor (AGC simulation)
            if self._config.get("compressor", {}).get("enabled", True):
                compressor = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.COMPRESSOR)
                threshold = self._config.get("compressor", {}).get("threshold_db", -20.0)
                ratio = self._config.get("compressor", {}).get("ratio", 10.0)
                attack = self._config.get("compressor", {}).get("attack_ms", 1.0)
                release = self._config.get("compressor", {}).get("release_ms", 100.0)
                makeup_gain = self._config.get("compressor", {}).get("makeup_gain_db", 6.0)

                compressor.set_parameter_float(0, threshold)  # Threshold
                compressor.set_parameter_float(1, ratio)  # Ratio
                compressor.set_parameter_float(2, attack)  # Attack
                compressor.set_parameter_float(3, release)  # Release
                compressor.set_parameter_float(4, makeup_gain)  # Makeup gain
                self._dsp_chain.append(compressor)
                logger.debug(
                    f"Added compressor: threshold={threshold}dB, ratio={ratio}:1, "
                    f"attack={attack}ms, release={release}ms, gain=+{makeup_gain}dB"
                )

            # Distortion (optional saturation)
            if self._config.get("distortion", {}).get("enabled", False):
                distortion = self._system.create_dsp_by_type(pyfmodex.enums.DSP_TYPE.DISTORTION)
                level = self._config.get("distortion", {}).get("level", 0.2)
                distortion.set_parameter_float(0, level)  # Distortion level
                self._dsp_chain.append(distortion)
                logger.debug(f"Added distortion at level {level}")

            # White noise (static/atmospheric interference)
            if self._config.get("static_noise", {}).get("enabled", False):
                try:
                    # Use oscillator DSP to generate white noise
                    oscillator = self._system.create_dsp_by_type(
                        pyfmodex.enums.DSP_TYPE.OSCILLATOR
                    )
                    # Set to white noise mode (type = 5)
                    oscillator.set_parameter_int(0, 5)  # Type: White noise
                    # Set volume/mix level
                    noise_level = self._config.get("static_noise", {}).get("level", 0.08)
                    oscillator.set_parameter_float(1, noise_level)  # Rate/Volume
                    self._dsp_chain.append(oscillator)
                    logger.debug(f"Added white noise at level {noise_level}")
                except Exception as e:
                    logger.warning(f"Could not add white noise DSP: {e}")

            logger.info(f"Radio effect DSP chain created with {len(self._dsp_chain)} effects")

        except Exception as e:
            logger.error(f"Error setting up DSP chain: {e}")
            # Clean up any created DSPs
            for dsp in self._dsp_chain:
                try:
                    dsp.release()
                except Exception:
                    pass
            self._dsp_chain.clear()
            self._enabled = False

    def apply_to_channel(self, channel: Any) -> None:
        """Apply radio effect to a channel.

        Adds all DSP effects in the chain to the specified channel's
        DSP chain at the head position.

        Args:
            channel: FMOD Channel to apply effect to.

        Note:
            If the DSP chain was not created successfully (e.g., due to
            initialization errors), this method will do nothing.
        """
        if not self._enabled or not self._dsp_chain:
            logger.warning("Radio effect not enabled or DSP chain empty")
            return

        try:
            # Add each DSP to the channel's DSP chain
            for dsp in self._dsp_chain:
                channel.add_dsp(0, dsp)  # Add at head of DSP chain
                dsp.active = True

            logger.debug(f"Applied radio effect to channel ({{len(self._dsp_chain)}} DSPs)")

        except Exception as e:
            logger.error(f"Error applying radio effect to channel: {e}")

    def remove_from_channel(self, channel: Any) -> None:
        """Remove radio effect from a channel.

        Removes all DSP effects from the specified channel.

        Args:
            channel: FMOD Channel to remove effect from.

        Note:
            This method suppresses exceptions if DSPs are already removed.
        """
        for dsp in self._dsp_chain:
            try:
                channel.remove_dsp(dsp)
            except Exception:
                pass  # Already removed or invalid channel

        logger.debug("Removed radio effect from channel")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the radio effect.

        Args:
            enabled: True to enable effect, False to disable.
        """
        self._enabled = enabled
        logger.debug(f"Radio effect {'enabled' if enabled else 'disabled'}")

    def is_enabled(self) -> bool:
        """Check if radio effect is enabled.

        Returns:
            True if effect is enabled and DSP chain is valid.
        """
        return self._enabled and len(self._dsp_chain) > 0

    def shutdown(self) -> None:
        """Clean up DSP resources.

        Releases all DSP effects and clears the chain.
        Should be called when the radio effect is no longer needed.
        """
        for dsp in self._dsp_chain:
            try:
                dsp.release()
            except Exception as e:
                logger.warning(f"Error releasing DSP: {e}")

        self._dsp_chain.clear()
        self._enabled = False
        logger.info("Radio effect filter shut down")
