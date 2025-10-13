"""Tests for Beep Generator."""

import numpy as np
import pytest

from airborne.audio.beeper import BeepGenerator, BeepStyle, ProximityBeeper


class TestBeepGenerator:
    """Test beep generator."""

    @pytest.fixture
    def generator(self) -> BeepGenerator:
        """Create beep generator."""
        return BeepGenerator(sample_rate=44100)

    def test_generate_sine_beep(self, generator: BeepGenerator) -> None:
        """Test generating sine wave beep."""
        samples = generator.generate_beep(frequency_hz=1000, duration_s=0.1, style=BeepStyle.SINE)

        assert len(samples) == 4410  # 0.1s * 44100 Hz
        assert samples.dtype == np.float32
        assert -1.0 <= samples.min() <= 1.0
        assert -1.0 <= samples.max() <= 1.0

    def test_generate_square_beep(self, generator: BeepGenerator) -> None:
        """Test generating square wave beep."""
        samples = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, style=BeepStyle.SQUARE
        )

        assert len(samples) == 4410
        # Square wave should have values near -1 or +1
        assert np.abs(samples).max() > 0.2

    def test_generate_triangle_beep(self, generator: BeepGenerator) -> None:
        """Test generating triangle wave beep."""
        samples = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, style=BeepStyle.TRIANGLE
        )

        assert len(samples) == 4410
        assert samples.dtype == np.float32

    def test_generate_sawtooth_beep(self, generator: BeepGenerator) -> None:
        """Test generating sawtooth wave beep."""
        samples = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, style=BeepStyle.SAWTOOTH
        )

        assert len(samples) == 4410
        assert samples.dtype == np.float32

    def test_generate_chirp_beep(self, generator: BeepGenerator) -> None:
        """Test generating chirp beep."""
        samples = generator.generate_beep(frequency_hz=1000, duration_s=0.1, style=BeepStyle.CHIRP)

        assert len(samples) == 4410
        assert samples.dtype == np.float32

    def test_amplitude_control(self, generator: BeepGenerator) -> None:
        """Test amplitude control."""
        samples_quiet = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, amplitude=0.1
        )
        samples_loud = generator.generate_beep(frequency_hz=1000, duration_s=0.1, amplitude=0.5)

        # Louder beep should have higher max amplitude
        assert np.abs(samples_loud).max() > np.abs(samples_quiet).max()

    def test_duration_control(self, generator: BeepGenerator) -> None:
        """Test duration control."""
        samples_short = generator.generate_beep(frequency_hz=1000, duration_s=0.05)
        samples_long = generator.generate_beep(frequency_hz=1000, duration_s=0.2)

        assert len(samples_short) == 2205  # 0.05s * 44100
        assert len(samples_long) == 8820  # 0.2s * 44100

    def test_fade_prevents_clicks(self, generator: BeepGenerator) -> None:
        """Test that fade-in/fade-out prevents clicks."""
        samples = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, fade_in_s=0.01, fade_out_s=0.01
        )

        # First sample should be near 0 (faded in)
        assert abs(samples[0]) < 0.01

        # Last sample should be near 0 (faded out)
        assert abs(samples[-1]) < 0.01


class TestProximityBeep:
    """Test proximity-based beep generation."""

    @pytest.fixture
    def generator(self) -> BeepGenerator:
        """Create beep generator."""
        return BeepGenerator(sample_rate=44100)

    def test_proximity_beep_frequency_changes(self, generator: BeepGenerator) -> None:
        """Test that proximity beep frequency changes with distance."""
        # Generate beeps at different distances
        beep_far = generator.generate_proximity_beep(
            distance_m=400,
            min_distance_m=10,
            max_distance_m=500,
            base_frequency_hz=800,
            max_frequency_hz=1200,
        )

        beep_close = generator.generate_proximity_beep(
            distance_m=50,
            min_distance_m=10,
            max_distance_m=500,
            base_frequency_hz=800,
            max_frequency_hz=1200,
        )

        # Both should generate samples
        assert len(beep_far) > 0
        assert len(beep_close) > 0

        # Can't directly test frequency from samples, but verify they're different
        # (This is a basic sanity check)
        assert not np.array_equal(beep_far, beep_close)

    def test_proximity_beep_at_min_distance(self, generator: BeepGenerator) -> None:
        """Test proximity beep at minimum distance."""
        beep = generator.generate_proximity_beep(
            distance_m=10,
            min_distance_m=10,
            max_distance_m=500,
            base_frequency_hz=800,
            max_frequency_hz=1200,
        )

        assert len(beep) > 0
        # Should use max frequency (1200 Hz) at min distance

    def test_proximity_beep_at_max_distance(self, generator: BeepGenerator) -> None:
        """Test proximity beep at maximum distance."""
        beep = generator.generate_proximity_beep(
            distance_m=500,
            min_distance_m=10,
            max_distance_m=500,
            base_frequency_hz=800,
            max_frequency_hz=1200,
        )

        assert len(beep) > 0
        # Should use base frequency (800 Hz) at max distance


class TestProximityBeeper:
    """Test high-level proximity beeper."""

    @pytest.fixture
    def beeper(self) -> ProximityBeeper:
        """Create proximity beeper."""
        return ProximityBeeper(sample_rate=44100)

    def test_beep_timing(self, beeper: ProximityBeeper) -> None:
        """Test beep timing logic."""
        # At 2 Hz, should beep every 0.5 seconds
        # First call with 0.3s: no beep
        samples = beeper.get_beep_if_ready(
            distance_m=100, beep_frequency_hz=2.0, delta_time=0.3
        )
        assert samples is None

        # Second call with 0.3s (total 0.6s): should beep
        samples = beeper.get_beep_if_ready(
            distance_m=100, beep_frequency_hz=2.0, delta_time=0.3
        )
        assert samples is not None
        assert len(samples) > 0

    def test_no_beep_when_frequency_zero(self, beeper: ProximityBeeper) -> None:
        """Test no beep when frequency is zero."""
        samples = beeper.get_beep_if_ready(
            distance_m=100, beep_frequency_hz=0.0, delta_time=1.0
        )
        assert samples is None

    def test_reset_timing(self, beeper: ProximityBeeper) -> None:
        """Test resetting beep timing."""
        # Accumulate time
        beeper.get_beep_if_ready(distance_m=100, beep_frequency_hz=1.0, delta_time=0.5)

        # Reset
        beeper.reset_timing()

        assert beeper.last_beep_time == 0.0

    def test_high_frequency_beeping(self, beeper: ProximityBeeper) -> None:
        """Test high frequency beeping (fast beeps)."""
        # At 10 Hz, should beep every 0.1 seconds
        samples = beeper.get_beep_if_ready(
            distance_m=50, beep_frequency_hz=10.0, delta_time=0.15
        )

        assert samples is not None

    def test_low_frequency_beeping(self, beeper: ProximityBeeper) -> None:
        """Test low frequency beeping (slow beeps)."""
        # At 0.5 Hz, should beep every 2 seconds
        samples = beeper.get_beep_if_ready(
            distance_m=400, beep_frequency_hz=0.5, delta_time=1.0
        )
        assert samples is None  # Not yet time

        samples = beeper.get_beep_if_ready(
            distance_m=400, beep_frequency_hz=0.5, delta_time=1.5
        )
        assert samples is not None  # Now it's time


class TestWaveformCharacteristics:
    """Test waveform generation characteristics."""

    @pytest.fixture
    def generator(self) -> BeepGenerator:
        """Create beep generator."""
        return BeepGenerator(sample_rate=44100)

    def test_sine_wave_smoothness(self, generator: BeepGenerator) -> None:
        """Test that sine wave is smooth."""
        samples = generator.generate_beep(frequency_hz=1000, duration_s=0.1, style=BeepStyle.SINE)

        # Sine wave should have no discontinuities
        # Check that max value is near amplitude (0.3)
        assert 0.25 <= np.abs(samples).max() <= 0.35

    def test_square_wave_edges(self, generator: BeepGenerator) -> None:
        """Test that square wave has sharp edges."""
        samples = generator.generate_beep(
            frequency_hz=1000, duration_s=0.1, style=BeepStyle.SQUARE
        )

        # Square wave should have values near -amplitude or +amplitude
        # Most samples should be near the extremes
        extreme_samples = np.abs(np.abs(samples) - 0.3) < 0.05
        assert np.sum(extreme_samples) > len(samples) * 0.8  # 80% should be at extremes

    def test_different_frequencies(self, generator: BeepGenerator) -> None:
        """Test generating beeps at different frequencies."""
        beep_low = generator.generate_beep(frequency_hz=500, duration_s=0.1)
        beep_mid = generator.generate_beep(frequency_hz=1000, duration_s=0.1)
        beep_high = generator.generate_beep(frequency_hz=2000, duration_s=0.1)

        # All should generate same number of samples
        assert len(beep_low) == len(beep_mid) == len(beep_high)

        # But waveforms should be different
        assert not np.array_equal(beep_low, beep_mid)
        assert not np.array_equal(beep_mid, beep_high)


class TestRealWorldScenarios:
    """Test real-world beeping scenarios."""

    def test_parking_guidance_beeps(self) -> None:
        """Test parking guidance beeping pattern."""
        beeper = ProximityBeeper(sample_rate=44100)

        # Simulate approaching parking stand
        distances = [50, 40, 30, 20, 10, 5]  # Getting closer
        frequencies = [1.0, 2.0, 4.0, 6.0, 8.0, 10.0]  # Beeping faster

        for distance, frequency in zip(distances, frequencies):
            beeper.reset_timing()
            samples = beeper.get_beep_if_ready(
                distance_m=distance,
                beep_frequency_hz=frequency,
                delta_time=1.0 / frequency,  # Just enough time for one beep
            )

            # Should generate beeps at all distances
            assert samples is not None
            assert len(samples) > 0

    def test_runway_approach_beeps(self) -> None:
        """Test runway approach beeping."""
        generator = BeepGenerator(sample_rate=44100)

        # Generate approach beeps at different distances
        beep_500m = generator.generate_proximity_beep(
            distance_m=500,
            min_distance_m=50,
            max_distance_m=500,
            base_frequency_hz=600,
            max_frequency_hz=1400,
            style=BeepStyle.CHIRP,  # Use chirp for approach
        )

        beep_100m = generator.generate_proximity_beep(
            distance_m=100,
            min_distance_m=50,
            max_distance_m=500,
            base_frequency_hz=600,
            max_frequency_hz=1400,
            style=BeepStyle.CHIRP,
        )

        assert len(beep_500m) > 0
        assert len(beep_100m) > 0

    def test_taxiway_node_beeps(self) -> None:
        """Test taxiway node proximity beeps."""
        generator = BeepGenerator(sample_rate=44100)

        # Simple sine beep for taxiway nodes
        beep = generator.generate_proximity_beep(
            distance_m=25,
            min_distance_m=5,
            max_distance_m=50,
            base_frequency_hz=800,
            max_frequency_hz=1200,
            style=BeepStyle.SINE,
            duration_s=0.08,
        )

        assert len(beep) > 0
        # Short duration beep for quick navigation cues
        assert len(beep) == int(44100 * 0.08)
