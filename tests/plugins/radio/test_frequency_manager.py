"""Tests for radio frequency manager."""

from airborne.plugins.radio.frequency_manager import FrequencyManager


class TestFrequencyManagerInit:
    """Test FrequencyManager initialization."""

    def test_init_default_frequencies(self) -> None:
        """Test manager initializes with default frequencies."""
        manager = FrequencyManager()

        assert manager.get_active("COM1") == 118.0
        assert manager.get_standby("COM1") == 121.5
        assert manager.get_active("COM2") == 119.0
        assert manager.get_standby("COM2") == 121.5
        assert manager.get_active("NAV1") == 110.0
        assert manager.get_standby("NAV1") == 108.0
        assert manager.get_active("NAV2") == 110.0
        assert manager.get_standby("NAV2") == 108.0


class TestFrequencyManagerSetActive:
    """Test setting active frequencies."""

    def test_set_active_com_valid(self) -> None:
        """Test setting valid COM active frequency."""
        manager = FrequencyManager()
        assert manager.set_active("COM1", 121.5) is True
        assert manager.get_active("COM1") == 121.5

    def test_set_active_nav_valid(self) -> None:
        """Test setting valid NAV active frequency."""
        manager = FrequencyManager()
        assert manager.set_active("NAV1", 115.3) is True
        assert manager.get_active("NAV1") == 115.3

    def test_set_active_com_below_range(self) -> None:
        """Test setting COM frequency below valid range."""
        manager = FrequencyManager()
        assert manager.set_active("COM1", 117.0) is False
        assert manager.get_active("COM1") == 118.0  # Unchanged

    def test_set_active_com_above_range(self) -> None:
        """Test setting COM frequency above valid range."""
        manager = FrequencyManager()
        assert manager.set_active("COM1", 137.0) is False
        assert manager.get_active("COM1") == 118.0  # Unchanged

    def test_set_active_nav_below_range(self) -> None:
        """Test setting NAV frequency below valid range."""
        manager = FrequencyManager()
        assert manager.set_active("NAV1", 107.0) is False
        assert manager.get_active("NAV1") == 110.0  # Unchanged

    def test_set_active_nav_above_range(self) -> None:
        """Test setting NAV frequency above valid range."""
        manager = FrequencyManager()
        assert manager.set_active("NAV1", 118.0) is False
        assert manager.get_active("NAV1") == 110.0  # Unchanged


class TestFrequencyManagerSetStandby:
    """Test setting standby frequencies."""

    def test_set_standby_com_valid(self) -> None:
        """Test setting valid COM standby frequency."""
        manager = FrequencyManager()
        assert manager.set_standby("COM1", 119.7) is True
        assert manager.get_standby("COM1") == 119.7

    def test_set_standby_nav_valid(self) -> None:
        """Test setting valid NAV standby frequency."""
        manager = FrequencyManager()
        assert manager.set_standby("NAV1", 112.5) is True
        assert manager.get_standby("NAV1") == 112.5

    def test_set_standby_invalid(self) -> None:
        """Test setting invalid standby frequency."""
        manager = FrequencyManager()
        original = manager.get_standby("COM1")
        assert manager.set_standby("COM1", 140.0) is False
        assert manager.get_standby("COM1") == original  # Unchanged


class TestFrequencyManagerSwap:
    """Test swapping active/standby frequencies."""

    def test_swap_com(self) -> None:
        """Test swapping COM frequencies."""
        manager = FrequencyManager()
        manager.set_active("COM1", 118.0)
        manager.set_standby("COM1", 121.5)

        manager.swap("COM1")

        assert manager.get_active("COM1") == 121.5
        assert manager.get_standby("COM1") == 118.0

    def test_swap_nav(self) -> None:
        """Test swapping NAV frequencies."""
        manager = FrequencyManager()
        manager.set_active("NAV1", 110.0)
        manager.set_standby("NAV1", 115.3)

        manager.swap("NAV1")

        assert manager.get_active("NAV1") == 115.3
        assert manager.get_standby("NAV1") == 110.0

    def test_swap_multiple_times(self) -> None:
        """Test swapping back and forth."""
        manager = FrequencyManager()
        manager.set_active("COM1", 118.0)
        manager.set_standby("COM1", 121.5)

        manager.swap("COM1")
        manager.swap("COM1")

        assert manager.get_active("COM1") == 118.0
        assert manager.get_standby("COM1") == 121.5


class TestFrequencyManagerIncrement:
    """Test incrementing frequencies."""

    def test_increment_active_default_step(self) -> None:
        """Test incrementing active with default step (25 kHz)."""
        manager = FrequencyManager()
        manager.set_active("COM1", 118.0)

        assert manager.increment_frequency("COM1", "active") is True
        assert manager.get_active("COM1") == 118.025

    def test_increment_standby_custom_step(self) -> None:
        """Test incrementing standby with custom step."""
        manager = FrequencyManager()
        manager.set_standby("COM1", 121.0)

        assert manager.increment_frequency("COM1", "standby", 0.1) is True
        assert manager.get_standby("COM1") == 121.1

    def test_increment_beyond_range(self) -> None:
        """Test incrementing beyond valid range."""
        manager = FrequencyManager()
        manager.set_active("COM1", 136.975)

        assert manager.increment_frequency("COM1", "active", 0.025) is False
        assert manager.get_active("COM1") == 136.975  # Unchanged


class TestFrequencyManagerDecrement:
    """Test decrementing frequencies."""

    def test_decrement_active_default_step(self) -> None:
        """Test decrementing active with default step (25 kHz)."""
        manager = FrequencyManager()
        manager.set_active("COM1", 118.025)

        assert manager.decrement_frequency("COM1", "active") is True
        assert manager.get_active("COM1") == 118.0

    def test_decrement_standby_custom_step(self) -> None:
        """Test decrementing standby with custom step."""
        manager = FrequencyManager()
        manager.set_standby("COM1", 121.5)

        assert manager.decrement_frequency("COM1", "standby", 0.5) is True
        assert manager.get_standby("COM1") == 121.0

    def test_decrement_below_range(self) -> None:
        """Test decrementing below valid range."""
        manager = FrequencyManager()
        manager.set_active("COM1", 118.0)

        assert manager.decrement_frequency("COM1", "active", 0.025) is False
        assert manager.get_active("COM1") == 118.0  # Unchanged


class TestFrequencyManagerGetAll:
    """Test getting all frequencies."""

    def test_get_all_frequencies(self) -> None:
        """Test getting all radio frequencies."""
        manager = FrequencyManager()
        manager.set_active("COM1", 121.5)
        manager.set_standby("COM1", 119.7)

        all_freqs = manager.get_all_frequencies()

        assert all_freqs["COM1"]["active"] == 121.5
        assert all_freqs["COM1"]["standby"] == 119.7
        assert "COM2" in all_freqs
        assert "NAV1" in all_freqs
        assert "NAV2" in all_freqs
