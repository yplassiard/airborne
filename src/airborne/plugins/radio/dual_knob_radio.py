"""Dual-knob radio system (traditional King KX-155 style).

This radio system mimics traditional dual-knob radios found in:
- Cessna 172 (pre-G1000)
- Piper Cherokee
- Most GA aircraft with King, Narco, or Bendix radios

Interface:
- Outer knob: Changes MHz portion (118-136 MHz)
- Inner knob: Changes kHz portion (.000-.975 in .025 steps)
- Flip-flop: Swaps active/standby

Keyboard mapping:
- D: Announce outer knob (MHz)
- Shift+D: Increase MHz
- Ctrl+D: Decrease MHz
- F: Announce inner knob (kHz)
- Shift+F: Increase kHz (.025 steps)
- Ctrl+F: Decrease kHz (.025 steps)
- S: Announce full frequency ("COM one: one one eight decimal seven five")
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.plugins.radio.frequency_announcer import FrequencyAnnouncer
from airborne.plugins.radio.frequency_manager import FrequencyManager
from airborne.plugins.radio.radio_system import RadioSystem, RadioSystemFactory

logger = get_logger(__name__)


class DualKnobRadioSystem(RadioSystem):
    """Dual-knob radio tuning system.

    Simulates traditional dual-knob radios with separate controls for
    MHz (outer knob) and kHz (inner knob) portions of the frequency.

    Examples:
        >>> system = DualKnobRadioSystem(freq_manager, announcer)
        >>> system.handle_input("outer_knob_increase")  # 118 → 119
        >>> system.handle_input("inner_knob_increase")  # .000 → .025
        >>> system.handle_input("announce_frequency")   # "COM one: one one nine decimal zero two five"
    """

    # COM radio frequency range
    MIN_MHZ = 118
    MAX_MHZ = 136
    KHZ_STEP = 0.025  # 25 kHz steps

    def __init__(
        self,
        frequency_manager: FrequencyManager,
        frequency_announcer: FrequencyAnnouncer | None = None,
        sound_manager: Any = None,
    ):
        """Initialize dual-knob radio system.

        Args:
            frequency_manager: Frequency manager for tuning operations.
            frequency_announcer: Announcer for audio feedback (optional).
            sound_manager: Sound manager for knob click sounds (optional).
        """
        super().__init__(frequency_manager, frequency_announcer, sound_manager)

    def get_input_actions(self) -> list[str]:
        """Get list of supported input actions.

        Returns:
            List of action names for dual-knob system.
        """
        return [
            "outer_knob_increase",  # Shift+D
            "outer_knob_decrease",  # Ctrl+D
            "outer_knob_read",  # D
            "inner_knob_increase",  # Shift+F
            "inner_knob_decrease",  # Ctrl+F
            "inner_knob_read",  # F
            "announce_frequency",  # S
        ]

    def handle_input(self, action: str, data: dict[str, Any] | None = None) -> bool:
        """Handle input action for dual-knob radio.

        Args:
            action: Input action name.
            data: Optional action data.

        Returns:
            True if action was handled, False otherwise.
        """
        if action == "outer_knob_increase":
            self._adjust_mhz(1)
            return True
        elif action == "outer_knob_decrease":
            self._adjust_mhz(-1)
            return True
        elif action == "outer_knob_read":
            self._announce_mhz()
            return True
        elif action == "inner_knob_increase":
            self._adjust_khz(1)
            return True
        elif action == "inner_knob_decrease":
            self._adjust_khz(-1)
            return True
        elif action == "inner_knob_read":
            self._announce_khz()
            return True
        elif action == "announce_frequency":
            self._announce_full_frequency()
            return True

        return False

    def _adjust_mhz(self, direction: int) -> None:
        """Adjust MHz portion of frequency (outer knob).

        Args:
            direction: +1 to increase, -1 to decrease.
        """
        # Get current frequency
        current = self.frequency_manager.get_active(self.selected_radio)

        # Split into MHz and kHz
        mhz_part = int(current)
        khz_part = current - mhz_part

        # Adjust MHz with wrapping
        new_mhz = mhz_part + direction
        if new_mhz > self.MAX_MHZ:
            new_mhz = self.MIN_MHZ
        elif new_mhz < self.MIN_MHZ:
            new_mhz = self.MAX_MHZ

        # Reconstruct frequency
        new_freq = new_mhz + khz_part

        # Set frequency
        self.frequency_manager.set_active(self.selected_radio, new_freq)

        # Play knob click sound
        if self.sound_manager:
            self.sound_manager.play_knob_sound()

        # Announce new MHz
        self._announce_mhz()

        logger.info("%s outer knob: %.3f → %.3f MHz", self.selected_radio, current, new_freq)

    def _adjust_khz(self, direction: int) -> None:
        """Adjust kHz portion of frequency (inner knob).

        Args:
            direction: +1 to increase, -1 to decrease.
        """
        # Get current frequency
        current = self.frequency_manager.get_active(self.selected_radio)

        # Adjust by 25 kHz steps
        new_freq = current + (direction * self.KHZ_STEP)

        # Keep within valid range
        mhz_part = int(new_freq)
        if mhz_part < self.MIN_MHZ or mhz_part > self.MAX_MHZ:
            # Wrapped around - adjust MHz portion
            if direction > 0:
                new_freq = self.MIN_MHZ + (new_freq - mhz_part)
            else:
                new_freq = self.MAX_MHZ + (new_freq - mhz_part)

        # Round to nearest .025
        new_freq = round(new_freq / self.KHZ_STEP) * self.KHZ_STEP

        # Set frequency
        self.frequency_manager.set_active(self.selected_radio, new_freq)

        # Play knob click sound
        if self.sound_manager:
            self.sound_manager.play_knob_sound()

        # Announce new kHz
        self._announce_khz()

        logger.info("%s inner knob: %.3f → %.3f MHz", self.selected_radio, current, new_freq)

    def _announce_mhz(self) -> None:
        """Announce MHz portion (outer knob value)."""
        if not self.frequency_announcer:
            return

        freq = self.frequency_manager.get_active(self.selected_radio)
        mhz_part = int(freq)

        self.frequency_announcer.announce_mhz(mhz_part)
        logger.debug("%s MHz: %d", self.selected_radio, mhz_part)

    def _announce_khz(self) -> None:
        """Announce kHz portion (inner knob value)."""
        if not self.frequency_announcer:
            return

        freq = self.frequency_manager.get_active(self.selected_radio)
        mhz_part = int(freq)
        khz_part = freq - mhz_part

        self.frequency_announcer.announce_khz(khz_part)
        logger.debug("%s kHz: %.3f", self.selected_radio, khz_part)

    def _announce_full_frequency(self) -> None:
        """Announce full frequency with radio number."""
        if not self.frequency_announcer:
            return

        freq = self.frequency_manager.get_active(self.selected_radio)

        # Use the existing announce_active_radio method
        self.frequency_announcer.announce_active_radio(self.selected_radio, freq)

        logger.debug("%s full frequency: %.3f MHz", self.selected_radio, freq)


# Register this system
RadioSystemFactory.register("dual_knob", DualKnobRadioSystem)
