"""Control panel plugin for AirBorne flight simulator.

Provides hierarchical panel navigation with switches, buttons, knobs, and levers.
All controls are audio-navigable with TTS descriptions and send state changes
to target plugins via messages.

Typical usage:
    The control panel plugin is loaded automatically and provides panel
    navigation and control services to the simulation.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageTopic
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType

logger = get_logger(__name__)


class ControlType(Enum):
    """Types of panel controls."""

    SWITCH = "switch"  # Two-position switch (ON/OFF)
    BUTTON = "button"  # Momentary button
    KNOB = "knob"  # Rotary knob with discrete positions
    LEVER = "lever"  # Lever with multiple positions
    SLIDER = "slider"  # Continuous slider


@dataclass
class PanelControl:
    """Single control on a panel.

    Attributes:
        id: Unique identifier for this control
        name: Display name (announced via TTS)
        control_type: Type of control (switch, button, etc.)
        states: List of possible states (e.g., ["OFF", "ON"]) - used for discrete controls
        current_state_index: Index of current state (for discrete controls)
        target_plugin: Plugin that handles this control
        message_topic: Message topic to publish on state change
        description: Optional description for TTS
        min_value: Minimum value for continuous controls (SLIDER)
        max_value: Maximum value for continuous controls (SLIDER)
        continuous_value: Current value for continuous controls (SLIDER)
        step_size: Step size for continuous control adjustments
    """

    id: str
    name: str
    control_type: ControlType
    states: list[str] = field(default_factory=list)
    current_state_index: int = 0
    target_plugin: str = ""
    message_topic: str = ""
    description: str = ""
    # Continuous control fields (for SLIDER type)
    min_value: float = 0.0
    max_value: float = 100.0
    continuous_value: float = 0.0
    step_size: float = 1.0

    def is_continuous(self) -> bool:
        """Check if this is a continuous control.

        Returns:
            True if control type is SLIDER and has no discrete states.
        """
        return self.control_type == ControlType.SLIDER and not self.states

    def get_current_state(self) -> str:
        """Get current state value.

        Returns:
            For discrete controls: state name from states list.
            For continuous controls: formatted percentage value.
        """
        if self.is_continuous():
            return f"{self.continuous_value:.1f}%"
        if 0 <= self.current_state_index < len(self.states):
            return self.states[self.current_state_index]
        return "UNKNOWN"

    def can_increase(self) -> bool:
        """Check if control can be increased.

        Returns:
            True if control is not at maximum value.
        """
        if self.is_continuous():
            return self.continuous_value < self.max_value
        if self.states:
            return self.current_state_index < len(self.states) - 1
        return False

    def can_decrease(self) -> bool:
        """Check if control can be decreased.

        Returns:
            True if control is not at minimum value.
        """
        if self.is_continuous():
            return self.continuous_value > self.min_value
        if self.states:
            return self.current_state_index > 0
        return False

    def next_state(self) -> str:
        """Advance to next state (does NOT wrap around).

        Returns:
            Current state after change (or unchanged if at max).
        """
        if self.is_continuous():
            self.continuous_value = min(self.max_value, self.continuous_value + self.step_size)
        elif self.states and self.can_increase():
            self.current_state_index += 1
        return self.get_current_state()

    def previous_state(self) -> str:
        """Go to previous state (does NOT wrap around).

        Returns:
            Current state after change (or unchanged if at min).
        """
        if self.is_continuous():
            self.continuous_value = max(self.min_value, self.continuous_value - self.step_size)
        elif self.states and self.can_decrease():
            self.current_state_index -= 1
        return self.get_current_state()

    def set_state(self, state: str) -> bool:
        """Set state by name.

        Args:
            state: State name to set (or numeric value for continuous controls).

        Returns:
            True if state was set successfully.
        """
        # For continuous controls, try to parse as number
        if self.is_continuous():
            try:
                value = float(state.rstrip("%"))
                return self.set_value(value)
            except ValueError:
                return False

        # For discrete controls, find state in list
        try:
            self.current_state_index = self.states.index(state)
            return True
        except ValueError:
            return False

    def set_state_index(self, index: int) -> bool:
        """Set state by index.

        Args:
            index: State index to set.

        Returns:
            True if index is valid.
        """
        if 0 <= index < len(self.states):
            self.current_state_index = index
            return True
        return False

    def set_value(self, value: float) -> bool:
        """Set continuous control value.

        Args:
            value: Value to set (must be within min_value to max_value range).

        Returns:
            True if value was set successfully.
        """
        if not self.is_continuous():
            return False

        if self.min_value <= value <= self.max_value:
            self.continuous_value = value
            return True
        return False

    def get_value(self) -> float:
        """Get continuous control value.

        Returns:
            Current continuous value, or 0.0 if not a continuous control.
        """
        if self.is_continuous():
            return self.continuous_value
        return 0.0


@dataclass
class Panel:
    """Panel containing multiple controls.

    Attributes:
        name: Panel name (e.g., "Instrument Panel")
        description: Brief description
        controls: List of PanelControl objects
    """

    name: str
    description: str = ""
    controls: list[PanelControl] = field(default_factory=list)


class ControlPanelPlugin(IPlugin):
    """Control panel plugin for hierarchical panel navigation.

    Provides keyboard-navigable panels with switches, buttons, knobs, and levers.
    All controls announce their state via TTS and send messages to target plugins.

    Components provided:
    - control_panel_manager: ControlPanelPlugin instance for panel operations
    """

    def __init__(self) -> None:
        """Initialize control panel plugin."""
        self.context: PluginContext | None = None
        self.panels: list[Panel] = []
        self.current_panel_index: int = 0
        self.current_control_index: int = 0

        # Control state tracking for SYSTEM_STATE_CHANGED messages
        self._control_states: dict[str, Any] = {}

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="control_panel_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.FEATURE,
            dependencies=[],
            provides=["control_panel_manager"],
            optional=False,
            update_priority=60,  # After checklist system
            requires_physics=False,
            description="Hierarchical panel navigation with audio feedback",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the control panel plugin."""
        self.context = context

        # Load panel definitions from config
        panel_config = context.config.get("panels", {})
        panel_file = panel_config.get("definition", "config/panels/cessna172_panel.yaml")

        # Load panels from file
        self._load_panels(Path(panel_file))

        # Register in component registry
        if context.plugin_registry:
            context.plugin_registry.register("control_panel_manager", self)

        logger.info(
            "Control panel plugin initialized with %d panels, %d controls",
            len(self.panels),
            sum(len(p.controls) for p in self.panels),
        )

    def update(self, dt: float) -> None:
        """Update control panel system."""
        # Panel system is event-driven, no continuous updates needed
        pass

    def shutdown(self) -> None:
        """Shutdown the control panel plugin."""
        # Unregister component
        if self.context and self.context.plugin_registry:
            self.context.plugin_registry.unregister("control_panel_manager")

        logger.info("Control panel plugin shutdown")

    def handle_message(self, message: Any) -> None:
        """Handle incoming messages.

        Args:
            message: Message from another plugin.
        """
        # Control panel is primarily command-driven rather than message-driven
        # Future: Could handle external control state requests here
        pass

    def _load_panels(self, panel_file: Path) -> None:
        """Load panel definitions from YAML file."""
        if not panel_file.exists():
            logger.warning("Panel definition file does not exist: %s", panel_file)
            return

        try:
            with open(panel_file) as f:
                data = yaml.safe_load(f)

            if not data or "panels" not in data:
                return

            for panel_data in data["panels"]:
                panel = self._parse_panel(panel_data)
                self.panels.append(panel)
                logger.info("Loaded panel: %s with %d controls", panel.name, len(panel.controls))

        except Exception as e:
            logger.error("Failed to load panels from %s: %s", panel_file, e)

    def _parse_panel(self, data: dict) -> Panel:
        """Parse panel from YAML data."""
        controls = []
        for control_data in data.get("controls", []):
            control = PanelControl(
                id=control_data["id"],
                name=control_data["name"],
                control_type=ControlType(control_data["type"]),
                states=control_data.get("states", []),
                current_state_index=control_data.get("default_index", 0),
                target_plugin=control_data.get("target_plugin", ""),
                message_topic=control_data.get("message_topic", ""),
                description=control_data.get("description", ""),
                # Continuous control fields
                min_value=control_data.get("min_value", 0.0),
                max_value=control_data.get("max_value", 100.0),
                continuous_value=control_data.get("default_value", 0.0),
                step_size=control_data.get("step_size", 1.0),
            )
            controls.append(control)

        return Panel(
            name=data["name"],
            description=data.get("description", ""),
            controls=controls,
        )

    def navigate_to_panel(self, panel_index: int) -> bool:
        """Navigate to a specific panel.

        Args:
            panel_index: Index of the panel to navigate to.

        Returns:
            True if navigation was successful.
        """
        if 0 <= panel_index < len(self.panels):
            self.current_panel_index = panel_index
            self.current_control_index = 0
            self._announce_panel()
            return True
        return False

    def next_panel(self) -> None:
        """Navigate to the next panel."""
        if self.panels:
            self.current_panel_index = (self.current_panel_index + 1) % len(self.panels)
            self.current_control_index = 0
            self._announce_panel()

    def previous_panel(self) -> None:
        """Navigate to the previous panel."""
        if self.panels:
            self.current_panel_index = (self.current_panel_index - 1) % len(self.panels)
            self.current_control_index = 0
            self._announce_panel()

    def next_control(self) -> None:
        """Navigate to the next control on current panel."""
        panel = self.get_current_panel()
        if panel and panel.controls:
            self.current_control_index = (self.current_control_index + 1) % len(panel.controls)
            self._announce_control()

    def previous_control(self) -> None:
        """Navigate to the previous control on current panel."""
        panel = self.get_current_panel()
        if panel and panel.controls:
            self.current_control_index = (self.current_control_index - 1) % len(panel.controls)
            self._announce_control()

    def activate_current_control(self) -> None:
        """Activate/toggle the current control."""
        control = self.get_current_control()
        if not control:
            return

        # Change control state
        if control.control_type == ControlType.BUTTON:
            # Buttons are momentary - trigger action
            self._trigger_button(control)
        else:
            # Switches, levers, knobs - advance to next state
            control.next_state()
            self._on_control_state_changed(control)

    def set_control_state(self, control_id: str, state: str) -> bool:
        """Set a control's state by ID.

        Args:
            control_id: ID of the control to set.
            state: State name to set.

        Returns:
            True if control was found and state was set.
        """
        for panel in self.panels:
            for control in panel.controls:
                if control.id == control_id:
                    if control.set_state(state):
                        self._on_control_state_changed(control)
                        return True
                    return False
        return False

    def get_current_panel(self) -> Panel | None:
        """Get the currently selected panel."""
        if 0 <= self.current_panel_index < len(self.panels):
            return self.panels[self.current_panel_index]
        return None

    def get_current_control(self) -> PanelControl | None:
        """Get the currently selected control."""
        panel = self.get_current_panel()
        if panel and 0 <= self.current_control_index < len(panel.controls):
            return panel.controls[self.current_control_index]
        return None

    def get_control_by_id(self, control_id: str) -> PanelControl | None:
        """Get a control by its ID.

        Args:
            control_id: ID of the control to find.

        Returns:
            PanelControl if found, None otherwise.
        """
        for panel in self.panels:
            for control in panel.controls:
                if control.id == control_id:
                    return control
        return None

    def _on_control_state_changed(self, control: PanelControl) -> None:
        """Handle control state change.

        Args:
            control: The control that changed state.
        """
        if not self.context:
            return

        current_state = control.get_current_state()

        # Update internal state tracking
        self._update_control_state(control.id, control.target_plugin, current_state)

        # Play click sound for switches, knobs, and sliders
        if control.control_type in (ControlType.SWITCH, ControlType.KNOB, ControlType.SLIDER):
            self.context.message_queue.publish(
                Message(
                    sender="control_panel_plugin",
                    recipients=["audio_plugin"],
                    topic="audio.play_click",
                    data={"control_type": control.control_type.value},
                    priority=MessagePriority.HIGH,
                )
            )

        # Announce state change using pre-recorded messages if available
        self._announce_control_state(control, current_state)

        # Send message to target plugin
        if control.target_plugin and control.message_topic:
            message_data: dict[str, Any] = {
                "control_id": control.id,
                "control_name": control.name,
                "state": current_state,
            }

            # Add continuous value or discrete index
            if control.is_continuous():
                message_data["value"] = control.continuous_value
                message_data["min_value"] = control.min_value
                message_data["max_value"] = control.max_value
            else:
                message_data["state_index"] = control.current_state_index

            self.context.message_queue.publish(
                Message(
                    sender="control_panel_plugin",
                    recipients=[control.target_plugin],
                    topic=control.message_topic,
                    data=message_data,
                    priority=MessagePriority.HIGH,
                )
            )

        # Publish system state change for checklist verification
        self._publish_system_state()

    def _trigger_button(self, control: PanelControl) -> None:
        """Trigger a momentary button.

        Args:
            control: The button control.
        """
        if not self.context:
            return

        # Play click sound for button press
        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["audio_plugin"],
                topic="audio.play_click",
                data={"control_type": "button"},
                priority=MessagePriority.HIGH,
            )
        )

        # Announce button press using MSG_* format
        # Build message keys like MSG_PRIMER_PUMP, MSG_PRIMER_PUMP_PRESSED
        control_key_base = control.id.upper().replace("_SWITCH", "").replace("_LEVER", "")
        control_key_base = control_key_base.replace("_BUTTON", "").replace("_VALVE", "")
        control_msg_key = f"MSG_{control_key_base}"
        control_state_msg_key = f"{control_msg_key}_PRESSED"

        self._speak_sequence([control_msg_key, control_state_msg_key])

        # Send button press message
        if control.target_plugin and control.message_topic:
            self.context.message_queue.publish(
                Message(
                    sender="control_panel_plugin",
                    recipients=[control.target_plugin],
                    topic=control.message_topic,
                    data={
                        "control_id": control.id,
                        "control_name": control.name,
                        "action": "pressed",
                    },
                    priority=MessagePriority.HIGH,
                )
            )

    def _update_control_state(self, control_id: str, plugin: str, state: str) -> None:
        """Update internal control state tracking.

        Args:
            control_id: Control identifier.
            plugin: Target plugin name.
            state: New state value.
        """
        # Create nested dict structure: {plugin: {control: state}}
        if plugin not in self._control_states:
            self._control_states[plugin] = {}

        # Extract control name from ID (e.g., "master_switch" -> "master")
        control_name = control_id.replace("_switch", "").replace("_", ".")
        self._control_states[plugin][control_name] = state

    def _publish_system_state(self) -> None:
        """Publish system state for checklist verification."""
        if not self.context:
            return

        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["*"],
                topic=MessageTopic.SYSTEM_STATE_CHANGED,
                data={"state": self._control_states},
                priority=MessagePriority.NORMAL,
            )
        )

    def _announce_panel(self) -> None:
        """Announce current panel via TTS."""
        panel = self.get_current_panel()
        if panel:
            # Use pre-recorded panel announcement messages
            from airborne.audio.tts.speech_messages import (
                MSG_PANEL_ENGINE_CONTROLS,
                MSG_PANEL_FLIGHT_CONTROLS,
                MSG_PANEL_INSTRUMENT_PANEL,
                MSG_PANEL_OVERHEAD_PANEL,
                MSG_PANEL_PEDESTAL,
            )

            panel_name_to_msg = {
                "Instrument Panel": MSG_PANEL_INSTRUMENT_PANEL,
                "Pedestal": MSG_PANEL_PEDESTAL,
                "Engine Controls": MSG_PANEL_ENGINE_CONTROLS,
                "Overhead Panel": MSG_PANEL_OVERHEAD_PANEL,
                "Flight Controls": MSG_PANEL_FLIGHT_CONTROLS,
            }

            msg_id = panel_name_to_msg.get(panel.name)
            if msg_id:
                self._speak(msg_id)
            else:
                # Fallback to dynamic speech if no pre-recorded message
                self._speak(f"Panel: {panel.name}")

    def _announce_control(self) -> None:
        """Announce current control via TTS."""
        control = self.get_current_control()
        if control:
            state = control.get_current_state()
            self._announce_control_state(control, state)

    def _announce_control_state(self, control: PanelControl, state: str) -> None:
        """Announce control and its state using pre-recorded messages.

        Args:
            control: The control to announce.
            state: The current state value.
        """
        # Build message keys for pre-recorded announcements
        # Convert control ID to message key base (e.g., "master_switch" -> "MSG_MASTER_SWITCH")
        control_key_base = control.id.upper().replace("_SWITCH", "").replace("_LEVER", "")
        control_key_base = control_key_base.replace("_BUTTON", "").replace("_VALVE", "")
        control_msg_key = f"MSG_{control_key_base}"

        # For continuous controls (sliders), only announce the control name without state
        # since the numeric values change continuously and we don't have MP3s for all values
        if control.is_continuous():
            logger.debug(f"Announcing continuous control: {control.id} -> [{control_msg_key}]")
            self._speak(control_msg_key)
            return

        # Convert state to message key (e.g., "ON" -> "MSG_MASTER_SWITCH_ON")
        # Handle boolean values (True/False -> ON/OFF)
        state_str = ("ON" if state else "OFF") if isinstance(state, bool) else str(state)
        state_normalized = state_str.upper().replace(" ", "_").replace("%", "")
        control_state_msg_key = f"{control_msg_key}_{state_normalized}"

        # Always use pre-recorded messages - no fallback to dynamic text
        # The TTS provider will log warnings if keys don't exist
        # If messages are missing, they need to be generated with scripts/generate_speech.py
        logger.debug(
            f"Announcing control: {control.id} -> [{control_msg_key}, {control_state_msg_key}]"
        )
        self._speak_sequence([control_msg_key, control_state_msg_key])

    def _speak(self, text: str) -> None:
        """Speak text via TTS.

        Args:
            text: Text to speak (message key or dynamic text).
        """
        if not self.context:
            return

        # Interrupt any ongoing cockpit speech before speaking
        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["tts_provider"],
                topic=MessageTopic.TTS_INTERRUPT,
                data={},
                priority=MessagePriority.HIGH,
            )
        )

        # Publish TTS message
        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["tts_provider"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": text, "priority": "normal"},
                priority=MessagePriority.NORMAL,
            )
        )

    def _speak_sequence(self, message_keys: list[str]) -> None:
        """Speak a sequence of pre-recorded message keys.

        Args:
            message_keys: List of message keys to speak in sequence.
        """
        if not self.context:
            return

        # Interrupt any ongoing cockpit speech before speaking
        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["tts_provider"],
                topic=MessageTopic.TTS_INTERRUPT,
                data={},
                priority=MessagePriority.HIGH,
            )
        )

        # Send the list of message keys to the TTS provider
        # The audio provider's speak() method handles lists of keys
        self.context.message_queue.publish(
            Message(
                sender="control_panel_plugin",
                recipients=["tts_provider"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_keys, "priority": "normal"},
                priority=MessagePriority.NORMAL,
            )
        )

    def list_panels(self) -> list[str]:
        """List all panel names.

        Returns:
            List of panel names.
        """
        return [panel.name for panel in self.panels]

    def get_panel_by_name(self, name: str) -> Panel | None:
        """Get a panel by name.

        Args:
            name: Panel name to find.

        Returns:
            Panel if found, None otherwise.
        """
        for panel in self.panels:
            if panel.name == name:
                return panel
        return None

    def _handle_control_key(self, control: PanelControl, mod: int) -> bool:
        """Handle key press for a control with new behavior.

        Args:
            control: The control to operate
            mod: Pygame keyboard modifier flags

        Returns:
            True if key was handled

        Behavior:
            - No modifiers: Announce current state (no change)
            - Shift: Increase/turn on (only if not at max)
            - Ctrl: Decrease/turn off (only if not at min)
        """
        import pygame

        # Check modifiers
        has_shift = bool(mod & pygame.KMOD_SHIFT)
        has_ctrl = bool(mod & pygame.KMOD_CTRL)

        # No modifiers: Just announce current state
        if not has_shift and not has_ctrl:
            state = control.get_current_state()
            self._announce_control_state(control, state)
            return True

        # Shift: Increase/turn on (only if can increase)
        if has_shift and not has_ctrl:
            if control.can_increase():
                control.next_state()
                self._on_control_state_changed(control)
            return True

        # Ctrl: Decrease/turn off (only if can decrease)
        if has_ctrl and not has_shift:
            if control.can_decrease():
                control.previous_state()
                self._on_control_state_changed(control)
            return True

        return False

    def handle_key_press(self, key: int, mod: int) -> bool:
        """Handle keyboard input for panel navigation and control.

        Args:
            key: Pygame key constant
            mod: Pygame keyboard modifier flags (KMOD_SHIFT, KMOD_CTRL, etc.)

        Returns:
            True if key was handled, False otherwise.
        """
        import pygame  # Import here to avoid circular dependency

        # Skip Ctrl+Q - let it fall through to app quit handler
        if mod & pygame.KMOD_CTRL and key == pygame.K_q:
            return False

        # Check for panel navigation (Ctrl+1-5)
        if mod & pygame.KMOD_CTRL:
            if key == pygame.K_1:
                return self.navigate_to_panel(0)
            elif key == pygame.K_2:
                return self.navigate_to_panel(1)
            elif key == pygame.K_3:
                return self.navigate_to_panel(2)
            elif key == pygame.K_4:
                return self.navigate_to_panel(3)
            elif key == pygame.K_5:
                return self.navigate_to_panel(4)
            # For other Ctrl+ combinations, check if they're panel-specific
            # If not handled below, consume them to prevent fallthrough

        # Get current panel to determine which control mappings to use
        panel = self.get_current_panel()
        if not panel:
            return False

        # Control key mappings based on current panel
        # These match the config/keymaps/cessna172_panels.yaml file

        # INSTRUMENT PANEL (Panel 0)
        if self.current_panel_index == 0:
            control_key_map = {
                pygame.K_m: "master_switch",
                pygame.K_a: "avionics_master_switch",
                pygame.K_b: "beacon_switch",
                pygame.K_n: "nav_lights_switch",
                pygame.K_s: "strobe_switch",
                pygame.K_t: "taxi_light_switch",
                pygame.K_l: "landing_light_switch",
            }

            if key in control_key_map:
                control = self.get_control_by_id(control_key_map[key])
                if control:
                    return self._handle_control_key(control, mod)

        # PEDESTAL (Panel 1)
        elif self.current_panel_index == 1:
            control_key_map = {
                pygame.K_m: "mixture_lever",
                pygame.K_c: "carburetor_heat_lever",
                pygame.K_t: "throttle_lever",
                pygame.K_f: "fuel_selector_valve",
                pygame.K_v: "fuel_shutoff_valve",
                pygame.K_p: "fuel_pump_switch",
            }

            if key in control_key_map:
                control = self.get_control_by_id(control_key_map[key])
                if control:
                    return self._handle_control_key(control, mod)

            # Primer pump button (any modifier triggers press)
            if key == pygame.K_r:
                control = self.get_control_by_id("primer_pump")
                if control:
                    self._trigger_button(control)
                    return True

        # ENGINE CONTROLS (Panel 2)
        elif self.current_panel_index == 2:
            control_key_map = {
                pygame.K_g: "magneto_switch",
            }

            if key in control_key_map:
                control = self.get_control_by_id(control_key_map[key])
                if control:
                    return self._handle_control_key(control, mod)

            # Starter button (any modifier triggers press)
            if key == pygame.K_s:
                control = self.get_control_by_id("starter_button")
                if control:
                    self._trigger_button(control)
                    return True

        # OVERHEAD PANEL (Panel 3)
        elif self.current_panel_index == 3:
            control_key_map = {
                pygame.K_h: "pitot_heat_switch",
            }

            if key in control_key_map:
                control = self.get_control_by_id(control_key_map[key])
                if control:
                    return self._handle_control_key(control, mod)

        # FLIGHT CONTROLS (Panel 4)
        elif self.current_panel_index == 4:
            control_key_map = {
                pygame.K_f: "flaps_lever",
                pygame.K_e: "elevator_trim_wheel",
                pygame.K_b: "parking_brake_lever",
            }

            if key in control_key_map:
                control = self.get_control_by_id(control_key_map[key])
                if control:
                    return self._handle_control_key(control, mod)

        # Allow certain keys to fall through to InputManager (flight controls, menus, etc.)
        passthrough_keys = {
            # Flight controls (arrow keys, home/end for throttle, etc.)
            pygame.K_UP,
            pygame.K_DOWN,
            pygame.K_LEFT,
            pygame.K_RIGHT,
            pygame.K_HOME,
            pygame.K_END,
            pygame.K_PAGEUP,
            pygame.K_PAGEDOWN,
            pygame.K_COMMA,  # Yaw left
            pygame.K_e,  # Yaw right (unless in Flight Controls panel)
            # Brakes
            pygame.K_b,  # Brakes (unless in Flight Controls or Instrument Panel)
            # Brackets for flaps (different from panel flaps control)
            pygame.K_LEFTBRACKET,
            pygame.K_RIGHTBRACKET,
            # Menu keys
            pygame.K_F1,  # ATC menu
            pygame.K_F2,  # Checklist menu
            pygame.K_TAB,  # Menu toggle
            pygame.K_RETURN,  # Menu select
            pygame.K_ESCAPE,  # Menu back
            # Instrument readout keys
            pygame.K_s,  # Speed (unless in Engine Controls panel)
            pygame.K_l,  # Altitude (unless in Instrument Panel)
            pygame.K_h,  # Heading (unless in Overhead Panel)
            pygame.K_w,  # Vertical speed
            pygame.K_t,  # Attitude (unless in Instrument Panel)
            # TTS controls
            pygame.K_n,  # Next (unless in Instrument Panel)
            pygame.K_r,  # Repeat (unless in Pedestal)
            pygame.K_i,  # Interrupt
            # View controls
            pygame.K_v,  # View next (unless in Pedestal)
            pygame.K_c,  # View prev (unless in Pedestal)
            # ATC number keys
            pygame.K_1,
            pygame.K_2,
            pygame.K_3,
            pygame.K_4,
            pygame.K_5,
            pygame.K_6,
            pygame.K_7,
            pygame.K_8,
            pygame.K_9,
            # System
            pygame.K_SPACE,  # Pause
        }

        # Check if this key should pass through
        # However, if the key was explicitly handled in a panel context above, don't pass through
        # So we only pass through keys that weren't handled by any panel

        # Keys that were handled in panel-specific code would have returned True already
        # So if we're here, the key wasn't handled by the current panel

        # For panel-context-aware keys: only block if they could interfere with panel controls
        # For now, block 'G' specifically since it conflicts with Engine Controls panel magnetos
        if key == pygame.K_g:
            # G is gear toggle in InputManager but magnetos in Engine Controls panel
            # Block it to prevent accidental gear toggle when on other panels
            return True

        # Allow other keys to pass through if they're in the passthrough list
        # Block all other keys to prevent unexpected panel interactions
        return key not in passthrough_keys
