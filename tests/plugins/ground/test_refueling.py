"""Unit tests for refueling service."""

import time

import pytest

from airborne.core.messaging import MessageQueue
from airborne.plugins.ground.ground_services import ServiceRequest, ServiceStatus, ServiceType
from airborne.plugins.ground.services.refueling import RefuelingPhase, RefuelingService


@pytest.fixture
def message_queue() -> MessageQueue:
    """Create a test message queue."""
    return MessageQueue()


@pytest.fixture
def refueling_service(message_queue: MessageQueue) -> RefuelingService:
    """Create a refueling service instance."""
    return RefuelingService(message_queue)


class TestRefuelingPhase:
    """Test RefuelingPhase enum."""

    def test_refueling_phases(self) -> None:
        """Test all refueling phases."""
        assert RefuelingPhase.DISPATCHING.value == "dispatching"
        assert RefuelingPhase.CONNECTING.value == "connecting"
        assert RefuelingPhase.REFUELING.value == "refueling"
        assert RefuelingPhase.COMPLETE.value == "complete"


class TestRefuelingService:
    """Test RefuelingService class."""

    def test_create_service(self, refueling_service: RefuelingService) -> None:
        """Test creating a refueling service."""
        assert refueling_service.service_type == ServiceType.REFUEL
        assert refueling_service.status == ServiceStatus.IDLE
        assert refueling_service.fuel_to_add == 0.0
        assert refueling_service.fuel_added == 0.0

    def test_start_refueling_ga_aircraft(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test starting refueling for GA aircraft."""
        # Set up message capture
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "quantity": 30.0,
                "is_jet": False,
                "current_fuel": 10.0,
                "max_fuel": 50.0,
            },
        )

        result = refueling_service.start(request)

        assert result is True
        assert refueling_service.status == ServiceStatus.IN_PROGRESS
        assert refueling_service.refueling_phase == RefuelingPhase.DISPATCHING
        assert refueling_service.fuel_to_add == 30.0
        assert refueling_service.fuel_added == 0.0
        assert refueling_service.refueling_rate == pytest.approx(
            10.0 / 60.0, rel=0.01
        )  # 10 gal/min

        # Process queue and check audio message
        message_queue.process()
        assert len(audio_messages) == 1
        assert "Fuel truck dispatched" in audio_messages[0].data["text"]

    def test_start_refueling_jet_aircraft(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test starting refueling for jet aircraft."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N456CD",
            parking_id="G2",
            timestamp=time.time(),
            parameters={
                "quantity": 500.0,
                "is_jet": True,
                "current_fuel": 100.0,
                "max_fuel": 1000.0,
            },
        )

        result = refueling_service.start(request)

        assert result is True
        assert refueling_service.fuel_to_add == 500.0
        assert refueling_service.refueling_rate == pytest.approx(
            100.0 / 60.0, rel=0.01
        )  # 100 gal/min

    def test_start_refueling_full_tanks(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test refueling with 'full tanks' option."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N789EF",
            parking_id="G3",
            timestamp=time.time(),
            parameters={
                "quantity": -1.0,  # Full tanks
                "is_jet": False,
                "current_fuel": 15.0,
                "max_fuel": 50.0,
            },
        )

        result = refueling_service.start(request)

        assert result is True
        assert refueling_service.fuel_to_add == 35.0  # 50 - 15 = 35

    def test_start_refueling_exceeds_capacity(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test refueling when requested quantity exceeds capacity."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N999ZZ",
            parking_id="G4",
            timestamp=time.time(),
            parameters={
                "quantity": 100.0,  # More than capacity
                "is_jet": False,
                "current_fuel": 20.0,
                "max_fuel": 50.0,
            },
        )

        result = refueling_service.start(request)

        assert result is True
        assert refueling_service.fuel_to_add == 30.0  # Limited to max capacity

    def test_phase_transition_to_connecting(self, refueling_service: RefuelingService) -> None:
        """Test transition from dispatching to connecting phase."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 20.0, "is_jet": False},
        )

        refueling_service.start(request)
        refueling_service.truck_dispatch_time = 0.1  # Short time for testing

        # Wait for dispatch phase
        time.sleep(0.15)
        refueling_service.update(0.15)

        assert refueling_service.refueling_phase == RefuelingPhase.CONNECTING

    def test_phase_transition_to_refueling(self, refueling_service: RefuelingService) -> None:
        """Test transition from connecting to refueling phase."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 20.0, "is_jet": False},
        )

        refueling_service.start(request)
        refueling_service.truck_dispatch_time = 0.05  # Very short for testing

        # Transition to connecting
        time.sleep(0.1)
        refueling_service.update(0.1)

        # Transition to refueling
        time.sleep(5.0)
        refueling_service.update(5.0)

        assert refueling_service.refueling_phase == RefuelingPhase.REFUELING

    def test_refueling_adds_fuel_over_time(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test that fuel is added over time during refueling."""
        # Set up message capture
        fuel_messages: list = []

        def capture_fuel(msg):  # type: ignore
            fuel_messages.append(msg)

        message_queue.subscribe("fuel.add", capture_fuel)

        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 10.0, "is_jet": False},
        )

        refueling_service.start(request)

        # Fast-forward to refueling phase
        refueling_service.refueling_phase = RefuelingPhase.REFUELING
        refueling_service.phase_start_time = time.time()
        refueling_service.last_update_time = time.time()

        # Simulate some time passing
        time.sleep(1.0)
        refueling_service.update(1.0)

        # Should have added some fuel
        assert refueling_service.fuel_added > 0
        assert refueling_service.fuel_added < refueling_service.fuel_to_add

        # Process queue and check fuel update message
        message_queue.process()
        assert len(fuel_messages) > 0

    def test_refueling_completes_when_target_reached(
        self, refueling_service: RefuelingService
    ) -> None:
        """Test that refueling completes when target fuel is reached."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 1.0, "is_jet": False},
        )

        refueling_service.start(request)

        # Fast-forward to refueling phase
        refueling_service.refueling_phase = RefuelingPhase.REFUELING
        refueling_service.phase_start_time = time.time() - 100.0  # Long enough ago
        refueling_service.last_update_time = time.time()
        refueling_service.fuel_added = 0.9  # Almost done

        # Update should complete
        time.sleep(1.0)
        refueling_service.update(1.0)

        assert refueling_service.refueling_phase == RefuelingPhase.COMPLETE

    def test_service_completes_after_refueling_phase(
        self, refueling_service: RefuelingService
    ) -> None:
        """Test that service status changes to COMPLETE after refueling."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 1.0, "is_jet": False},
        )

        refueling_service.start(request)

        # Fast-forward to complete phase
        refueling_service.refueling_phase = RefuelingPhase.COMPLETE
        refueling_service.update(0.1)

        assert refueling_service.status == ServiceStatus.COMPLETE

    def test_get_progress_during_dispatching(self, refueling_service: RefuelingService) -> None:
        """Test progress calculation during dispatching phase."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 20.0, "is_jet": False},
        )

        refueling_service.start(request)
        progress = refueling_service.get_progress()

        # Should be in dispatching phase, progress 0-20%
        assert 0.0 <= progress <= 0.2

    def test_get_progress_during_refueling(self, refueling_service: RefuelingService) -> None:
        """Test progress calculation during refueling phase."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 100.0, "is_jet": False},
        )

        refueling_service.start(request)
        # Manually set state for testing
        refueling_service.status = ServiceStatus.IN_PROGRESS
        refueling_service.refueling_phase = RefuelingPhase.REFUELING
        refueling_service.fuel_to_add = 100.0
        refueling_service.fuel_added = 50.0  # 50% complete

        progress = refueling_service.get_progress()

        # Should be 25% (phases) + 75% * 50% (refueling) = 62.5%
        assert progress == pytest.approx(0.625, rel=0.01)

    def test_get_progress_when_complete(self, refueling_service: RefuelingService) -> None:
        """Test progress is 100% when complete."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 20.0, "is_jet": False},
        )

        refueling_service.start(request)
        refueling_service.status = ServiceStatus.COMPLETE
        refueling_service.refueling_phase = RefuelingPhase.COMPLETE

        progress = refueling_service.get_progress()

        assert progress == 1.0

    def test_audio_messages_published(
        self, refueling_service: RefuelingService, message_queue: MessageQueue
    ) -> None:
        """Test that audio messages are published at each phase."""
        # Set up message capture
        audio_messages: list = []

        def capture_audio(msg):  # type: ignore
            audio_messages.append(msg)

        message_queue.subscribe("ground.audio.speak", capture_audio)

        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={"quantity": 20.0, "is_jet": False},
        )

        refueling_service.start(request)
        message_queue.process()

        # Should have initial dispatch message
        assert len(audio_messages) == 1
        audio_messages.clear()

        # Transition to connecting
        refueling_service._transition_to_connecting()
        message_queue.process()
        assert len(audio_messages) == 1
        assert "connected" in audio_messages[0].data["text"].lower()

        # Transition to refueling
        refueling_service._transition_to_refueling()
        message_queue.process()
        assert len(audio_messages) == 2  # Previous + new
        assert "in progress" in audio_messages[1].data["text"].lower()

        # Transition to complete
        refueling_service.fuel_added = refueling_service.fuel_to_add
        refueling_service._transition_to_complete()
        message_queue.process()
        assert len(audio_messages) == 3  # All messages
        assert "complete" in audio_messages[2].data["text"].lower()

    def test_zero_fuel_request(self, refueling_service: RefuelingService) -> None:
        """Test requesting zero fuel (should still start but complete immediately)."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "quantity": 0.0,
                "is_jet": False,
                "current_fuel": 50.0,
                "max_fuel": 50.0,
            },
        )

        result = refueling_service.start(request)

        assert result is True
        assert refueling_service.fuel_to_add == 0.0

    def test_update_when_idle(self, refueling_service: RefuelingService) -> None:
        """Test that update does nothing when service is idle."""
        refueling_service.status = ServiceStatus.IDLE
        initial_phase = refueling_service.refueling_phase

        refueling_service.update(1.0)

        assert refueling_service.refueling_phase == initial_phase
        assert refueling_service.fuel_added == 0.0

    def test_estimated_duration_calculation(self, refueling_service: RefuelingService) -> None:
        """Test estimated duration is calculated correctly."""
        request = ServiceRequest(
            service_type=ServiceType.REFUEL,
            aircraft_id="N123AB",
            parking_id="G1",
            timestamp=time.time(),
            parameters={
                "quantity": 60.0,  # 60 gallons
                "is_jet": False,  # 10 gal/min = 6 minutes refueling
                "current_fuel": 0.0,
                "max_fuel": 100.0,
            },
        )

        refueling_service.start(request)

        # Estimated duration = dispatch (30-60s) + connection (5s) + refueling (360s)
        # Should be roughly 395-425 seconds
        assert 395.0 <= refueling_service.estimated_duration <= 425.0
