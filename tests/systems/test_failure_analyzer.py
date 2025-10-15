"""Tests for failure analyzer system."""

from datetime import datetime, timedelta

from airborne.systems.failure_analyzer import (
    FailureAnalyzer,
    FailureSnapshot,
    FailureType,
    SurvivabilityLevel,
)


class TestFailureAnalyzer:
    """Test failure analyzer functionality."""

    def test_analyzer_initialization(self):
        """Test FailureAnalyzer can be initialized."""
        analyzer = FailureAnalyzer()
        assert analyzer is not None
        assert len(analyzer.event_timeline) == 0
        assert len(analyzer.warnings_given) == 0
        assert analyzer.flight_start_time is None

    def test_start_flight(self):
        """Test starting flight tracking."""
        analyzer = FailureAnalyzer()
        start_time = datetime.now()
        analyzer.start_flight(start_time)

        assert analyzer.flight_start_time == start_time
        assert len(analyzer.event_timeline) == 1
        assert analyzer.event_timeline[0][1] == "Flight started"

    def test_record_event(self):
        """Test recording events."""
        analyzer = FailureAnalyzer()
        analyzer.record_event(10.5, "Engine started")
        analyzer.record_event(30.0, "Takeoff roll commenced")

        assert len(analyzer.event_timeline) == 2
        assert analyzer.event_timeline[0] == (10.5, "Engine started")
        assert analyzer.event_timeline[1] == (30.0, "Takeoff roll commenced")

    def test_record_warning(self):
        """Test recording warnings."""
        analyzer = FailureAnalyzer()
        analyzer.record_warning(120.0, "Low fuel warning")

        assert len(analyzer.warnings_given) == 1
        assert analyzer.warnings_given[0] == (120.0, "Low fuel warning")
        # Should also be in event timeline
        assert len(analyzer.event_timeline) == 1
        assert "WARNING" in analyzer.event_timeline[0][1]

    def test_fuel_exhaustion_detection(self):
        """Test fuel exhaustion failure detection."""
        analyzer = FailureAnalyzer()
        start_time = datetime.now()
        analyzer.start_flight(start_time)

        failure_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=180),
            position=(37.5, -122.5, 2000.0),
            velocity=(0.0, -10.0, 100.0),
            airspeed_knots=70.0,
            ground_speed_knots=70.0,
            vertical_speed_fpm=-500.0,
            heading=270.0,
            pitch=-5.0,
            roll=0.0,
            engine_state={"running": False, "rpm": 0},
            electrical_state={"battery_voltage": 12.0},
            fuel_state={"total_usable_gallons": 0.0, "tanks": {}},
            control_inputs={"throttle": 1.0, "gear": True},
        )

        impact_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=185),
            position=(37.4, -122.4, 100.0),
            velocity=(0.0, -15.0, 50.0),
            airspeed_knots=55.0,
            ground_speed_knots=55.0,
            vertical_speed_fpm=-800.0,
            heading=270.0,
            pitch=-10.0,
            roll=5.0,
            engine_state={"running": False, "rpm": 0},
            electrical_state={"battery_voltage": 12.0},
            fuel_state={"total_usable_gallons": 0.0, "tanks": {}},
            control_inputs={"throttle": 0.0, "gear": True},
        )

        analysis = analyzer.analyze_failure(failure_snapshot, impact_snapshot)

        assert analysis.failure_type == FailureType.FUEL_EXHAUSTION
        assert "Fuel Exhaustion" in analysis.primary_cause
        assert analysis.impact_force_g > 0

    def test_hard_landing_detection(self):
        """Test hard landing failure detection."""
        analyzer = FailureAnalyzer()
        start_time = datetime.now()
        analyzer.start_flight(start_time)

        failure_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=30),
            position=(37.5, -122.5, 50.0),
            velocity=(0.0, -12.0, 60.0),
            airspeed_knots=65.0,
            ground_speed_knots=65.0,
            vertical_speed_fpm=-720.0,
            heading=90.0,
            pitch=-8.0,
            roll=0.0,
            engine_state={"running": True, "rpm": 2000},
            electrical_state={"battery_voltage": 14.0},
            fuel_state={"total_usable_gallons": 20.0, "tanks": {}},
            control_inputs={"throttle": 0.2, "gear": True},
        )

        impact_snapshot = failure_snapshot

        analysis = analyzer.analyze_failure(failure_snapshot, impact_snapshot)

        assert analysis.failure_type == FailureType.HARD_LANDING
        assert "Hard Landing" in analysis.primary_cause

    def test_stall_spin_detection(self):
        """Test stall/spin failure detection."""
        analyzer = FailureAnalyzer()
        start_time = datetime.now()
        analyzer.start_flight(start_time)

        failure_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=15),
            position=(37.5, -122.5, 500.0),
            velocity=(0.0, -20.0, 30.0),
            airspeed_knots=40.0,  # Below stall
            ground_speed_knots=40.0,
            vertical_speed_fpm=-1200.0,
            heading=180.0,
            pitch=-30.0,
            roll=45.0,  # Steep bank
            engine_state={"running": True, "rpm": 2200},
            electrical_state={"battery_voltage": 14.0},
            fuel_state={"total_usable_gallons": 30.0, "tanks": {}},
            control_inputs={"throttle": 0.5, "gear": False},
        )

        impact_snapshot = failure_snapshot

        analysis = analyzer.analyze_failure(failure_snapshot, impact_snapshot)

        assert analysis.failure_type == FailureType.STALL_SPIN
        assert "Stall" in analysis.primary_cause

    def test_impact_force_calculation(self):
        """Test impact G-force calculation."""
        analyzer = FailureAnalyzer()

        # Moderate landing (-300 fpm)
        impact_snapshot = FailureSnapshot(
            time=datetime.now(),
            position=(37.5, -122.5, 10.0),
            velocity=(0.0, -5.0, 60.0),
            airspeed_knots=60.0,
            ground_speed_knots=60.0,
            vertical_speed_fpm=-300.0,
            heading=90.0,
            pitch=-3.0,
            roll=0.0,
            engine_state={},
            electrical_state={},
            fuel_state={},
            control_inputs={"gear": True},
        )

        g_force = analyzer._calculate_impact_force(impact_snapshot)
        assert g_force > 0
        assert g_force < 5.0  # Should be survivable

        # Hard landing (-900 fpm) without gear
        impact_snapshot.vertical_speed_fpm = -900.0
        impact_snapshot.control_inputs = {"gear": False}  # No gear = harder impact
        g_force = analyzer._calculate_impact_force(impact_snapshot)
        assert g_force > 1.0  # More severe than moderate landing

    def test_survivability_assessment(self):
        """Test survivability level assessment."""
        analyzer = FailureAnalyzer()
        impact_snapshot = FailureSnapshot(
            time=datetime.now(),
            position=(37.5, -122.5, 0.0),
            velocity=(0.0, 0.0, 0.0),
            airspeed_knots=0.0,
            ground_speed_knots=0.0,
            vertical_speed_fpm=0.0,
            heading=0.0,
            pitch=0.0,
            roll=0.0,
            engine_state={},
            electrical_state={},
            fuel_state={},
            control_inputs={},
        )

        # Low G - survivable
        survivability = analyzer._assess_survivability(1.5, impact_snapshot)
        assert survivability == SurvivabilityLevel.SURVIVABLE

        # Medium G - minor injury
        survivability = analyzer._assess_survivability(3.5, impact_snapshot)
        assert survivability == SurvivabilityLevel.MINOR_INJURY

        # High G - serious injury
        survivability = analyzer._assess_survivability(7.0, impact_snapshot)
        assert survivability == SurvivabilityLevel.SERIOUS_INJURY

        # Very high G - likely fatal
        survivability = analyzer._assess_survivability(15.0, impact_snapshot)
        assert survivability == SurvivabilityLevel.LIKELY_FATAL

        # Extreme G - unsurvivable
        survivability = analyzer._assess_survivability(25.0, impact_snapshot)
        assert survivability == SurvivabilityLevel.UNSURVIVABLE

    def test_generate_report(self):
        """Test failure report generation."""
        analyzer = FailureAnalyzer()
        start_time = datetime.now()
        analyzer.start_flight(start_time)
        analyzer.record_warning(180.0, "Low fuel")

        failure_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=190),
            position=(37.5, -122.5, 2000.0),
            velocity=(0.0, -10.0, 100.0),
            airspeed_knots=70.0,
            ground_speed_knots=70.0,
            vertical_speed_fpm=-500.0,
            heading=270.0,
            pitch=-5.0,
            roll=0.0,
            engine_state={"running": False, "rpm": 0},
            electrical_state={"battery_voltage": 12.0},
            fuel_state={"total_usable_gallons": 0.0, "tanks": {}},
            control_inputs={"throttle": 1.0, "gear": False},
        )

        impact_snapshot = FailureSnapshot(
            time=start_time + timedelta(minutes=195),
            position=(37.4, -122.4, 100.0),
            velocity=(0.0, -15.0, 50.0),
            airspeed_knots=55.0,
            ground_speed_knots=55.0,
            vertical_speed_fpm=-800.0,
            heading=270.0,
            pitch=-10.0,
            roll=5.0,
            engine_state={"running": False, "rpm": 0},
            electrical_state={"battery_voltage": 12.0},
            fuel_state={"total_usable_gallons": 0.0, "tanks": {}},
            control_inputs={"throttle": 0.0, "gear": False},
        )

        analysis = analyzer.analyze_failure(failure_snapshot, impact_snapshot)
        report = analyzer.generate_report(analysis)

        assert "FLIGHT FAILURE ANALYSIS" in report
        assert "Fuel Exhaustion" in report
        assert "Lessons Learned" in report
        assert "ignored" in report.lower()  # Should mention ignored warning
        assert "gear" in report.lower()  # Should mention gear retracted
