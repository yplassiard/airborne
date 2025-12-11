"""Context-aware input management system.

This module provides a declarative, YAML-based input system that supports:
- Context stacking (global → flight_mode → atc_menu)
- Automatic conflict detection
- User customization
- Clear separation between global and context-specific bindings

Architecture:
    1. Global bindings (work everywhere): Space, Alt+numbers, Escape, etc.
    2. Context-specific bindings: Arrow keys (flight vs menu), D/F/S (radio), etc.
    3. Context stack: Contexts can be pushed/popped (opening/closing menus)
    4. Priority resolution: global (100) → menu (75) → flight_mode (50)

Example:
    >>> manager = InputContextManager(config_dir)
    >>> manager.push_context("atc_menu")  # Open ATC menu
    >>> manager.handle_key_press(pygame.K_UP, 0)  # Now moves in menu, not aircraft
    >>> manager.pop_context()  # Close menu, back to flight mode
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame
import yaml

if TYPE_CHECKING:
    from airborne.core.event_bus import EventBus

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic

logger = get_logger(__name__)


class InputContext(str, Enum):
    """Input contexts (active panels/modes)."""

    GLOBAL = "global"  # Always active (highest priority)
    FLIGHT_MODE = "flight_mode"  # Default flying context
    ATC_MENU = "atc_menu"  # F1 menu
    CHECKLIST_MENU = "checklist_menu"  # F2 menu
    GROUND_SERVICES = "ground_services_menu"  # F3 menu
    RADIO_PANEL = "radio_panel"  # Ctrl+F1 radio controls
    CONTROL_PANEL = "control_panel"  # Ctrl+P panel
    TEXT_ENTRY = "text_entry"  # Typing mode
    ALTIMETER_SETTING = "altimeter_setting"  # Alt+A altimeter mode


@dataclass
class KeyBinding:
    """Single key binding configuration."""

    keys: list[str]  # Key names (e.g., ["up", "w"])
    action: str  # Action name (e.g., "pitch_down")
    modifiers: list[str] = field(default_factory=list)  # [SHIFT, CTRL, ALT]
    description: str = ""
    repeat: bool = True  # Allow key repeat
    toggle_context: str | None = None  # Context to toggle
    pop_context: bool = False  # Return to previous context

    def __post_init__(self):
        """Normalize keys and modifiers to uppercase."""
        self.keys = [k.upper() for k in self.keys]
        self.modifiers = [m.upper() for m in self.modifiers]

    def matches(self, key_name: str, active_mods: set[str]) -> bool:
        """Check if this binding matches the pressed key.

        Args:
            key_name: Pygame key name (uppercased).
            active_mods: Set of active modifiers {"SHIFT", "CTRL", "ALT"}.

        Returns:
            True if key and modifiers match.
        """
        if key_name not in self.keys:
            return False

        required_mods = set(self.modifiers)
        return required_mods == active_mods


@dataclass
class InputContextConfig:
    """Configuration for a single input context."""

    name: str
    description: str
    priority: int = 50
    bindings: list[KeyBinding] = field(default_factory=list)
    on_enter: dict[str, Any] | None = None  # Actions when entering context
    on_exit: dict[str, Any] | None = None  # Actions when exiting context
    block_actions: list[str] = field(default_factory=list)  # Blocked action names


class InputContextManager:
    """Manages context-aware input bindings from YAML configuration.

    This class loads YAML binding files and resolves key presses based on
    the active context stack. Contexts are checked in priority order:
    global (100) → active menu (75) → flight_mode (50).

    User-defined keybindings (from ~/.airborne/keybindings/{aircraft_id}.yaml)
    override the default YAML configurations when an aircraft_id is provided.

    Attributes:
        contexts: Loaded context configurations by name.
        context_stack: Active contexts (top = current).
        message_queue: Message queue for publishing input events.
        action_handlers: Direct action handlers (bypass messaging).
        aircraft_id: Aircraft identifier for loading user keybindings.
    """

    def __init__(
        self,
        config_dir: Path,
        message_queue: MessageQueue,
        aircraft_id: str | None = None,
        event_bus: "EventBus | None" = None,
    ):
        """Initialize input context manager.

        Args:
            config_dir: Path to config/input directory.
            message_queue: Message queue for publishing input events.
            aircraft_id: Aircraft identifier for loading user keybindings.
                If provided, user overrides from ~/.airborne/keybindings/
                will be applied on top of default YAML bindings.
            event_bus: Optional event bus for publishing InputActionEvents.
        """
        self.config_dir = config_dir
        self.message_queue = message_queue
        self.aircraft_id = aircraft_id
        self.event_bus = event_bus
        self.contexts: dict[str, InputContextConfig] = {}
        self.context_stack: list[str] = [InputContext.FLIGHT_MODE]
        self.action_handlers: dict[str, Callable] = {}

        self._load_all_contexts()
        self._apply_user_overrides()

    def _load_all_contexts(self):
        """Load all YAML context files from config/input/contexts/."""
        context_dir = self.config_dir / "contexts"
        if not context_dir.exists():
            logger.warning(f"Context directory not found: {context_dir}")
            return

        for yaml_file in context_dir.glob("*.yaml"):
            try:
                self._load_context(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load context {yaml_file}: {e}")

        logger.info(f"Loaded {len(self.contexts)} input contexts")

    def _load_context(self, yaml_file: Path):
        """Load single context configuration from YAML.

        Args:
            yaml_file: Path to YAML file.
        """
        with open(yaml_file) as f:
            config = yaml.safe_load(f)

        context_name = config["context"]
        bindings = []

        for binding_config in config.get("bindings", []):
            # Handle both single key and multiple keys
            keys = binding_config.get("keys") or [binding_config.get("key")]
            if not isinstance(keys, list):
                keys = [keys]

            binding = KeyBinding(
                keys=[str(k) for k in keys],
                action=binding_config["action"],
                modifiers=binding_config.get("modifiers", []),
                description=binding_config.get("description", ""),
                repeat=binding_config.get("repeat", True),
                toggle_context=binding_config.get("toggle_context"),
                pop_context=binding_config.get("pop_context", False),
            )
            bindings.append(binding)

        context_cfg = InputContextConfig(
            name=context_name,
            description=config.get("description", ""),
            priority=config.get("priority", 50),
            bindings=bindings,
            on_enter=config.get("on_enter"),
            on_exit=config.get("on_exit"),
            block_actions=config.get("block_actions", []),
        )

        self.contexts[context_name] = context_cfg
        logger.debug(f"Loaded context '{context_name}' with {len(bindings)} bindings")

    def _apply_user_overrides(self) -> None:
        """Apply user keybinding overrides from settings.

        Loads user settings for the current aircraft and overrides or unbinds
        the default bindings accordingly. User overrides take precedence over
        YAML defaults.
        """
        if not self.aircraft_id:
            logger.debug("No aircraft_id set, skipping user keybinding overrides")
            return

        try:
            from airborne.settings.keybindings_settings import get_keybindings_settings

            settings = get_keybindings_settings(self.aircraft_id)

            if not settings.has_overrides():
                logger.debug("No user keybinding overrides for %s", self.aircraft_id)
                return

            override_count = 0
            unbind_count = 0

            for context_name, overrides in settings.overrides.items():
                context_cfg = self.contexts.get(context_name)
                if not context_cfg:
                    logger.warning("User override for unknown context '%s', skipping", context_name)
                    continue

                for override in overrides:
                    # Find the binding for this action
                    binding_found = False
                    for i, binding in enumerate(context_cfg.bindings):
                        if binding.action == override.action:
                            binding_found = True
                            if override.unbound:
                                # Remove the binding entirely
                                context_cfg.bindings.pop(i)
                                unbind_count += 1
                                logger.debug(
                                    "Unbound action '%s' in context '%s'",
                                    override.action,
                                    context_name,
                                )
                            else:
                                # Override the keys and modifiers
                                binding.keys = [k.upper() for k in override.keys]
                                binding.modifiers = [m.upper() for m in override.modifiers]
                                override_count += 1
                                logger.debug(
                                    "Override binding for '%s' in '%s': %s+%s",
                                    override.action,
                                    context_name,
                                    binding.modifiers,
                                    binding.keys,
                                )
                            break

                    if not binding_found and not override.unbound:
                        # Action not found in defaults - add as new binding
                        new_binding = KeyBinding(
                            keys=[k.upper() for k in override.keys],
                            action=override.action,
                            modifiers=[m.upper() for m in override.modifiers],
                        )
                        context_cfg.bindings.append(new_binding)
                        override_count += 1
                        logger.debug(
                            "Added new binding for '%s' in '%s': %s+%s",
                            override.action,
                            context_name,
                            new_binding.modifiers,
                            new_binding.keys,
                        )

            if override_count > 0 or unbind_count > 0:
                logger.info(
                    "Applied user keybindings for %s: %d overrides, %d unbound",
                    self.aircraft_id,
                    override_count,
                    unbind_count,
                )

        except ImportError:
            logger.debug("keybindings_settings not available, skipping user overrides")
        except Exception as e:
            logger.error("Failed to apply user keybinding overrides: %s", e)

    def handle_key_press(self, key: int, mods: int, is_repeat: bool = False) -> bool:
        """Handle key press with context awareness.

        Resolves bindings in priority order:
        1. Global context (always checked first)
        2. Active context (top of stack)
        3. Lower contexts in stack

        Args:
            key: Pygame key code.
            mods: Pygame modifier mask.
            is_repeat: True if this is a repeated key event.

        Returns:
            True if key was handled, False otherwise.
        """
        # Convert key to name
        key_name = pygame.key.name(key).upper()

        # Extract active modifiers
        active_mods = self._get_active_modifiers(mods)

        # Build context priority list
        # Always check global first, then active contexts in stack order
        contexts_to_check = self._get_context_priority_list()

        # Log for debugging
        mod_str = "+".join(sorted(active_mods)) + "+" if active_mods else ""
        logger.debug(f"Key press: {mod_str}{key_name}, contexts: {contexts_to_check}")

        # Try each context in priority order
        for context_name in contexts_to_check:
            context_cfg = self.contexts.get(context_name)
            if not context_cfg:
                continue

            # Try each binding in this context
            for binding in context_cfg.bindings:
                if binding.matches(key_name, active_mods):
                    # Skip if repeat and binding doesn't allow repeat
                    if is_repeat and not binding.repeat:
                        logger.debug(f"Skipping repeat for {binding.action}")
                        return True

                    logger.info(
                        f"Matched: {mod_str}{key_name} → {binding.action} (context: {context_name})"
                    )

                    # Handle context changes
                    self._handle_context_change(binding)

                    # Execute action
                    self._execute_action(binding.action, key, mods)
                    return True  # Handled

        # Not handled by any context
        logger.debug(f"No binding found for {mod_str}{key_name}")
        return False

    def _get_active_modifiers(self, mods: int) -> set[str]:
        """Extract active modifier keys from pygame modifier mask.

        Args:
            mods: Pygame modifier mask.

        Returns:
            Set of active modifier names {"SHIFT", "CTRL", "ALT"}.
        """
        active_mods = set()

        if mods & (pygame.KMOD_SHIFT | pygame.KMOD_LSHIFT | pygame.KMOD_RSHIFT):
            active_mods.add("SHIFT")
        if mods & (pygame.KMOD_CTRL | pygame.KMOD_LCTRL | pygame.KMOD_RCTRL):
            active_mods.add("CTRL")
        if mods & (pygame.KMOD_ALT | pygame.KMOD_LALT | pygame.KMOD_RALT):
            active_mods.add("ALT")

        return active_mods

    def _get_context_priority_list(self) -> list[str]:
        """Get ordered list of contexts to check (highest priority first).

        Returns:
            List of context names in priority order.
        """
        # Collect all active contexts (global + stack)
        active_contexts = [InputContext.GLOBAL] + self.context_stack

        # Sort by priority (highest first)
        return sorted(
            active_contexts,
            key=lambda ctx: self.contexts.get(ctx, InputContextConfig(ctx, "", 0)).priority,
            reverse=True,
        )

    def _handle_context_change(self, binding: KeyBinding):
        """Handle context push/pop/toggle from binding.

        Args:
            binding: The matched key binding.
        """
        if binding.pop_context:
            self.pop_context()

        if binding.toggle_context:
            # Toggle: if context already active, pop it; otherwise push it
            if binding.toggle_context in self.context_stack:
                self.pop_context()
            else:
                self.push_context(binding.toggle_context)

    def _execute_action(self, action: str, key: int, mods: int):
        """Execute action handler or publish as message.

        Args:
            action: Action name.
            key: Pygame key code.
            mods: Pygame modifier mask.
        """
        # Try direct handler first
        handler = self.action_handlers.get(action)
        if handler:
            try:
                handler(action, key, mods)
                return
            except Exception as e:
                logger.error(f"Action handler '{action}' failed: {e}")

        # Publish InputActionEvent to event bus (for main.py handlers)
        if self.event_bus:
            from airborne.core.input import InputActionEvent

            self.event_bus.publish(InputActionEvent(action=action))

        # Publish as message for plugins to handle
        # Skip push_to_talk since it requires special press/release handling
        # (main.py handles it via KEYDOWN/KEYUP events)
        if action != "push_to_talk":
            self.message_queue.publish(
                Message(
                    sender="input_context_manager",
                    recipients=["*"],
                    topic=f"input.{action}",
                    data={"key": key, "mods": mods},
                    priority=MessagePriority.NORMAL,
                )
            )

    def push_context(self, context_name: str):
        """Push new context onto stack (becomes active).

        Args:
            context_name: Name of context to activate.
        """
        if context_name in self.context_stack:
            logger.warning(f"Context '{context_name}' already active")
            return

        self.context_stack.append(context_name)
        logger.info(f"Pushed context: {context_name}, stack: {self.context_stack}")

        # Execute on_enter actions
        context_cfg = self.contexts.get(context_name)
        if context_cfg and context_cfg.on_enter:
            self._execute_context_action(context_cfg.on_enter)

    def pop_context(self):
        """Pop current context (return to previous).

        The base context (flight_mode) is never popped.
        """
        if len(self.context_stack) <= 1:
            logger.warning("Cannot pop base context (flight_mode)")
            return

        popped = self.context_stack.pop()
        logger.info(f"Popped context: {popped}, stack: {self.context_stack}")

        # Execute on_exit actions
        context_cfg = self.contexts.get(popped)
        if context_cfg and context_cfg.on_exit:
            self._execute_context_action(context_cfg.on_exit)

    def _execute_context_action(self, action_config: dict[str, Any]):
        """Execute context action (on_enter/on_exit).

        Args:
            action_config: Action configuration from YAML.
        """
        # Support "announce" action for TTS
        if "announce" in action_config:
            from airborne.core.i18n import t

            msg_key = action_config["announce"]
            # Translate the message key and send as text
            text = t(msg_key)
            self.message_queue.publish(
                Message(
                    sender="input_context_manager",
                    recipients=["*"],
                    topic=MessageTopic.TTS_SPEAK,
                    data={"text": text, "priority": "high"},
                    priority=MessagePriority.HIGH,
                )
            )

    def get_active_context(self) -> str:
        """Get current active context.

        Returns:
            Name of topmost context in stack.
        """
        return self.context_stack[-1] if self.context_stack else InputContext.FLIGHT_MODE

    def register_action_handler(self, action: str, handler: Callable):
        """Register direct action handler (bypasses messaging).

        Args:
            action: Action name.
            handler: Callable handler(action: str, key: int, mods: int).
        """
        self.action_handlers[action] = handler
        logger.debug(f"Registered action handler: {action}")

    def detect_conflicts(self) -> list[dict]:
        """Detect key binding conflicts within each context.

        Returns:
            List of conflict descriptions.
        """
        conflicts = []

        for context_name, context_cfg in self.contexts.items():
            seen: dict[tuple, list[KeyBinding]] = {}

            for binding in context_cfg.bindings:
                for key in binding.keys:
                    mods_key = (key, tuple(sorted(binding.modifiers)))

                    if mods_key in seen:
                        conflicts.append(
                            {
                                "context": context_name,
                                "key": key,
                                "modifiers": binding.modifiers,
                                "actions": [b.action for b in seen[mods_key]] + [binding.action],
                            }
                        )
                    else:
                        seen[mods_key] = [binding]

        return conflicts

    def get_binding_help(self, context: str | None = None) -> str:
        """Generate help text for bindings.

        Args:
            context: Context name, or None for current context.

        Returns:
            Formatted help text.
        """
        context_name = context or self.get_active_context()
        context_cfg = self.contexts.get(context_name)

        if not context_cfg:
            return f"Context '{context_name}' not found"

        lines = [f"=== {context_cfg.description} ===\n"]

        for binding in context_cfg.bindings:
            key_str = ", ".join(binding.keys)
            mod_str = "+".join(binding.modifiers) + "+" if binding.modifiers else ""
            lines.append(f"{mod_str}{key_str:15} → {binding.description}")

        return "\n".join(lines)
