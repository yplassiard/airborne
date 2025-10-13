"""Tests for Proximity Audio Cues."""

import pytest

from airborne.audio.proximity import BeepPattern, ProximityCueManager, ProximityTarget
from airborne.physics.vectors import Vector3


class TestProximityTarget:
    """Test proximity target dataclass."""

    def test_create_target(self) -> None:
        """Test creating a proximity target."""
        position = Vector3(100, 0, 200)
        target = ProximityTarget(
            target_id="test_target",
            position=position,
            pattern=BeepPattern.LINEAR,
            min_distance_m=10.0,
            max_distance_m=500.0,
        )

        assert target.target_id == "test_target"
        assert target.position == position
        assert target.pattern == BeepPattern.LINEAR
        assert target.min_distance_m == 10.0
        assert target.max_distance_m == 500.0
        assert target.enabled is True


class TestProximityCueManager:
    """Test proximity cue manager."""

    @pytest.fixture
    def manager(self) -> ProximityCueManager:
        """Create proximity cue manager."""
        return ProximityCueManager()

    def test_add_target(self, manager: ProximityCueManager) -> None:
        """Test adding a proximity target."""
        manager.add_target("target1", Vector3(0, 0, 100))

        assert len(manager.targets) == 1
        assert "target1" in manager.targets

        target = manager.get_target("target1")
        assert target is not None
        assert target.target_id == "target1"

    def test_remove_target(self, manager: ProximityCueManager) -> None:
        """Test removing a proximity target."""
        manager.add_target("target1", Vector3(0, 0, 100))
        manager.remove_target("target1")

        assert len(manager.targets) == 0
        assert manager.get_target("target1") is None

    def test_enable_disable_target(self, manager: ProximityCueManager) -> None:
        """Test enabling and disabling targets."""
        manager.add_target("target1", Vector3(0, 0, 100))

        # Disable
        manager.enable_target("target1", False)
        target = manager.get_target("target1")
        assert target is not None
        assert target.enabled is False

        # Re-enable
        manager.enable_target("target1", True)
        target = manager.get_target("target1")
        assert target is not None
        assert target.enabled is True

    def test_clear_targets(self, manager: ProximityCueManager) -> None:
        """Test clearing all targets."""
        manager.add_target("target1", Vector3(0, 0, 100))
        manager.add_target("target2", Vector3(0, 0, 200))
        manager.clear_targets()

        assert len(manager.targets) == 0

    def test_get_all_targets(self, manager: ProximityCueManager) -> None:
        """Test getting all targets."""
        manager.add_target("target1", Vector3(0, 0, 100))
        manager.add_target("target2", Vector3(0, 0, 200))

        targets = manager.get_all_targets()
        assert len(targets) == 2


class TestNearestTarget:
    """Test finding nearest target."""

    @pytest.fixture
    def manager(self) -> ProximityCueManager:
        """Create manager with multiple targets."""
        mgr = ProximityCueManager()
        mgr.add_target("near", Vector3(0, 0, 50), max_distance_m=100.0)
        mgr.add_target("far", Vector3(0, 0, 200), max_distance_m=300.0)
        return mgr

    def test_nearest_target_selected(self, manager: ProximityCueManager) -> None:
        """Test that nearest target is selected."""
        position = Vector3(0, 0, 0)
        target_id, distance, frequency = manager.get_nearest_target(position)

        assert target_id == "near"
        assert distance == 50.0
        assert frequency > 0

    def test_no_target_when_out_of_range(self, manager: ProximityCueManager) -> None:
        """Test that no target is selected when out of range."""
        position = Vector3(0, 0, 1000)  # Far from all targets
        target_id, distance, frequency = manager.get_nearest_target(position)

        assert target_id is None
        assert distance == float("inf")
        assert frequency == 0.0

    def test_disabled_target_ignored(self, manager: ProximityCueManager) -> None:
        """Test that disabled targets are ignored."""
        manager.enable_target("near", False)

        position = Vector3(0, 0, 0)
        target_id, distance, frequency = manager.get_nearest_target(position)

        # Should select "far" since "near" is disabled
        assert target_id == "far"


class TestBeepFrequency:
    """Test beep frequency calculations."""

    @pytest.fixture
    def manager(self) -> ProximityCueManager:
        """Create manager with linear pattern target."""
        mgr = ProximityCueManager()
        mgr.add_target(
            "linear_target",
            Vector3(0, 0, 100),
            pattern=BeepPattern.LINEAR,
            min_distance_m=10.0,
            max_distance_m=100.0,
            min_frequency_hz=1.0,
            max_frequency_hz=10.0,
        )
        return mgr

    def test_frequency_increases_with_proximity(self, manager: ProximityCueManager) -> None:
        """Test that frequency increases as distance decreases."""
        # Far position
        _, _, freq_far = manager.get_nearest_target(Vector3(0, 0, 10))

        # Close position
        _, _, freq_close = manager.get_nearest_target(Vector3(0, 0, 90))

        assert freq_close > freq_far

    def test_max_frequency_at_min_distance(self, manager: ProximityCueManager) -> None:
        """Test max frequency at minimum distance."""
        _, _, frequency = manager.get_nearest_target(Vector3(0, 0, 90))  # 10m from target

        # Should be at or near max frequency (10 Hz)
        assert frequency >= 9.0

    def test_min_frequency_at_max_distance(self, manager: ProximityCueManager) -> None:
        """Test min frequency at maximum distance."""
        _, _, frequency = manager.get_nearest_target(Vector3(0, 0, 0))  # 100m from target

        # Should be at or near min frequency (1 Hz)
        assert frequency <= 2.0


class TestBeepPatterns:
    """Test different beep patterns."""

    def test_linear_pattern(self) -> None:
        """Test linear beep pattern."""
        manager = ProximityCueManager()
        manager.add_target(
            "target",
            Vector3(0, 0, 100),
            pattern=BeepPattern.LINEAR,
            min_distance_m=0.0,
            max_distance_m=100.0,
            min_frequency_hz=1.0,
            max_frequency_hz=10.0,
        )

        # At midpoint (50m), should be ~5.5 Hz
        _, _, frequency = manager.get_nearest_target(Vector3(0, 0, 50))
        assert 4.5 <= frequency <= 6.5

    def test_exponential_pattern(self) -> None:
        """Test exponential beep pattern."""
        manager = ProximityCueManager()
        manager.add_target(
            "target",
            Vector3(0, 0, 100),
            pattern=BeepPattern.EXPONENTIAL,
            min_distance_m=0.0,
            max_distance_m=100.0,
            min_frequency_hz=1.0,
            max_frequency_hz=10.0,
        )

        # Exponential should have lower frequency at midpoint than linear
        _, _, freq_mid = manager.get_nearest_target(Vector3(0, 0, 50))

        # Should be less than linear midpoint (~5.5 Hz)
        assert freq_mid < 5.0

    def test_constant_pattern(self) -> None:
        """Test constant beep pattern."""
        manager = ProximityCueManager()
        manager.add_target(
            "target",
            Vector3(0, 0, 100),
            pattern=BeepPattern.CONSTANT,
            min_distance_m=0.0,
            max_distance_m=100.0,
            min_frequency_hz=1.0,
            max_frequency_hz=10.0,
        )

        # Should always be at max frequency
        _, _, freq_far = manager.get_nearest_target(Vector3(0, 0, 0))
        _, _, freq_close = manager.get_nearest_target(Vector3(0, 0, 90))

        assert freq_far >= 9.0
        assert freq_close >= 9.0
        assert abs(freq_far - freq_close) < 0.1

    def test_stepped_pattern(self) -> None:
        """Test stepped beep pattern."""
        manager = ProximityCueManager()
        manager.add_target(
            "target",
            Vector3(0, 0, 100),
            pattern=BeepPattern.STEPPED,
            min_distance_m=0.0,
            max_distance_m=100.0,
            min_frequency_hz=0.0,
            max_frequency_hz=10.0,
        )

        # Test different zones
        _, _, freq_far = manager.get_nearest_target(Vector3(0, 0, 10))  # 90m = far zone
        _, _, freq_close = manager.get_nearest_target(Vector3(0, 0, 90))  # 10m = close zone

        # Stepped should have discrete levels
        assert freq_close > freq_far


class TestBeepTiming:
    """Test beep timing and update logic."""

    @pytest.fixture
    def manager(self) -> ProximityCueManager:
        """Create manager with target."""
        mgr = ProximityCueManager()
        mgr.add_target(
            "target",
            Vector3(0, 0, 100),
            min_distance_m=0.0,
            max_distance_m=200.0,
            min_frequency_hz=1.0,  # 1 beep per second
            max_frequency_hz=10.0,  # 10 beeps per second
        )
        return mgr

    def test_update_returns_beep_signal(self, manager: ProximityCueManager) -> None:
        """Test that update returns True when beep should play."""
        position = Vector3(0, 0, 90)  # Close to target = high frequency

        # Should beep after sufficient time
        should_beep = manager.update(position, delta_time=0.2)
        assert should_beep is True

    def test_no_beep_when_out_of_range(self, manager: ProximityCueManager) -> None:
        """Test no beep when out of range."""
        position = Vector3(0, 0, 500)  # Far from target

        should_beep = manager.update(position, delta_time=0.1)
        assert should_beep is False

    def test_beep_rate_increases_with_proximity(self, manager: ProximityCueManager) -> None:
        """Test that beep rate increases as distance decreases."""
        # At max distance: 1 Hz = 1 beep per second
        pos_far = Vector3(0, 0, -100)  # 200m from target
        manager.update(pos_far, delta_time=0.0)
        freq_far = manager.get_current_frequency()

        # At min distance: 10 Hz = 10 beeps per second
        pos_close = Vector3(0, 0, 100)  # 0m from target
        manager.update(pos_close, delta_time=0.0)
        freq_close = manager.get_current_frequency()

        assert freq_close > freq_far


class TestRealWorldScenarios:
    """Test real-world proximity scenarios."""

    def test_runway_approach_guidance(self) -> None:
        """Test runway approach proximity guidance."""
        manager = ProximityCueManager()

        # Runway threshold at 1000m ahead
        manager.add_target(
            "runway_threshold",
            Vector3(0, 0, 1000),
            pattern=BeepPattern.EXPONENTIAL,
            min_distance_m=50.0,  # Start beeping at 50m
            max_distance_m=500.0,  # Stop beeping beyond 500m
            min_frequency_hz=0.5,
            max_frequency_hz=5.0,
        )

        # Aircraft at 300m from threshold
        position = Vector3(0, 0, 700)
        target_id, distance, frequency = manager.get_nearest_target(position)

        assert target_id == "runway_threshold"
        assert distance == 300.0
        assert 0.5 <= frequency <= 5.0

    def test_taxiway_node_navigation(self) -> None:
        """Test taxiway node proximity navigation."""
        manager = ProximityCueManager()

        # Multiple taxiway nodes
        manager.add_target("node_A1", Vector3(50, 0, 50), max_distance_m=100.0)
        manager.add_target("node_A2", Vector3(100, 0, 100), max_distance_m=100.0)
        manager.add_target("node_A3", Vector3(150, 0, 150), max_distance_m=100.0)

        # Aircraft approaching node A2
        position = Vector3(90, 0, 90)
        target_id, distance, frequency = manager.get_nearest_target(position)

        # Should lock onto nearest node (A2)
        assert target_id == "node_A2"
        assert distance < 20.0

    def test_parking_stand_guidance(self) -> None:
        """Test parking stand proximity guidance."""
        manager = ProximityCueManager()

        # Parking stand
        manager.add_target(
            "stand_5",
            Vector3(200, 0, 300),
            pattern=BeepPattern.LINEAR,
            min_distance_m=5.0,  # Very close range for parking
            max_distance_m=50.0,
            min_frequency_hz=1.0,
            max_frequency_hz=10.0,
        )

        # Aircraft very close to stand
        position = Vector3(195, 0, 295)  # ~7m away
        target_id, distance, frequency = manager.get_nearest_target(position)

        assert target_id == "stand_5"
        assert 5.0 <= distance <= 10.0
        assert frequency > 7.0  # High frequency when close

    def test_multi_target_switching(self) -> None:
        """Test switching between multiple targets."""
        manager = ProximityCueManager()

        # Two targets along a path
        manager.add_target("waypoint_1", Vector3(0, 0, 100), max_distance_m=150.0)
        manager.add_target("waypoint_2", Vector3(0, 0, 300), max_distance_m=150.0)

        # Approaching waypoint 1
        target_id, _, _ = manager.get_nearest_target(Vector3(0, 0, 50))
        assert target_id == "waypoint_1"

        # Passed waypoint 1, approaching waypoint 2
        target_id, _, _ = manager.get_nearest_target(Vector3(0, 0, 250))
        assert target_id == "waypoint_2"
