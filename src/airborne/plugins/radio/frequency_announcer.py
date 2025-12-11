"""Frequency announcement for audio-only radio interface.

Provides audio feedback for frequency changes, radio operations, and tuning
using the cockpit voice via TTS.

Examples:
    >>> announcer = FrequencyAnnouncer(tts_provider)
    >>> announcer.announce_com1_active(121.5)
    # Speaks: "COM one active one two one decimal five"
"""

from typing import Any

from airborne.plugins.radio.callsign_builder import CallsignBuilder


class FrequencyAnnouncer:
    """Announces radio frequencies and operations via cockpit voice.

    Provides audio feedback for frequency changes in audio-only interface.
    Uses the TTS cache service to generate speech.

    Examples:
        >>> announcer = FrequencyAnnouncer(tts_provider)
        >>> announcer.announce_com1_active(121.5)
        >>> announcer.announce_swap("COM1")
        >>> announcer.announce_tuning_mode("COM1")
    """

    def __init__(self, tts_provider: Any):
        """Initialize frequency announcer.

        Args:
            tts_provider: AudioSpeechProvider instance for speech playback.
        """
        self.tts = tts_provider
        self.builder = CallsignBuilder()

    def announce_com1_active(self, frequency: float) -> None:
        """Announce COM1 active frequency.

        Args:
            frequency: Frequency in MHz (e.g., 121.5)

        Audio output:
            "COM one active one two one decimal five"
        """
        freq_text = self.builder.build_frequency(frequency)
        self._speak(f"COM one active {freq_text}")

    def announce_com2_active(self, frequency: float) -> None:
        """Announce COM2 active frequency.

        Args:
            frequency: Frequency in MHz (e.g., 119.0)

        Audio output:
            "COM two active one one nine decimal zero"
        """
        freq_text = self.builder.build_frequency(frequency)
        self._speak(f"COM two active {freq_text}")

    def announce_com1_standby(self, frequency: float) -> None:
        """Announce COM1 standby frequency.

        Args:
            frequency: Frequency in MHz

        Audio output:
            "COM one standby one one eight decimal three"
        """
        freq_text = self.builder.build_frequency(frequency)
        self._speak(f"COM one standby {freq_text}")

    def announce_com2_standby(self, frequency: float) -> None:
        """Announce COM2 standby frequency.

        Args:
            frequency: Frequency in MHz

        Audio output:
            "COM two standby one two one decimal five"
        """
        freq_text = self.builder.build_frequency(frequency)
        self._speak(f"COM two standby {freq_text}")

    def announce_swap(self, radio: str) -> None:
        """Announce frequency swap.

        Args:
            radio: "COM1" or "COM2"

        Audio output:
            "COM one swapped"
        """
        radio_num = "one" if radio == "COM1" else "two"
        self._speak(f"COM {radio_num} swapped")

    def announce_tuning_mode(self, radio: str, mode: str = "active") -> None:
        """Announce entering tuning mode.

        Args:
            radio: "COM1" or "COM2"
            mode: "active" or "standby"

        Audio output:
            "Tuning COM one active"
        """
        radio_num = "one" if radio == "COM1" else "two"
        self._speak(f"Tuning COM {radio_num} {mode}")

    def announce_frequency_step(self, direction: str = "up") -> None:
        """Announce frequency tuning step (subtle beep).

        Args:
            direction: "up" or "down" (currently unused, could add different beeps)

        Note:
            This could play a short beep sound instead of speech.
            For now, we'll skip audio to avoid clutter.
        """
        # Could add beep sounds here if available
        # For now, silent to avoid too much audio feedback
        pass

    def announce_radio_selected(self, radio: str) -> None:
        """Announce radio selection.

        Args:
            radio: "COM1" or "COM2"

        Audio output:
            "COM one selected"
        """
        radio_num = "one" if radio == "COM1" else "two"
        self._speak(f"COM {radio_num} selected")

    def announce_active_radio(self, radio: str, frequency: float) -> None:
        """Announce active radio and its frequency (short form).

        Args:
            radio: "COM1" or "COM2"
            frequency: Frequency in MHz (e.g., 121.5)

        Audio output:
            "COM one, one two one decimal five"
        """
        radio_num = "one" if radio == "COM1" else "two"
        freq_text = self.builder.build_frequency(frequency)
        self._speak(f"COM {radio_num}, {freq_text}")

    def announce_mhz(self, mhz_part: int) -> None:
        """Announce MHz portion (outer knob value).

        Args:
            mhz_part: Integer MHz value (e.g., 118, 121)

        Audio output:
            "One one eight"
        """
        mhz_text = self.builder.build_callsign(str(mhz_part))
        self._speak(mhz_text)

    def announce_khz(self, khz_part: float) -> None:
        """Announce kHz portion (inner knob value).

        Args:
            khz_part: Decimal kHz value (e.g., 0.75, 0.5)

        Audio output:
            "decimal seven five"
        """
        # Format to 3 decimal places and strip trailing zeros
        khz_str = f"{khz_part:.3f}"[2:].rstrip("0")
        if not khz_str:
            khz_str = "0"

        words = ["decimal"]
        for digit in khz_str:
            if digit in self.builder.DIGIT_WORDS:
                words.append(self.builder.DIGIT_WORDS[digit])

        self._speak(" ".join(words))

    def _speak(self, text: str) -> None:
        """Speak text using TTS.

        Args:
            text: Text to speak
        """
        if self.tts:
            self.tts.speak(text, context="cockpit")
