"""Checklist plugin for AirBorne flight simulator.

Provides interactive checklists with challenge-response pattern, auto-verification,
and TTS announcements for procedural training and operational safety.

Typical usage:
    The checklist plugin is loaded automatically and provides checklist
    services to the simulation.
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


class ChecklistItemState(Enum):
    """State of a checklist item."""

    PENDING = "pending"  # Not yet started
    IN_PROGRESS = "in_progress"  # Currently active item
    COMPLETED = "completed"  # Successfully completed
    SKIPPED = "skipped"  # Manually skipped


@dataclass
class ChecklistItem:
    """Single item in a checklist.

    Attributes:
        challenge: The challenge/prompt text (e.g., "Fuel Pump")
        response: Expected response (e.g., "ON")
        verify_condition: Optional condition to auto-verify (e.g., "fuel.pump == ON")
        state: Current state of this item
        completed_by: How it was completed ("manual", "auto", or None)
    """

    challenge: str
    response: str
    verify_condition: str | None = None
    state: ChecklistItemState = ChecklistItemState.PENDING
    completed_by: str | None = None

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.challenge}... {self.response}"


@dataclass
class Checklist:
    """Complete checklist.

    Attributes:
        id: Unique identifier for this checklist
        name: Display name
        description: Brief description
        items: List of ChecklistItem objects
        current_index: Index of current item (None if not started)
    """

    id: str
    name: str
    description: str
    items: list[ChecklistItem] = field(default_factory=list)
    current_index: int | None = None

    def is_complete(self) -> bool:
        """Check if all items are completed or skipped."""
        return all(
            item.state in [ChecklistItemState.COMPLETED, ChecklistItemState.SKIPPED]
            for item in self.items
        )

    def get_current_item(self) -> ChecklistItem | None:
        """Get the current active item."""
        if self.current_index is None or self.current_index >= len(self.items):
            return None
        return self.items[self.current_index]

    def get_completion_percentage(self) -> float:
        """Get completion percentage."""
        if not self.items:
            return 100.0
        completed = sum(1 for item in self.items if item.state == ChecklistItemState.COMPLETED)
        return (completed / len(self.items)) * 100.0


class ChecklistPlugin(IPlugin):
    """Checklist plugin for interactive procedural checklists.

    Provides challenge-response checklists with auto-verification based on
    system state. Supports TTS announcements and manual completion.

    Components provided:
    - checklist_manager: ChecklistPlugin instance for checklist operations
    """

    def __init__(self) -> None:
        """Initialize checklist plugin."""
        self.context: PluginContext | None = None
        self.checklists: dict[str, Checklist] = {}
        self.active_checklist: Checklist | None = None

        # System state for auto-verification
        self._system_state: dict[str, Any] = {}

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="checklist_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.FEATURE,
            dependencies=[],
            provides=["checklist_manager"],
            optional=False,
            update_priority=50,  # Mid-range priority
            requires_physics=False,
            description="Interactive checklists with challenge-response and auto-verification",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the checklist plugin."""
        self.context = context

        # Load checklists from config
        checklist_config = context.config.get("checklists", {})
        checklist_dir = checklist_config.get("directory", "config/checklists")

        # Load checklists from directory
        self._load_checklists(Path(checklist_dir))

        # Register in component registry
        if context.plugin_registry:
            context.plugin_registry.register("checklist_manager", self)

        # Subscribe to system state updates
        context.message_queue.subscribe(MessageTopic.POSITION_UPDATED, self.handle_message)
        context.message_queue.subscribe(MessageTopic.SYSTEM_STATE_CHANGED, self.handle_message)

        logger.info("Checklist plugin initialized with %d checklists", len(self.checklists))

    def update(self, dt: float) -> None:
        """Update checklist system."""
        if not self.active_checklist or not self.context:
            return

        # Auto-verify current item if conditions met
        self._auto_verify_items()

    def shutdown(self) -> None:
        """Shutdown the checklist plugin."""
        if self.context:
            # Unsubscribe from messages
            self.context.message_queue.unsubscribe(
                MessageTopic.POSITION_UPDATED, self.handle_message
            )
            self.context.message_queue.unsubscribe(
                MessageTopic.SYSTEM_STATE_CHANGED, self.handle_message
            )

            # Unregister component
            if self.context.plugin_registry:
                self.context.plugin_registry.unregister("checklist_manager")

        logger.info("Checklist plugin shutdown")

    def handle_message(self, message: Message) -> None:
        """Handle messages from other plugins."""
        if message.topic == MessageTopic.SYSTEM_STATE_CHANGED:
            # Update system state for auto-verification
            if "state" in message.data:
                self._system_state.update(message.data["state"])

    def _load_checklists(self, checklist_dir: Path) -> None:
        """Load checklists from YAML files."""
        if not checklist_dir.exists():
            logger.warning("Checklist directory does not exist: %s", checklist_dir)
            return

        for yaml_file in checklist_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                checklist = self._parse_checklist(data)
                self.checklists[checklist.id] = checklist
                logger.info("Loaded checklist: %s", checklist.name)

            except Exception as e:
                logger.error("Failed to load checklist from %s: %s", yaml_file, e)

    def _parse_checklist(self, data: dict) -> Checklist:
        """Parse checklist from YAML data."""
        items = []
        for item_data in data.get("items", []):
            item = ChecklistItem(
                challenge=item_data["challenge"],
                response=item_data["response"],
                verify_condition=item_data.get("verify_condition"),
            )
            items.append(item)

        return Checklist(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            items=items,
        )

    def start_checklist(self, checklist_id: str) -> bool:
        """Start a checklist.

        Args:
            checklist_id: ID of the checklist to start.

        Returns:
            True if checklist started successfully.
        """
        if checklist_id not in self.checklists:
            logger.warning("Checklist not found: %s", checklist_id)
            return False

        self.active_checklist = self.checklists[checklist_id]
        self.active_checklist.current_index = 0

        # Mark first item as in progress
        if self.active_checklist.items:
            self.active_checklist.items[0].state = ChecklistItemState.IN_PROGRESS

        # Announce checklist start
        self._announce_checklist_start()

        # Announce first item
        self._announce_current_item()

        logger.info("Started checklist: %s", self.active_checklist.name)
        return True

    def complete_current_item(self, manual: bool = True) -> bool:
        """Complete the current checklist item.

        Args:
            manual: True if manually completed, False if auto-verified.

        Returns:
            True if item was completed successfully.
        """
        if not self.active_checklist:
            return False

        current_item = self.active_checklist.get_current_item()
        if not current_item:
            return False

        # Mark as completed
        current_item.state = ChecklistItemState.COMPLETED
        current_item.completed_by = "manual" if manual else "auto"

        # Announce completion
        if self.context:
            self._speak(f"{current_item.challenge}... {current_item.response}... Check")

        # Move to next item
        return self._advance_to_next_item()

    def skip_current_item(self) -> bool:
        """Skip the current checklist item.

        Returns:
            True if item was skipped successfully.
        """
        if not self.active_checklist:
            return False

        current_item = self.active_checklist.get_current_item()
        if not current_item:
            return False

        # Mark as skipped
        current_item.state = ChecklistItemState.SKIPPED

        # Announce skip
        if self.context:
            self._speak(f"{current_item.challenge}... Skipped")

        # Move to next item
        return self._advance_to_next_item()

    def _advance_to_next_item(self) -> bool:
        """Advance to the next checklist item.

        Returns:
            True if there is a next item, False if checklist is complete.
        """
        if not self.active_checklist:
            return False

        # Move to next item
        if self.active_checklist.current_index is not None:
            self.active_checklist.current_index += 1

        # Check if checklist is complete
        if self.active_checklist.current_index >= len(self.active_checklist.items):
            self._announce_checklist_complete()
            self.active_checklist = None
            return False

        # Mark new current item as in progress
        current_item = self.active_checklist.get_current_item()
        if current_item:
            current_item.state = ChecklistItemState.IN_PROGRESS
            self._announce_current_item()

        return True

    def _auto_verify_items(self) -> None:
        """Auto-verify checklist items based on system state."""
        if not self.active_checklist:
            return

        current_item = self.active_checklist.get_current_item()
        if not current_item or not current_item.verify_condition:
            return

        # Check if verify condition is met
        if self._check_verify_condition(current_item.verify_condition):
            logger.info("Auto-verified: %s", current_item.challenge)
            self.complete_current_item(manual=False)

    def _check_verify_condition(self, condition: str) -> bool:
        """Check if a verify condition is met.

        Args:
            condition: Condition string (e.g., "fuel.pump == ON")

        Returns:
            True if condition is met.
        """
        # Simple condition parser (supports "key == value" format)
        try:
            parts = condition.split("==")
            if len(parts) != 2:
                return False

            key = parts[0].strip()
            expected_value = parts[1].strip().strip("\"'")

            # Check system state
            actual_value = self._get_nested_value(self._system_state, key)
            return str(actual_value).upper() == expected_value.upper()

        except Exception as e:
            logger.warning("Failed to check verify condition %s: %s", condition, e)
            return False

    def _get_nested_value(self, data: dict, key: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        keys = key.split(".")
        value = data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return None
        return value

    def _announce_checklist_start(self) -> None:
        """Announce checklist start via TTS."""
        if not self.active_checklist or not self.context:
            return

        self._speak(f"Starting checklist: {self.active_checklist.name}")

    def _announce_current_item(self) -> None:
        """Announce current checklist item via TTS."""
        if not self.active_checklist or not self.context:
            return

        current_item = self.active_checklist.get_current_item()
        if current_item:
            self._speak(f"{current_item.challenge}?")

    def _announce_checklist_complete(self) -> None:
        """Announce checklist completion via TTS."""
        if not self.active_checklist or not self.context:
            return

        completion = self.active_checklist.get_completion_percentage()
        self._speak(
            f"Checklist {self.active_checklist.name} complete. {completion:.0f} percent completed."
        )

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
                sender="checklist_plugin",
                recipients=["tts_provider"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": text, "priority": "high"},
                priority=MessagePriority.HIGH,
            )
        )

    def get_active_checklist(self) -> Checklist | None:
        """Get the currently active checklist."""
        return self.active_checklist

    def get_checklist(self, checklist_id: str) -> Checklist | None:
        """Get a checklist by ID."""
        return self.checklists.get(checklist_id)

    def list_checklists(self) -> list[str]:
        """List all available checklist IDs."""
        return list(self.checklists.keys())
