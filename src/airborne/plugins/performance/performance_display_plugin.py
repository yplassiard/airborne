"""Performance Display plugin for aircraft performance calculations.

This plugin provides a multi-page display (FMC/PFD) showing:
- Weight & Balance data
- V-speeds for current weight
- Takeoff performance calculations

Key binding: F4 to open/close display
Navigation: Up/Down arrows to navigate pages, ENTER to read page data
"""

import pygame

from airborne.core.input_event import InputEvent
from airborne.core.input_handler import InputHandler
from airborne.core.logging_system import get_logger
from airborne.core.plugin import IPlugin, PluginContext, PluginMetadata, PluginType
from airborne.systems.performance.performance_calculator import PerformanceCalculator
from airborne.systems.weight_balance.weight_balance_system import WeightBalanceSystem
from airborne.ui.performance_display import PerformanceDisplay

logger = get_logger(__name__)


class PerformanceDisplayInputHandler(InputHandler):
    """Input handler for performance display navigation.

    Handles F4 to toggle display, arrow keys for navigation, ENTER to read page.
    """

    def __init__(self, display: PerformanceDisplay):
        """Initialize input handler.

        Args:
            display: PerformanceDisplay instance to control.
        """
        self.display = display

    def get_priority(self) -> int:
        """Get handler priority.

        Returns:
            Priority 50 (modal overlay priority).
        """
        return 50  # Modal overlays (menus, dialogs)

    def can_handle_input(self, event: InputEvent) -> bool:
        """Check if handler wants this input.

        Args:
            event: Input event to check.

        Returns:
            True if F4 key or navigation keys when display is open.
        """
        # Always handle F4 to toggle display
        if event.matches_keyboard(pygame.K_F4):
            return True

        # Handle navigation only when display is open
        if self.display.is_open():
            if event.matches_keyboard(pygame.K_UP):
                return True
            if event.matches_keyboard(pygame.K_DOWN):
                return True
            if event.matches_keyboard(pygame.K_RETURN):
                return True
            if event.matches_keyboard(pygame.K_ESCAPE):
                return True

            # Handle number keys for menu selection (when menu is open)
            if self.display.has_active_menu():
                if event.matches_keyboard(pygame.K_1):
                    return True
                if event.matches_keyboard(pygame.K_2):
                    return True
                if event.matches_keyboard(pygame.K_3):
                    return True
                if event.matches_keyboard(pygame.K_4):
                    return True

        return False

    def handle_input(self, event: InputEvent) -> bool:
        """Process input event.

        Args:
            event: Input event to process.

        Returns:
            True if event consumed (prevents propagation).
        """
        # F4: Toggle display
        if event.matches_keyboard(pygame.K_F4):
            if self.display.is_open():
                self.display.close()
            else:
                self.display.open()
            return True

        # Navigation only when display is open
        if self.display.is_open():
            # Check if a menu is currently active
            active_menu = self.display.get_active_menu()

            if active_menu:
                # Route input to the active menu
                if event.matches_keyboard(pygame.K_UP):
                    active_menu.move_selection_up()
                    return True
                elif event.matches_keyboard(pygame.K_DOWN):
                    active_menu.move_selection_down()
                    return True
                elif event.matches_keyboard(pygame.K_RETURN):
                    active_menu.select_current()
                    return True
                elif event.matches_keyboard(pygame.K_ESCAPE):
                    # Close menu, not the entire display
                    self.display.close_active_menu()
                    return True
                # Number key selection
                elif event.matches_keyboard(pygame.K_1):
                    active_menu.select_option("1")
                    return True
                elif event.matches_keyboard(pygame.K_2):
                    active_menu.select_option("2")
                    return True
                elif event.matches_keyboard(pygame.K_3):
                    active_menu.select_option("3")
                    return True
                elif event.matches_keyboard(pygame.K_4):
                    active_menu.select_option("4")
                    return True
            else:
                # No menu active - handle page navigation
                if event.matches_keyboard(pygame.K_UP):
                    self.display.previous_page()
                    return True
                elif event.matches_keyboard(pygame.K_DOWN):
                    self.display.next_page()
                    return True
                elif event.matches_keyboard(pygame.K_RETURN):
                    self.display.read_current_page()
                    return True
                elif event.matches_keyboard(pygame.K_ESCAPE):
                    self.display.close()
                    return True

        return False

    def is_active(self) -> bool:
        """Check if handler is active.

        Returns:
            Always True (always listens for F4).
        """
        return True

    def get_name(self) -> str:
        """Get handler name.

        Returns:
            Handler name string.
        """
        return "performance_display_handler"


class PerformanceDisplayPlugin(IPlugin):
    """Plugin for performance display (FMC/PFD).

    Responsibilities:
    - Create and manage PerformanceDisplay instance
    - Register input handler for F4 key and navigation
    - Wire up weight/balance and performance calculator systems

    The plugin provides:
    - performance_display: PerformanceDisplay instance
    """

    def __init__(self) -> None:
        """Initialize performance display plugin."""
        self.context: PluginContext | None = None
        self.display: PerformanceDisplay | None = None
        self.input_handler: PerformanceDisplayInputHandler | None = None

        # System dependencies
        self.wb_system: WeightBalanceSystem | None = None
        self.perf_calculator: PerformanceCalculator | None = None

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata describing this plugin.
        """
        return PluginMetadata(
            name="performance_display_plugin",
            version="1.0.0",
            author="AirBorne Team",
            plugin_type=PluginType.AVIONICS,
            dependencies=["weight_balance_plugin"],
            provides=["performance_display"],
            optional=True,
            update_priority=100,  # Low priority, UI-only
            requires_physics=False,
            description="Performance display (FMC/PFD) for W&B, V-speeds, and takeoff performance",
        )

    def initialize(self, context: PluginContext) -> None:
        """Initialize the performance display plugin.

        Args:
            context: Plugin context with access to core systems.
        """
        self.context = context

        # Get weight & balance system from registry
        if context.plugin_registry:
            self.wb_system = context.plugin_registry.get("weight_balance_system")
            if not self.wb_system:
                logger.warning("Weight & balance system not found, display will be unavailable")

        # Create performance calculator
        aircraft_config = context.config.get("aircraft", {})
        perf_config = aircraft_config.get("performance", {})

        if perf_config:
            self.perf_calculator = PerformanceCalculator(perf_config)
        else:
            logger.warning("Performance config not found, display will be unavailable")

        # Create performance display
        self.display = PerformanceDisplay(
            wb_system=self.wb_system,
            perf_calculator=self.perf_calculator,
            message_queue=context.message_queue,
        )

        # Register in registry
        if context.plugin_registry:
            context.plugin_registry.register("performance_display", self.display)

        logger.info("Performance display plugin initialized (F4 key for display)")

    def update(self, dt: float) -> None:
        """Update performance display (currently no-op).

        Args:
            dt: Delta time in seconds since last update.
        """
        # Performance display is event-driven, no periodic updates needed
        pass

    def handle_message(self, message) -> None:  # type: ignore[no-untyped-def]
        """Handle incoming messages (no-op for this plugin).

        Args:
            message: Message to handle.
        """
        # Performance display doesn't subscribe to any messages
        pass

    def shutdown(self) -> None:
        """Shutdown the performance display plugin."""
        # Close display if open
        if self.display and self.display.is_open():
            self.display.close()

        # Unregister from registry
        if self.context and self.context.plugin_registry:
            self.context.plugin_registry.unregister("performance_display")

        logger.info("Performance display plugin shutdown")
