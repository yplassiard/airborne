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

    def next_state(self) -> str:
        """Advance to next state (wraps around for discrete, increments for continuous)."""
        if self.is_continuous():
            self.continuous_value = min(self.max_value, self.continuous_value + self.step_size)
        elif self.states:
            self.current_state_index = (self.current_state_index + 1) % len(self.states)
        return self.get_current_state()

    def previous_state(self) -> str:
        """Go to previous state (wraps around for discrete, decrements for continuous)."""
        if self.is_continuous():
            self.continuous_value = max(self.min_value, self.continuous_value - self.step_size)
        elif self.states:
            self.current_state_index = (self.current_state_index - 1) % len(self.states)
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

        # Announce state change
        self._speak(f"{control.name}, {current_state}")

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

        # Announce button press
        self._speak(f"{control.name}, pressed")

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
            self._speak(f"Panel: {panel.name}")

    def _announce_control(self) -> None:
        """Announce current control via TTS."""
        control = self.get_current_control()
        if control:
            state = control.get_current_state()
            self._speak(f"{control.name}, {state}")

    def _speak(self, text: str) -> None:
        """Speak text via TTS.

        Args:
            text: Text to speak.
        """
        if not self.context:
            return

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

    def handle_key_press(self, key: int, mod: int) -> bool:
        """Handle keyboard input for panel navigation and control.

        Args:
            key: Pygame key constant
            mod: Pygame keyboard modifier flags (KMOD_SHIFT, KMOD_CTRL, etc.)

        Returns:
            True if key was handled, False otherwise.
        """
        import pygame  # Import here to avoid circular dependency

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

        # Get current panel to determine which control mappings to use
        panel = self.get_current_panel()
        if not panel:
            return False

        # Control key mappings based on current panel
        # These match the config/keymaps/cessna172_panels.yaml file

        # INSTRUMENT PANEL (Panel 0)
        if self.current_panel_index == 0:
            if key == pygame.K_m:
                control = self.get_control_by_id("master_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_a:
                control = self.get_control_by_id("avionics_master_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_b:
                control = self.get_control_by_id("beacon_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_n:
                control = self.get_control_by_id("nav_lights_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_s:
                control = self.get_control_by_id("strobe_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_t:
                control = self.get_control_by_id("taxi_light_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True
            elif key == pygame.K_l:
                control = self.get_control_by_id("landing_light_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

        # PEDESTAL (Panel 1)
        elif self.current_panel_index == 1:
            # Mixture lever (Shift+M next, Ctrl+M previous)
            if key == pygame.K_m:
                control = self.get_control_by_id("mixture_lever")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()
                    self._on_control_state_changed(control)
                    return True

            # Carburetor heat (C toggles)
            elif key == pygame.K_c:
                control = self.get_control_by_id("carburetor_heat_lever")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

            # Throttle (Shift+T increase, Ctrl+T decrease)
            elif key == pygame.K_t:
                control = self.get_control_by_id("throttle_lever")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()  # Increase
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()  # Decrease
                    self._on_control_state_changed(control)
                    return True

            # Fuel selector (Shift+F next, Ctrl+F previous)
            elif key == pygame.K_f:
                control = self.get_control_by_id("fuel_selector_valve")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()
                    self._on_control_state_changed(control)
                    return True

            # Fuel shutoff valve (V toggles)
            elif key == pygame.K_v:
                control = self.get_control_by_id("fuel_shutoff_valve")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

            # Fuel pump (P toggles)
            elif key == pygame.K_p:
                control = self.get_control_by_id("fuel_pump_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

            # Primer pump (R presses)
            elif key == pygame.K_r:
                control = self.get_control_by_id("primer_pump")
                if control:
                    self._trigger_button(control)
                    return True

        # ENGINE CONTROLS (Panel 2)
        elif self.current_panel_index == 2:
            # Magnetos (Shift+G next, Ctrl+G previous)
            if key == pygame.K_g:
                control = self.get_control_by_id("magneto_switch")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()
                    self._on_control_state_changed(control)
                    return True

            # Starter button (S presses)
            elif key == pygame.K_s:
                control = self.get_control_by_id("starter_button")
                if control:
                    self._trigger_button(control)
                    return True

        # OVERHEAD PANEL (Panel 3)
        elif self.current_panel_index == 3:
            # Pitot heat (H toggles)
            if key == pygame.K_h:
                control = self.get_control_by_id("pitot_heat_switch")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

        # FLIGHT CONTROLS (Panel 4)
        elif self.current_panel_index == 4:
            # Flaps (Shift+F next, Ctrl+F previous)
            if key == pygame.K_f:
                control = self.get_control_by_id("flaps_lever")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()
                    self._on_control_state_changed(control)
                    return True

            # Elevator trim (Shift+E next, Ctrl+E previous)
            elif key == pygame.K_e:
                control = self.get_control_by_id("elevator_trim_wheel")
                if control:
                    if mod & pygame.KMOD_SHIFT:
                        control.next_state()
                    elif mod & pygame.KMOD_CTRL:
                        control.previous_state()
                    self._on_control_state_changed(control)
                    return True

            # Parking brake (B toggles)
            elif key == pygame.K_b:
                control = self.get_control_by_id("parking_brake_lever")
                if control:
                    control.next_state()
                    self._on_control_state_changed(control)
                    return True

        return False
