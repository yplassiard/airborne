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
        states: List of possible states (e.g., ["OFF", "ON"])
        current_state_index: Index of current state
        target_plugin: Plugin that handles this control
        message_topic: Message topic to publish on state change
        description: Optional description for TTS
    """

    id: str
    name: str
    control_type: ControlType
    states: list[str]
    current_state_index: int = 0
    target_plugin: str = ""
    message_topic: str = ""
    description: str = ""

    def get_current_state(self) -> str:
        """Get current state value."""
        if 0 <= self.current_state_index < len(self.states):
            return self.states[self.current_state_index]
        return "UNKNOWN"

    def next_state(self) -> str:
        """Advance to next state (wraps around)."""
        if self.states:
            self.current_state_index = (self.current_state_index + 1) % len(self.states)
        return self.get_current_state()

    def previous_state(self) -> str:
        """Go to previous state (wraps around)."""
        if self.states:
            self.current_state_index = (self.current_state_index - 1) % len(self.states)
        return self.get_current_state()

    def set_state(self, state: str) -> bool:
        """Set state by name.

        Args:
            state: State name to set.

        Returns:
            True if state was set successfully.
        """
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
        if self.context:
            # Unregister component
            if self.context.plugin_registry:
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
            self.context.message_queue.publish(
                Message(
                    sender="control_panel_plugin",
                    recipients=[control.target_plugin],
                    topic=control.message_topic,
                    data={
                        "control_id": control.id,
                        "control_name": control.name,
                        "state": current_state,
                        "state_index": control.current_state_index,
                    },
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
