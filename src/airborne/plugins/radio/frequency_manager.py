"""Frequency Manager for radio communications.

Manages COM and NAV radio frequencies with active/standby functionality.
"""

from dataclasses import dataclass
from typing import Literal

RadioType = Literal["COM1", "COM2", "NAV1", "NAV2"]


@dataclass
class RadioFrequencies:
    """Stores active and standby frequencies for a radio.

    Attributes:
        active: Currently tuned frequency in MHz
        standby: Standby frequency in MHz
    """

    active: float = 118.0  # Default to Tower frequency
    standby: float = 118.0


class FrequencyManager:
    """Manages radio frequencies for COM and NAV radios.

    Handles frequency tuning, storage, and swapping between active/standby.
    Aviation frequencies:
    - COM: 118.0 - 136.975 MHz (25 kHz spacing)
    - NAV: 108.0 - 117.95 MHz (50 kHz spacing for VOR/ILS)
    """

    def __init__(self) -> None:
        """Initialize frequency manager with default frequencies."""
        self.radios: dict[RadioType, RadioFrequencies] = {
            "COM1": RadioFrequencies(active=118.0, standby=121.5),
            "COM2": RadioFrequencies(active=119.0, standby=121.5),
            "NAV1": RadioFrequencies(active=110.0, standby=108.0),
            "NAV2": RadioFrequencies(active=110.0, standby=108.0),
        }

    def set_active(self, radio: RadioType, frequency: float) -> bool:
        """Set active frequency for a radio.

        Args:
            radio: Radio identifier (COM1, COM2, NAV1, NAV2)
            frequency: Frequency in MHz

        Returns:
            True if frequency was set successfully, False if invalid

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.set_active("COM1", 121.5)
            True
            >>> manager.get_active("COM1")
            121.5
        """
        if not self._validate_frequency(radio, frequency):
            return False

        self.radios[radio].active = frequency
        return True

    def set_standby(self, radio: RadioType, frequency: float) -> bool:
        """Set standby frequency for a radio.

        Args:
            radio: Radio identifier (COM1, COM2, NAV1, NAV2)
            frequency: Frequency in MHz

        Returns:
            True if frequency was set successfully, False if invalid

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.set_standby("COM1", 119.7)
            True
            >>> manager.get_standby("COM1")
            119.7
        """
        if not self._validate_frequency(radio, frequency):
            return False

        self.radios[radio].standby = frequency
        return True

    def swap(self, radio: RadioType) -> None:
        """Swap active and standby frequencies.

        Args:
            radio: Radio identifier (COM1, COM2, NAV1, NAV2)

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.set_active("COM1", 118.0)
            True
            >>> manager.set_standby("COM1", 121.5)
            True
            >>> manager.swap("COM1")
            >>> manager.get_active("COM1")
            121.5
            >>> manager.get_standby("COM1")
            118.0
        """
        radio_freq = self.radios[radio]
        radio_freq.active, radio_freq.standby = radio_freq.standby, radio_freq.active

    def get_active(self, radio: RadioType) -> float:
        """Get active frequency for a radio.

        Args:
            radio: Radio identifier (COM1, COM2, NAV1, NAV2)

        Returns:
            Active frequency in MHz

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.get_active("COM1")
            118.0
        """
        return self.radios[radio].active

    def get_standby(self, radio: RadioType) -> float:
        """Get standby frequency for a radio.

        Args:
            radio: Radio identifier (COM1, COM2, NAV1, NAV2)

        Returns:
            Standby frequency in MHz

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.get_standby("COM1")
            121.5
        """
        return self.radios[radio].standby

    def increment_frequency(
        self, radio: RadioType, which: Literal["active", "standby"], amount: float = 0.025
    ) -> bool:
        """Increment a frequency by specified amount.

        Args:
            radio: Radio identifier
            which: Which frequency to increment ("active" or "standby")
            amount: Amount to increment in MHz (default 0.025 = 25 kHz)

        Returns:
            True if incremented successfully

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.increment_frequency("COM1", "active", 0.025)
            True
            >>> manager.get_active("COM1")
            118.025
        """
        current = self.get_active(radio) if which == "active" else self.get_standby(radio)
        new_freq = round(current + amount, 3)  # Round to 3 decimal places

        if which == "active":
            return self.set_active(radio, new_freq)
        return self.set_standby(radio, new_freq)

    def decrement_frequency(
        self, radio: RadioType, which: Literal["active", "standby"], amount: float = 0.025
    ) -> bool:
        """Decrement a frequency by specified amount.

        Args:
            radio: Radio identifier
            which: Which frequency to decrement ("active" or "standby")
            amount: Amount to decrement in MHz (default 0.025 = 25 kHz)

        Returns:
            True if decremented successfully

        Examples:
            >>> manager = FrequencyManager()
            >>> manager.decrement_frequency("COM1", "active", 0.025)
            True
            >>> manager.get_active("COM1")
            117.975
        """
        current = self.get_active(radio) if which == "active" else self.get_standby(radio)
        new_freq = round(current - amount, 3)  # Round to 3 decimal places

        if which == "active":
            return self.set_active(radio, new_freq)
        return self.set_standby(radio, new_freq)

    def _validate_frequency(self, radio: RadioType, frequency: float) -> bool:
        """Validate frequency is within valid range for radio type.

        Args:
            radio: Radio identifier
            frequency: Frequency to validate in MHz

        Returns:
            True if frequency is valid for the radio type
        """
        if radio in ("COM1", "COM2"):
            # COM radios: 118.0 - 136.975 MHz
            return 118.0 <= frequency <= 136.975
        # NAV radios: 108.0 - 117.95 MHz
        return 108.0 <= frequency <= 117.95

    def get_all_frequencies(self) -> dict[RadioType, dict[str, float]]:
        """Get all frequencies for all radios.

        Returns:
            Dictionary mapping radio types to their active/standby frequencies

        Examples:
            >>> manager = FrequencyManager()
            >>> freqs = manager.get_all_frequencies()
            >>> freqs["COM1"]["active"]
            118.0
        """
        return {
            radio: {"active": freq.active, "standby": freq.standby}
            for radio, freq in self.radios.items()
        }
