"""Tests for input management system."""

from unittest.mock import Mock

import pygame
import pytest

from airborne.core.event_bus import EventBus
from airborne.core.input import (
    InputAction,
    InputActionEvent,
    InputConfig,
    InputManager,
    InputState,
    InputStateEvent,
)


class TestInputAction:
    """Test InputAction enum."""

    def test_has_flight_controls(self) -> None:
        """Test flight control actions exist."""
        assert InputAction.PITCH_UP.value == "pitch_up"
        assert InputAction.ROLL_LEFT.value == "roll_left"
        assert InputAction.THROTTLE_INCREASE.value == "throttle_increase"

    def test_has_system_controls(self) -> None:
        """Test system control actions exist."""
        assert InputAction.PAUSE.value == "pause"
        assert InputAction.QUIT.value == "quit"


class TestInputState:
    """Test InputState dataclass."""

    def test_default_state(self) -> None:
        """Test default input state."""
        state = InputState()
        assert state.pitch == 0.0
        assert state.roll == 0.0
        assert state.yaw == 0.0
        assert state.throttle == 0.0
        assert state.brakes == 0.0
        assert state.flaps == 0.0
        assert state.gear == 1.0  # Default gear down

    def test_clamp_all_within_range(self) -> None:
        """Test clamping values already in range."""
        state = InputState(pitch=0.5, roll=-0.5, throttle=0.8)
        state.clamp_all()
        assert state.pitch == 0.5
        assert state.roll == -0.5
        assert state.throttle == 0.8

    def test_clamp_all_above_range(self) -> None:
        """Test clamping values above maximum."""
        state = InputState(pitch=2.0, throttle=1.5)
        state.clamp_all()
        assert state.pitch == 1.0
        assert state.throttle == 1.0

    def test_clamp_all_below_range(self) -> None:
        """Test clamping values below minimum."""
        state = InputState(roll=-2.0, throttle=-0.5)
        state.clamp_all()
        assert state.roll == -1.0
        assert state.throttle == 0.0


class TestInputConfig:
    """Test InputConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = InputConfig()
        assert len(config.keyboard_bindings) > 0
        assert config.axis_sensitivity == 1.0
        assert config.axis_deadzone == 0.1
        assert config.throttle_increment == 0.01  # Changed to 1%

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        bindings = {pygame.K_w: InputAction.PITCH_UP}
        config = InputConfig(keyboard_bindings=bindings, axis_sensitivity=2.0)
        assert config.keyboard_bindings == bindings
        assert config.axis_sensitivity == 2.0

    def test_default_bindings_include_essential_controls(self) -> None:
        """Test default bindings include flight controls."""
        config = InputConfig()
        # Check some essential bindings exist
        assert InputAction.PITCH_UP in config.keyboard_bindings.values()
        assert InputAction.THROTTLE_INCREASE in config.keyboard_bindings.values()
        # Note: QUIT is now handled specially with Ctrl+Q (not in bindings dict)
        assert InputAction.PAUSE in config.keyboard_bindings.values()


class TestInputManagerInitialization:
    """Test InputManager initialization."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    def test_init_with_default_config(self, event_bus: EventBus) -> None:
        """Test initialization with default config."""
        manager = InputManager(event_bus)
        assert manager.event_bus == event_bus
        assert manager.config is not None
        assert isinstance(manager.state, InputState)

    def test_init_with_custom_config(self, event_bus: EventBus) -> None:
        """Test initialization with custom config."""
        config = InputConfig(axis_sensitivity=2.0)
        manager = InputManager(event_bus, config)
        assert manager.config == config
        assert manager.config.axis_sensitivity == 2.0

    def test_init_state_is_zero(self, event_bus: EventBus) -> None:
        """Test initial state is neutral."""
        manager = InputManager(event_bus)
        state = manager.get_state()
        assert state.pitch == 0.0
        assert state.roll == 0.0
        assert state.throttle == 0.0


class TestInputManagerKeyboard:
    """Test InputManager keyboard input."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_process_keydown_updates_state(self, manager: InputManager) -> None:
        """Test keydown event updates internal state."""
        event = Mock()
        event.type = pygame.KEYDOWN
        event.key = pygame.K_UP  # Pitch down

        manager.process_events([event])
        assert pygame.K_UP in manager._keys_pressed

    def test_process_keyup_clears_state(self, manager: InputManager) -> None:
        """Test keyup event clears key state."""
        # Press key
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_UP
        manager.process_events([keydown])
        assert pygame.K_UP in manager._keys_pressed

        # Release key
        keyup = Mock()
        keyup.type = pygame.KEYUP
        keyup.key = pygame.K_UP
        manager.process_events([keyup])
        assert pygame.K_UP not in manager._keys_pressed

    def test_continuous_control_pitch_up(self, manager: InputManager) -> None:
        """Test pitch up continuous control."""
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_DOWN  # Pitch up
        manager.process_events([keydown])
        manager.update(0.016)

        assert manager.state.pitch > 0.0

    def test_continuous_control_roll_left(self, manager: InputManager) -> None:
        """Test roll left continuous control."""
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_LEFT
        manager.process_events([keydown])
        manager.update(0.016)

        assert manager.state.roll < 0.0

    def test_discrete_action_throttle_increase(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test throttle increase continuous action."""
        initial_throttle = manager.state.throttle

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_PAGEUP  # Throttle increase
        manager.process_events([keydown])

        # Call update to apply continuous throttle change
        manager.update(0.016)

        # Throttle should target higher value
        assert manager._target_throttle > initial_throttle

    def test_discrete_action_gear_toggle(self, manager: InputManager) -> None:
        """Test gear toggle action."""
        assert manager.state.gear == 1.0  # Gear down

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_g
        manager.process_events([keydown])
        manager.update(0.016)

        assert manager.state.gear == 0.0  # Gear up

        # Release and press again to toggle
        keyup = Mock()
        keyup.type = pygame.KEYUP
        keyup.key = pygame.K_g
        manager.process_events([keyup])

        keydown2 = Mock()
        keydown2.type = pygame.KEYDOWN
        keydown2.key = pygame.K_g
        manager.process_events([keydown2])
        manager.update(0.016)
        assert manager.state.gear == 1.0  # Gear down again

    def test_discrete_action_flaps_down(self, manager: InputManager) -> None:
        """Test flaps down action."""
        assert manager.state.flaps == 0.0

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_RIGHTBRACKET
        manager.process_events([keydown])

        assert manager.state.flaps == pytest.approx(0.25)

    def test_brakes_released_on_keyup(self, manager: InputManager) -> None:
        """Test brakes are released when key is released."""
        # Press brakes
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_b
        manager.process_events([keydown])
        manager.update(0.016)
        assert manager.state.brakes == 1.0

        # Release brakes
        keyup = Mock()
        keyup.type = pygame.KEYUP
        keyup.key = pygame.K_b
        manager.process_events([keyup])
        manager.update(0.016)
        assert manager.state.brakes == 0.0


class TestInputManagerUpdate:
    """Test InputManager update logic."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_update_smooths_throttle(self, manager: InputManager) -> None:
        """Test throttle changes are smoothed over time."""
        manager._target_throttle = 1.0
        manager.state.throttle = 0.0

        # Update several times
        for _ in range(10):
            manager.update(0.016)

        # Throttle should have increased but not instantly
        assert 0.0 < manager.state.throttle < 1.0

    def test_update_clamps_values(self, manager: InputManager) -> None:
        """Test update clamps throttle to valid ranges."""
        manager.state.throttle = -0.5
        manager._target_throttle = -0.5

        manager.update(0.016)

        assert manager.state.throttle == 0.0

    def test_update_publishes_state_event(self, manager: InputManager, event_bus: EventBus) -> None:
        """Test update publishes input state event."""
        received_events = []

        def handler(event: InputStateEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputStateEvent, handler)
        manager.update(0.016)

        assert len(received_events) == 1
        assert isinstance(received_events[0], InputStateEvent)
        assert hasattr(received_events[0], "throttle")

    def test_update_with_multiple_keys_pressed(self, manager: InputManager) -> None:
        """Test update with multiple control keys pressed."""
        # Press pitch and roll
        pitch_key = Mock()
        pitch_key.type = pygame.KEYDOWN
        pitch_key.key = pygame.K_UP

        roll_key = Mock()
        roll_key.type = pygame.KEYDOWN
        roll_key.key = pygame.K_LEFT

        manager.process_events([pitch_key, roll_key])
        manager.update(0.016)

        assert manager.state.pitch != 0.0
        assert manager.state.roll != 0.0


class TestInputManagerActions:
    """Test InputManager action queries."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_is_action_pressed(self, manager: InputManager) -> None:
        """Test checking if action is currently pressed."""
        assert not manager.is_action_pressed(InputAction.PITCH_UP)

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_DOWN  # Pitch up
        manager.process_events([keydown])

        assert manager.is_action_pressed(InputAction.PITCH_UP)

    def test_is_action_just_pressed(self, manager: InputManager) -> None:
        """Test checking if action was just pressed."""
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_g  # Gear toggle
        manager.process_events([keydown])

        assert manager.is_action_just_pressed(InputAction.GEAR_TOGGLE)

        # Next frame it should not be "just pressed"
        manager.process_events([])
        assert not manager.is_action_just_pressed(InputAction.GEAR_TOGGLE)


class TestInputManagerDeadzone:
    """Test InputManager deadzone handling."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_apply_deadzone_inside_deadzone(self, manager: InputManager) -> None:
        """Test values inside deadzone return zero."""
        result = manager._apply_deadzone(0.05)
        assert result == 0.0

        result = manager._apply_deadzone(-0.05)
        assert result == 0.0

    def test_apply_deadzone_outside_deadzone(self, manager: InputManager) -> None:
        """Test values outside deadzone are remapped."""
        # Value outside deadzone should be non-zero
        result = manager._apply_deadzone(0.5)
        assert result != 0.0

        # Should preserve sign
        result_positive = manager._apply_deadzone(0.5)
        result_negative = manager._apply_deadzone(-0.5)
        assert result_positive > 0.0
        assert result_negative < 0.0

    def test_apply_deadzone_at_boundary(self, manager: InputManager) -> None:
        """Test value exactly at deadzone boundary."""
        # Exactly at deadzone (0.1)
        result = manager._apply_deadzone(0.1)
        # Should be zero (at boundary)
        assert abs(result) < 0.001

    def test_apply_deadzone_full_range(self, manager: InputManager) -> None:
        """Test full range input."""
        result = manager._apply_deadzone(1.0)
        assert result == pytest.approx(1.0)

        result = manager._apply_deadzone(-1.0)
        assert result == pytest.approx(-1.0)


class TestInputManagerThrottle:
    """Test InputManager throttle handling."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_throttle_full(self, manager: InputManager) -> None:
        """Test throttle increase moves towards full."""
        # Start at partial throttle
        manager._target_throttle = 0.5

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_PAGEUP  # Throttle increase
        manager.process_events([keydown])

        # Multiple updates to reach full throttle
        for _ in range(50):  # 50 * 0.01 = 0.5, should reach 1.0
            manager.update(0.016)

        assert manager._target_throttle == 1.0

    def test_throttle_idle(self, manager: InputManager) -> None:
        """Test throttle idle action."""
        manager.state.throttle = 0.8

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_PAGEDOWN  # Changed from K_i to K_PAGEDOWN
        manager.process_events([keydown])

        assert manager._target_throttle == 0.0

    def test_throttle_increment_multiple_times(self, manager: InputManager) -> None:
        """Test incrementing throttle multiple times with update loop."""
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_PAGEUP  # Throttle increase
        manager.process_events([keydown])

        # Call update 5 times to increment throttle continuously
        for _ in range(5):
            manager.update(0.016)

        # Should be 5 * 0.01 = 0.05 (changed from 0.25)
        assert manager._target_throttle == pytest.approx(0.05)

    def test_throttle_clamps_at_maximum(self, manager: InputManager) -> None:
        """Test throttle clamps at 1.0."""
        manager._target_throttle = 0.98

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_PAGEUP  # Throttle increase
        manager.process_events([keydown])

        # Call update multiple times to exceed 1.0
        for _ in range(5):
            manager.update(0.016)

        assert manager._target_throttle == 1.0


class TestInputManagerEventPublishing:
    """Test InputManager event publishing."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def manager(self, event_bus: EventBus) -> InputManager:
        """Create input manager."""
        return InputManager(event_bus)

    def test_publishes_input_action_events(
        self, manager: InputManager, event_bus: EventBus
    ) -> None:
        """Test discrete actions publish INPUT_ACTION events."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        # Trigger gear toggle
        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_g
        manager.process_events([keydown])

        # Should have published InputActionEvent
        assert len(received_events) > 0
        assert received_events[0].action == InputAction.GEAR_TOGGLE.value

    def test_publishes_tts_action_events(self, manager: InputManager, event_bus: EventBus) -> None:
        """Test TTS actions publish events."""
        received_events = []

        def handler(event: InputActionEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(InputActionEvent, handler)

        keydown = Mock()
        keydown.type = pygame.KEYDOWN
        keydown.key = pygame.K_n  # TTS next (changed from T to N)
        manager.process_events([keydown])

        assert len(received_events) > 0
        assert received_events[0].action == InputAction.TTS_NEXT.value
