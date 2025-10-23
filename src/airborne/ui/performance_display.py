"""Performance Display (FMC) for aircraft performance calculations.

This module provides a multi-page display system showing:
- Weight & Balance (total weight, CG, station breakdown)
- V-speeds (stall, rotation, climb speeds)
- Takeoff Performance (distances, climb rate)

Navigation:
- F4: Open/close performance display
- Up/Down: Navigate between pages
- Enter: Open page submenu
- ESC: Close display
"""

from typing import Any

from airborne.core.logging_system import get_logger
from airborne.core.messaging import Message, MessagePriority, MessageQueue, MessageTopic
from airborne.systems.performance.performance_calculator import PerformanceCalculator
from airborne.systems.weight_balance.weight_balance_system import WeightBalanceSystem
from airborne.ui.menu import Menu, MenuOption

logger = get_logger(__name__)


class PerformanceDisplay:
    """Multi-page performance display system (FMC/PFD).

    Displays aircraft performance data across multiple pages:
    1. Weight & Balance (W&B)
    2. V-speeds
    3. Takeoff Performance

    Responsibilities:
    - Display current weight and CG data
    - Calculate and show V-speeds for current weight
    - Calculate and show takeoff distances and climb rates
    - TTS announcements for navigation and values

    Examples:
        >>> display = PerformanceDisplay(wb_system, perf_calc, message_queue)
        >>> display.open()  # Opens to page 1 (Weight & Balance)
        >>> display.next_page()  # Move to page 2 (V-speeds)
        >>> display.read_current_page()  # Announce page content via TTS
    """

    def __init__(
        self,
        wb_system: WeightBalanceSystem | None,
        perf_calculator: PerformanceCalculator | None,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize performance display.

        Args:
            wb_system: Weight and balance system instance.
            perf_calculator: Performance calculator instance.
            message_queue: Message queue for TTS announcements.
        """
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator
        self._message_queue = message_queue

        self._state = "CLOSED"  # CLOSED, OPEN
        self._current_page = 1  # 1=W&B, 2=V-speeds, 3=Takeoff
        self._total_pages = 3

        # Create page menus
        self._wb_menu: WeightBalanceMenu | None = None
        self._vspeeds_menu: VSpeedsMenu | None = None
        self._takeoff_menu: TakeoffMenu | None = None

        if wb_system and perf_calculator:
            self._wb_menu = WeightBalanceMenu(wb_system, message_queue)
            self._vspeeds_menu = VSpeedsMenu(wb_system, perf_calculator, message_queue)
            self._takeoff_menu = TakeoffMenu(wb_system, perf_calculator, message_queue)

        logger.info("PerformanceDisplay initialized with 3 pages")

    def open(self) -> bool:
        """Open the performance display.

        Returns:
            True if opened successfully, False otherwise.
        """
        if self._state == "OPEN":
            logger.warning("PerformanceDisplay already open")
            return False

        if not self.wb_system or not self.perf_calculator:
            logger.warning("PerformanceDisplay missing systems (W&B or PerformanceCalculator)")
            self._speak("MSG_FMC_NOT_AVAILABLE")
            return False

        self._state = "OPEN"
        self._current_page = 1
        logger.info("PerformanceDisplay opened to page 1")

        # Announce opening with page title
        self._speak(["MSG_FMC_OPENED", "MSG_FMC_PAGE_1", "MSG_FMC_WB_TITLE"], interrupt=True)

        return True

    def close(self) -> bool:
        """Close the performance display.

        Returns:
            True if closed successfully, False otherwise.
        """
        if self._state == "CLOSED":
            return False

        self._state = "CLOSED"
        logger.info("PerformanceDisplay closed")

        self._speak("MSG_FMC_CLOSED", interrupt=True)

        return True

    def next_page(self) -> bool:
        """Navigate to next page.

        Returns:
            True if moved to next page, False if at last page.
        """
        if self._state != "OPEN":
            return False

        if self._current_page < self._total_pages:
            self._current_page += 1
            logger.debug(f"PerformanceDisplay: page {self._current_page}")
            self._announce_page()
            return True

        return False

    def previous_page(self) -> bool:
        """Navigate to previous page.

        Returns:
            True if moved to previous page, False if at first page.
        """
        if self._state != "OPEN":
            return False

        if self._current_page > 1:
            self._current_page -= 1
            logger.debug(f"PerformanceDisplay: page {self._current_page}")
            self._announce_page()
            return True

        return False

    def read_current_page(self) -> bool:
        """Open submenu for current page.

        Returns:
            True if menu opened successfully, False otherwise.
        """
        if self._state != "OPEN":
            return False

        # Open the appropriate menu
        if self._current_page == 1 and self._wb_menu:
            return self._wb_menu.open()
        elif self._current_page == 2 and self._vspeeds_menu:
            return self._vspeeds_menu.open()
        elif self._current_page == 3 and self._takeoff_menu:
            return self._takeoff_menu.open()

        return False

    def is_open(self) -> bool:
        """Check if display is open.

        Returns:
            True if open, False otherwise.
        """
        return self._state == "OPEN"

    def get_current_page(self) -> int:
        """Get current page number.

        Returns:
            Current page number (1-3).
        """
        return self._current_page

    def get_active_menu(self) -> Menu | None:
        """Get currently active menu.

        Returns:
            Active menu instance or None if no menu is open.
        """
        if self._wb_menu and self._wb_menu.is_open():
            return self._wb_menu
        if self._vspeeds_menu and self._vspeeds_menu.is_open():
            return self._vspeeds_menu
        if self._takeoff_menu and self._takeoff_menu.is_open():
            return self._takeoff_menu
        return None

    def has_active_menu(self) -> bool:
        """Check if any page menu is currently open.

        Returns:
            True if a menu is open, False otherwise.
        """
        return self.get_active_menu() is not None

    def close_active_menu(self) -> bool:
        """Close the currently active menu.

        Returns:
            True if a menu was closed, False if no menu was open.
        """
        active_menu = self.get_active_menu()
        if active_menu:
            active_menu.close()
            return True
        return False

    # Page-specific reading methods

    def _read_weight_balance_page(self) -> None:
        """Read Weight & Balance page data via TTS."""
        if not self.wb_system:
            return

        # Calculate current data
        total_weight = self.wb_system.calculate_total_weight()
        cg = self.wb_system.calculate_cg()
        within_limits, status_msg = self.wb_system.is_within_limits()

        # Build TTS message
        messages: list[str] = [
            "MSG_FMC_WB_TITLE",
            "MSG_FMC_WB_TOTAL_WEIGHT",
        ]
        messages.extend(self._flatten_speech(self._weight_to_speech(total_weight)))
        messages.append("MSG_WORD_POUNDS")

        # Add CG position
        messages.append("MSG_FMC_WB_CG_POSITION")
        messages.extend(self._flatten_speech(self._number_to_speech(int(cg))))
        messages.append("MSG_WORD_INCHES")

        # Add status
        if within_limits:
            messages.append("MSG_FMC_WB_WITHIN_LIMITS")
        else:
            messages.append("MSG_FMC_WB_OUT_OF_LIMITS")

        self._speak(messages, interrupt=True)

        logger.info(f"Read W&B: {total_weight:.0f} lbs, CG={cg:.1f} in, {status_msg}")

    def _read_vspeeds_page(self) -> None:
        """Read V-speeds page data via TTS."""
        if not self.wb_system or not self.perf_calculator:
            return

        # Calculate V-speeds
        weight = self.wb_system.calculate_total_weight()
        vspeeds = self.perf_calculator.calculate_vspeeds(weight)

        # Build TTS message
        messages: list[str] = [
            "MSG_FMC_VS_TITLE",
            "MSG_FMC_VS_WEIGHT",
        ]
        messages.extend(self._flatten_speech(self._weight_to_speech(weight)))
        messages.append("MSG_WORD_POUNDS")

        # Add each V-speed
        messages.append("MSG_FMC_VS_VSTALL")
        messages.extend(self._flatten_speech(self._number_to_speech(int(vspeeds.v_s))))
        messages.append("MSG_WORD_KNOTS")

        messages.append("MSG_FMC_VS_VR")
        messages.extend(self._flatten_speech(self._number_to_speech(int(vspeeds.v_r))))
        messages.append("MSG_WORD_KNOTS")

        messages.append("MSG_FMC_VS_VX")
        messages.extend(self._flatten_speech(self._number_to_speech(int(vspeeds.v_x))))
        messages.append("MSG_WORD_KNOTS")

        messages.append("MSG_FMC_VS_VY")
        messages.extend(self._flatten_speech(self._number_to_speech(int(vspeeds.v_y))))
        messages.append("MSG_WORD_KNOTS")

        self._speak(messages, interrupt=True)

        logger.info(
            f"Read V-speeds: V_S={vspeeds.v_s:.0f}, V_R={vspeeds.v_r:.0f}, "
            f"V_X={vspeeds.v_x:.0f}, V_Y={vspeeds.v_y:.0f} KIAS"
        )

    def _read_takeoff_page(self) -> None:
        """Read Takeoff Performance page data via TTS."""
        if not self.wb_system or not self.perf_calculator:
            return

        # Calculate takeoff performance
        weight = self.wb_system.calculate_total_weight()
        takeoff = self.perf_calculator.calculate_takeoff_distance(weight)
        climb_rate = self.perf_calculator.calculate_climb_rate(weight)

        # Build TTS message
        messages: list[str] = [
            "MSG_FMC_TO_TITLE",
            "MSG_FMC_TO_WEIGHT",
        ]
        messages.extend(self._flatten_speech(self._weight_to_speech(weight)))
        messages.append("MSG_WORD_POUNDS")

        # Ground roll
        messages.append("MSG_FMC_TO_GROUND_ROLL")
        messages.extend(self._flatten_speech(self._number_to_speech(int(takeoff.ground_roll_ft))))
        messages.append("MSG_WORD_FEET")

        # Distance to 50ft
        messages.append("MSG_FMC_TO_DISTANCE_50")
        messages.extend(self._flatten_speech(self._number_to_speech(int(takeoff.distance_50ft))))
        messages.append("MSG_WORD_FEET")

        # Climb rate
        messages.append("MSG_FMC_TO_CLIMB_RATE")
        messages.extend(self._flatten_speech(self._number_to_speech(int(climb_rate))))
        messages.append("MSG_WORD_FPM")

        self._speak(messages, interrupt=True)

        logger.info(
            f"Read takeoff: ground_roll={takeoff.ground_roll_ft:.0f} ft, "
            f"distance_50={takeoff.distance_50ft:.0f} ft, climb={climb_rate:.0f} fpm"
        )

    def _announce_page(self) -> None:
        """Announce current page number and title via TTS."""
        if self._current_page == 1:
            self._speak(["MSG_FMC_PAGE_1", "MSG_FMC_WB_TITLE"], interrupt=True)
        elif self._current_page == 2:
            self._speak(["MSG_FMC_PAGE_2", "MSG_FMC_VS_TITLE"], interrupt=True)
        elif self._current_page == 3:
            self._speak(["MSG_FMC_PAGE_3", "MSG_FMC_TO_TITLE"], interrupt=True)

    # Helper methods for TTS

    def _flatten_speech(self, speech: str | list[str]) -> list[str]:
        """Flatten speech result to list of strings.

        Args:
            speech: String or list of strings.

        Returns:
            List of strings (flattened if needed).
        """
        if isinstance(speech, str):
            return [speech]
        return speech

    def _weight_to_speech(self, weight: float) -> str | list[str]:
        """Convert weight value to TTS message keys.

        Args:
            weight: Weight in pounds.

        Returns:
            Message key or list of keys for TTS.
        """
        # Round to nearest 10
        weight_rounded = int(round(weight / 10.0) * 10)
        return self._number_to_speech(weight_rounded)

    def _number_to_speech(self, number: int) -> str | list[str]:
        """Convert number to TTS message keys.

        Args:
            number: Integer number.

        Returns:
            Message key or list of keys for TTS.

        Note:
            For numbers 0-100, uses MSG_NUMBER_X.
            For larger numbers, breaks down into components.
        """
        # Simple numbers (0-100): direct mapping
        if 0 <= number <= 100:
            return f"MSG_NUMBER_{number}"

        # Larger numbers: break down into components
        # For simplicity, just use the direct number for now
        # Could be enhanced to speak "two thousand five hundred" etc.
        if number < 1000:
            # Hundreds: "500" -> "five hundred"
            hundreds = number // 100
            remainder = number % 100

            messages = []
            if hundreds > 0:
                messages.append(f"MSG_NUMBER_{hundreds}")
                messages.append("MSG_WORD_HUNDRED")

            if remainder > 0:
                messages.append(f"MSG_NUMBER_{remainder}")

            return messages if len(messages) > 1 else messages[0]

        # Thousands: "2500" -> "two thousand five hundred"
        thousands = number // 1000
        remainder = number % 1000

        messages = []
        if thousands > 0:
            messages.append(f"MSG_NUMBER_{thousands}")
            messages.append("MSG_WORD_THOUSAND")

        if remainder > 0:
            messages.extend(self._number_to_speech(remainder))

        return messages if len(messages) > 1 else messages[0]

    def _speak(
        self,
        message_keys: str | list[str],
        priority: str = "high",
        interrupt: bool = False,
    ) -> None:
        """Speak message via TTS.

        Args:
            message_keys: Message key or list of keys to speak.
            priority: Priority level (high, normal, low).
            interrupt: Whether to interrupt current speech.
        """
        if not self._message_queue:
            return

        self._message_queue.publish(
            Message(
                sender="performance_display",
                recipients=["*"],
                topic=MessageTopic.TTS_SPEAK,
                data={"text": message_keys, "priority": priority, "interrupt": interrupt},
                priority=MessagePriority.HIGH if priority == "high" else MessagePriority.NORMAL,
            )
        )


class WeightBalanceMenu(Menu):
    """Menu for Weight & Balance page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize W&B menu.

        Args:
            wb_system: Weight and balance system.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="weight_balance_menu")
        self.wb_system = wb_system

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for W&B page."""
        total_weight = self.wb_system.calculate_total_weight()
        cg = self.wb_system.calculate_cg()
        within_limits, status_msg = self.wb_system.is_within_limits()

        return [
            MenuOption(
                key="1",
                label=f"Total Weight: {total_weight:.0f} lbs",
                message_key="MSG_FMC_WB_TOTAL_WEIGHT",
                data={"value": total_weight, "type": "weight"},
            ),
            MenuOption(
                key="2",
                label=f"CG Position: {cg:.1f} inches",
                message_key="MSG_FMC_WB_CG_POSITION",
                data={"value": cg, "type": "cg"},
            ),
            MenuOption(
                key="3",
                label=f"Status: {status_msg}",
                message_key="MSG_FMC_WB_WITHIN_LIMITS"
                if within_limits
                else "MSG_FMC_WB_OUT_OF_LIMITS",
                data={"within_limits": within_limits},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        # Speak the full value
        if option.data and option.data.get("type") == "weight":
            weight = option.data["value"]
            messages = [option.message_key]
            messages.extend(self._number_to_speech(int(round(weight / 10.0) * 10)))
            messages.append("MSG_WORD_POUNDS")
            self._speak(messages, interrupt=True)
        elif option.data and option.data.get("type") == "cg":
            cg = option.data["value"]
            messages = [option.message_key]
            messages.extend(self._number_to_speech(int(cg)))
            messages.append("MSG_WORD_INCHES")
            self._speak(messages, interrupt=True)
        else:
            # Just announce the status
            self._speak(option.message_key, interrupt=True)

    def _number_to_speech(self, number: int) -> list[str]:
        """Convert number to speech messages."""
        if 0 <= number <= 100:
            return [f"MSG_NUMBER_{number}"]

        messages = []
        if number < 1000:
            hundreds = number // 100
            remainder = number % 100
            if hundreds > 0:
                messages.extend([f"MSG_NUMBER_{hundreds}", "MSG_WORD_HUNDRED"])
            if remainder > 0:
                messages.append(f"MSG_NUMBER_{remainder}")
        else:
            thousands = number // 1000
            remainder = number % 1000
            if thousands > 0:
                messages.extend([f"MSG_NUMBER_{thousands}", "MSG_WORD_THOUSAND"])
            if remainder > 0:
                messages.extend(self._number_to_speech(remainder))

        return messages

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return "MSG_FMC_WB_TITLE"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return "MSG_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return "MSG_INVALID_OPTION"


class VSpeedsMenu(Menu):
    """Menu for V-speeds page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        perf_calculator: PerformanceCalculator,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize V-speeds menu.

        Args:
            wb_system: Weight and balance system.
            perf_calculator: Performance calculator.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="vspeeds_menu")
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for V-speeds page."""
        weight = self.wb_system.calculate_total_weight()
        vspeeds = self.perf_calculator.calculate_vspeeds(weight)

        return [
            MenuOption(
                key="1",
                label=f"V-Stall: {vspeeds.v_s:.0f} KIAS",
                message_key="MSG_FMC_VS_VSTALL",
                data={"value": vspeeds.v_s, "type": "vspeed"},
            ),
            MenuOption(
                key="2",
                label=f"V-Rotate: {vspeeds.v_r:.0f} KIAS",
                message_key="MSG_FMC_VS_VR",
                data={"value": vspeeds.v_r, "type": "vspeed"},
            ),
            MenuOption(
                key="3",
                label=f"V-X (Best Angle): {vspeeds.v_x:.0f} KIAS",
                message_key="MSG_FMC_VS_VX",
                data={"value": vspeeds.v_x, "type": "vspeed"},
            ),
            MenuOption(
                key="4",
                label=f"V-Y (Best Rate): {vspeeds.v_y:.0f} KIAS",
                message_key="MSG_FMC_VS_VY",
                data={"value": vspeeds.v_y, "type": "vspeed"},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        if option.data and option.data.get("type") == "vspeed":
            speed = option.data["value"]
            messages = [option.message_key]
            messages.extend(self._number_to_speech(int(speed)))
            messages.append("MSG_WORD_KNOTS")
            self._speak(messages, interrupt=True)

    def _number_to_speech(self, number: int) -> list[str]:
        """Convert number to speech messages."""
        if 0 <= number <= 100:
            return [f"MSG_NUMBER_{number}"]

        messages = []
        if number < 1000:
            hundreds = number // 100
            remainder = number % 100
            if hundreds > 0:
                messages.extend([f"MSG_NUMBER_{hundreds}", "MSG_WORD_HUNDRED"])
            if remainder > 0:
                messages.append(f"MSG_NUMBER_{remainder}")
        else:
            thousands = number // 1000
            remainder = number % 1000
            if thousands > 0:
                messages.extend([f"MSG_NUMBER_{thousands}", "MSG_WORD_THOUSAND"])
            if remainder > 0:
                messages.extend(self._number_to_speech(remainder))

        return messages

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return "MSG_FMC_VS_TITLE"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return "MSG_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return "MSG_INVALID_OPTION"


class TakeoffMenu(Menu):
    """Menu for Takeoff Performance page."""

    def __init__(
        self,
        wb_system: WeightBalanceSystem,
        perf_calculator: PerformanceCalculator,
        message_queue: MessageQueue | None = None,
    ):
        """Initialize takeoff menu.

        Args:
            wb_system: Weight and balance system.
            perf_calculator: Performance calculator.
            message_queue: Message queue for TTS.
        """
        super().__init__(message_queue=message_queue, sender_name="takeoff_menu")
        self.wb_system = wb_system
        self.perf_calculator = perf_calculator

    def _build_options(self, context: Any) -> list[MenuOption]:
        """Build menu options for takeoff page."""
        weight = self.wb_system.calculate_total_weight()
        takeoff = self.perf_calculator.calculate_takeoff_distance(weight)
        climb_rate = self.perf_calculator.calculate_climb_rate(weight)

        return [
            MenuOption(
                key="1",
                label=f"Ground Roll: {takeoff.ground_roll_ft:.0f} ft",
                message_key="MSG_FMC_TO_GROUND_ROLL",
                data={"value": takeoff.ground_roll_ft, "type": "distance"},
            ),
            MenuOption(
                key="2",
                label=f"Distance to 50ft: {takeoff.distance_50ft:.0f} ft",
                message_key="MSG_FMC_TO_DISTANCE_50",
                data={"value": takeoff.distance_50ft, "type": "distance"},
            ),
            MenuOption(
                key="3",
                label=f"Climb Rate: {climb_rate:.0f} fpm",
                message_key="MSG_FMC_TO_CLIMB_RATE",
                data={"value": climb_rate, "type": "climb_rate"},
            ),
        ]

    def _handle_selection(self, option: MenuOption) -> None:
        """Handle menu option selection."""
        if option.data:
            value = option.data["value"]
            value_type = option.data.get("type")

            messages = [option.message_key]
            messages.extend(self._number_to_speech(int(value)))

            if value_type == "distance":
                messages.append("MSG_WORD_FEET")
            elif value_type == "climb_rate":
                messages.append("MSG_WORD_FPM")

            self._speak(messages, interrupt=True)

    def _number_to_speech(self, number: int) -> list[str]:
        """Convert number to speech messages."""
        if 0 <= number <= 100:
            return [f"MSG_NUMBER_{number}"]

        messages = []
        if number < 1000:
            hundreds = number // 100
            remainder = number % 100
            if hundreds > 0:
                messages.extend([f"MSG_NUMBER_{hundreds}", "MSG_WORD_HUNDRED"])
            if remainder > 0:
                messages.append(f"MSG_NUMBER_{remainder}")
        else:
            thousands = number // 1000
            remainder = number % 1000
            if thousands > 0:
                messages.extend([f"MSG_NUMBER_{thousands}", "MSG_WORD_THOUSAND"])
            if remainder > 0:
                messages.extend(self._number_to_speech(remainder))

        return messages

    def _get_menu_opened_message(self) -> str:
        """Get TTS message for menu opened."""
        return "MSG_FMC_TO_TITLE"

    def _get_menu_closed_message(self) -> str:
        """Get TTS message for menu closed."""
        return "MSG_MENU_CLOSED"

    def _get_invalid_option_message(self) -> str:
        """Get TTS message for invalid option."""
        return "MSG_INVALID_OPTION"
