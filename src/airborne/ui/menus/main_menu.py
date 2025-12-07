"""Main menu for AirBorne flight simulator.

This is the top-level menu shown at game startup:
- Fly!
- Flight Settings (Aircraft, Airports, Passengers, Fuel, Position, State)
- Settings (Voice Settings)
- Exit

Typical usage:
    menu = MainMenu()
    menu.open()
    # In game loop:
    menu.handle_key(key, unicode)
    # Check result:
    result = menu.get_result()
"""

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

import yaml

from airborne.core.i18n import t
from airborne.core.resource_path import get_resource_path
from airborne.scenario.scenario import EngineState, SpawnLocation
from airborne.ui.menus.base_menu import AudioMenu, MenuItem
from airborne.ui.menus.voice_settings import VoiceSettingsMenu

logger = logging.getLogger(__name__)


class FlightSettingsMenu(AudioMenu):
    """Flight settings menu with flattened structure.

    Contains all flight configuration options:
    - Aircraft selection
    - From/To airports
    - Circuit training mode
    - Passengers and fuel
    - Initial position and state
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize flight settings menu."""
        super().__init__(t("menu.flight_settings.title"), parent)

        # Flight configuration values
        self._aircraft: str | None = None
        self._aircraft_name: str | None = None
        self._from_airport: str | None = None
        self._to_airport: str | None = None
        self._circuit_training: bool = False
        self._passengers: int = 0
        self._fuel_gallons: float | None = None
        self._initial_position: SpawnLocation = SpawnLocation.RAMP
        self._initial_state: EngineState = EngineState.COLD_AND_DARK

        # Aircraft data for capacity limits
        self._max_passengers: int = 3  # Default for C172 (pilot + 3)
        self._max_fuel: float = 52.0  # Default for C172 (2 x 26 gallons)

        # Submenus for selection
        self._aircraft_menu: AircraftSubMenu | None = None
        self._from_airport_menu: AirportSubMenu | None = None
        self._to_airport_menu: AirportSubMenu | None = None
        self._passengers_menu: NumberInputSubMenu | None = None
        self._fuel_menu: NumberInputSubMenu | None = None
        self._position_menu: SelectionSubMenu | None = None
        self._state_menu: SelectionSubMenu | None = None

    def open(self) -> None:
        """Open the menu with updated title."""
        self.title = t("menu.flight_settings.title")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        items = []

        # 1. Aircraft selection
        aircraft_display = self._aircraft_name or t("common.not_set")
        items.append(
            MenuItem(
                "aircraft",
                t("menu.flight_settings.aircraft_value", aircraft=aircraft_display),
                action=self._open_aircraft_menu,
            )
        )

        # 2. From Airport
        from_display = self._get_airport_display(self._from_airport)
        items.append(
            MenuItem(
                "from_airport",
                t("menu.flight_settings.from_airport_value", airport=from_display),
                action=self._open_from_airport_menu,
            )
        )

        # 3. Circuit Training toggle (placed after From Airport)
        circuit_label = (
            t("menu.flight_settings.circuit_training_on")
            if self._circuit_training
            else t("menu.flight_settings.circuit_training_off")
        )
        items.append(
            MenuItem(
                "circuit_training",
                circuit_label,
                action=self._toggle_circuit_training,
            )
        )

        # 4. To Airport (only if not circuit training)
        if not self._circuit_training:
            to_display = self._get_airport_display(self._to_airport)
            items.append(
                MenuItem(
                    "to_airport",
                    t("menu.flight_settings.to_airport_value", airport=to_display),
                    action=self._open_to_airport_menu,
                )
            )

        # 5. Passengers
        items.append(
            MenuItem(
                "passengers",
                t("menu.flight_settings.passengers_value", count=self._passengers),
                action=self._open_passengers_menu,
            )
        )

        # 6. Fuel
        fuel_display = (
            f"{int(self._fuel_gallons)}" if self._fuel_gallons is not None else t("common.not_set")
        )
        items.append(
            MenuItem(
                "fuel",
                t("menu.flight_settings.fuel_value", gallons=fuel_display),
                action=self._open_fuel_menu,
            )
        )

        # 7. Initial Position
        position_display = self._get_position_display(self._initial_position)
        items.append(
            MenuItem(
                "initial_position",
                t("menu.flight_settings.initial_position_value", position=position_display),
                action=self._open_position_menu,
            )
        )

        # 8. Initial State
        state_display = self._get_state_display(self._initial_state)
        items.append(
            MenuItem(
                "initial_state",
                t("menu.flight_settings.initial_state_value", state=state_display),
                action=self._open_state_menu,
            )
        )

        # Back
        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

    def _get_airport_display(self, icao: str | None) -> str:
        """Get display name for an airport."""
        if not icao:
            return t("common.not_set")

        try:
            from airborne.airports.airport_index import get_airport_index

            index = get_airport_index()
            airport = index.get(icao)
            if airport:
                return airport.short_name()
        except Exception:
            pass

        return icao

    def _get_position_display(self, position: SpawnLocation) -> str:
        """Get display name for a spawn position."""
        if position == SpawnLocation.RAMP:
            return t("menu.flight_settings.position_parking")
        elif position == SpawnLocation.RUNWAY:
            return t("menu.flight_settings.position_runway")
        return position.value

    def _get_state_display(self, state: EngineState) -> str:
        """Get display name for an engine state."""
        if state == EngineState.COLD_AND_DARK:
            return t("menu.flight_settings.state_cold_and_dark")
        elif state == EngineState.READY_TO_START:
            return t("menu.flight_settings.state_ready_to_start")
        elif state == EngineState.READY_FOR_TAKEOFF:
            return t("menu.flight_settings.state_ready_for_takeoff")
        return state.value

    def _toggle_circuit_training(self) -> None:
        """Toggle circuit training mode."""
        self._circuit_training = not self._circuit_training
        self.items = self._build_items()

        if self._circuit_training:
            self._speak(t("menu.flight_settings.circuit_training_on"))
        else:
            self._speak(t("menu.flight_settings.circuit_training_off"))

    def _open_aircraft_menu(self) -> None:
        """Open aircraft selection submenu."""
        if not self._aircraft_menu:
            self._aircraft_menu = AircraftSubMenu(self, self._on_aircraft_selected)
        self._aircraft_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._aircraft_menu.open()
        self._active_child = self._aircraft_menu

    def _on_aircraft_selected(self, aircraft_id: str, aircraft_name: str, config: dict) -> None:
        """Handle aircraft selection."""
        self._aircraft = aircraft_id
        self._aircraft_name = aircraft_name

        # Update capacity limits from aircraft config
        self._update_aircraft_limits(config)

        # Rebuild items to show new selection
        self.items = self._build_items()

    def _update_aircraft_limits(self, config: dict) -> None:
        """Update passenger and fuel limits from aircraft config."""
        try:
            aircraft_config = config.get("aircraft", {})

            # Get max passengers (count seats minus pilot)
            weight_balance = aircraft_config.get("weight_balance", {})
            seats = weight_balance.get("stations", {}).get("seats", [])
            # Count seats, minus 1 for pilot
            self._max_passengers = max(0, len(seats) - 1)

            # Get max fuel (total from all tanks)
            fuel_config = aircraft_config.get("fuel", {})
            tanks = fuel_config.get("tanks", {})
            total_fuel = 0.0
            for tank_name, tank_data in tanks.items():
                total_fuel += tank_data.get("capacity_usable", 0.0)
            if total_fuel > 0:
                self._max_fuel = total_fuel

            # Set default fuel to full if not set
            if self._fuel_gallons is None:
                self._fuel_gallons = self._max_fuel

            logger.debug(
                "Aircraft limits: max_passengers=%d, max_fuel=%.1f",
                self._max_passengers,
                self._max_fuel,
            )
        except Exception as e:
            logger.warning("Failed to parse aircraft limits: %s", e)

    def _open_from_airport_menu(self) -> None:
        """Open from airport selection."""
        if not self._from_airport_menu:
            self._from_airport_menu = AirportSubMenu(
                self,
                t("menu.flight_settings.from_airport"),
                self._on_from_airport_selected,
            )
        self._from_airport_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._from_airport_menu.open()
        self._active_child = self._from_airport_menu

    def _on_from_airport_selected(self, icao: str | None) -> None:
        """Handle from airport selection."""
        self._from_airport = icao
        self.items = self._build_items()

    def _open_to_airport_menu(self) -> None:
        """Open to airport selection."""
        if not self._to_airport_menu:
            self._to_airport_menu = AirportSubMenu(
                self,
                t("menu.flight_settings.to_airport"),
                self._on_to_airport_selected,
            )
        self._to_airport_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._to_airport_menu.open()
        self._active_child = self._to_airport_menu

    def _on_to_airport_selected(self, icao: str | None) -> None:
        """Handle to airport selection."""
        self._to_airport = icao
        self.items = self._build_items()

    def _open_passengers_menu(self) -> None:
        """Open passengers input."""
        if not self._passengers_menu:
            self._passengers_menu = NumberInputSubMenu(
                self,
                t("menu.flight_settings.passengers"),
                min_value=0,
                max_value=self._max_passengers,
                current_value=self._passengers,
                unit="",
                on_selected=self._on_passengers_selected,
            )
        else:
            # Update max in case aircraft changed
            self._passengers_menu._max_value = self._max_passengers
            self._passengers_menu._current_value = self._passengers
        self._passengers_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._passengers_menu.open()
        self._active_child = self._passengers_menu

    def _on_passengers_selected(self, count: int) -> None:
        """Handle passengers selection."""
        self._passengers = count
        self.items = self._build_items()

    def _open_fuel_menu(self) -> None:
        """Open fuel input."""
        if not self._fuel_menu:
            self._fuel_menu = NumberInputSubMenu(
                self,
                t("menu.flight_settings.fuel"),
                min_value=0,
                max_value=self._max_fuel,
                current_value=self._fuel_gallons,
                unit="gallons",
                on_selected=self._on_fuel_selected,
            )
        else:
            # Update max in case aircraft changed
            self._fuel_menu._max_value = self._max_fuel
            self._fuel_menu._current_value = self._fuel_gallons
        self._fuel_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._fuel_menu.open()
        self._active_child = self._fuel_menu

    def _on_fuel_selected(self, gallons: float) -> None:
        """Handle fuel selection."""
        self._fuel_gallons = gallons
        self.items = self._build_items()

    def _open_position_menu(self) -> None:
        """Open position selection."""
        options = [
            (SpawnLocation.RAMP, t("menu.flight_settings.position_parking")),
            (SpawnLocation.RUNWAY, t("menu.flight_settings.position_runway")),
        ]
        if not self._position_menu:
            self._position_menu = SelectionSubMenu(
                self,
                t("menu.flight_settings.initial_position"),
                options,
                self._initial_position,
                self._on_position_selected,
            )
        self._position_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._position_menu.open()
        self._active_child = self._position_menu

    def _on_position_selected(self, position: SpawnLocation) -> None:
        """Handle position selection."""
        self._initial_position = position
        self.items = self._build_items()

    def _open_state_menu(self) -> None:
        """Open state selection."""
        options = [
            (EngineState.COLD_AND_DARK, t("menu.flight_settings.state_cold_and_dark")),
            (EngineState.READY_TO_START, t("menu.flight_settings.state_ready_to_start")),
            (EngineState.READY_FOR_TAKEOFF, t("menu.flight_settings.state_ready_for_takeoff")),
        ]
        if not self._state_menu:
            self._state_menu = SelectionSubMenu(
                self,
                t("menu.flight_settings.initial_state"),
                options,
                self._initial_state,
                self._on_state_selected,
            )
        self._state_menu.set_audio_callbacks(
            speak=self._speak_callback,
            play_sound=self._play_sound_callback,
            tts_client=self._tts_client,
        )
        self._state_menu.open()
        self._active_child = self._state_menu

    def _on_state_selected(self, state: EngineState) -> None:
        """Handle state selection."""
        self._initial_state = state
        self.items = self._build_items()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with child menu management."""
        # Check if active child closed
        if self._active_child and not self._active_child.is_open:
            self._active_child = None
            self._announce_current_item()
            return True

        return super().handle_key(key, unicode)

    # Public getters for flight config
    def get_aircraft(self) -> str | None:
        """Get selected aircraft ID."""
        return self._aircraft

    def get_from_airport(self) -> str | None:
        """Get departure airport ICAO."""
        return self._from_airport

    def get_to_airport(self) -> str | None:
        """Get arrival airport ICAO."""
        return self._to_airport

    def get_circuit_training(self) -> bool:
        """Get circuit training mode."""
        return self._circuit_training

    def get_passengers(self) -> int:
        """Get passenger count."""
        return self._passengers

    def get_fuel_gallons(self) -> float | None:
        """Get fuel in gallons."""
        return self._fuel_gallons

    def get_initial_position(self) -> SpawnLocation:
        """Get initial spawn position."""
        return self._initial_position

    def get_initial_state(self) -> EngineState:
        """Get initial engine state."""
        return self._initial_state

    def is_ready_to_fly(self) -> bool:
        """Check if minimum requirements are met to fly."""
        return self._aircraft is not None and self._from_airport is not None


class AircraftSubMenu(AudioMenu):
    """Aircraft selection submenu."""

    def __init__(
        self,
        parent: AudioMenu,
        on_selected: Callable[[str, str, dict], None],
    ) -> None:
        """Initialize aircraft submenu."""
        super().__init__(t("menu.flight_settings.aircraft"), parent)
        self._on_selected = on_selected
        self._aircraft_list: list[dict[str, Any]] = []

    def open(self) -> None:
        """Open and load aircraft list."""
        self._load_aircraft_list()
        super().open()

    def _load_aircraft_list(self) -> None:
        """Load available aircraft from config/aircraft directory."""
        self._aircraft_list = []

        try:
            aircraft_dir = get_resource_path("config/aircraft")
            if not aircraft_dir.exists():
                return

            for yaml_file in sorted(aircraft_dir.glob("*.yaml")):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        config = yaml.safe_load(f)

                    if config:
                        aircraft_data = config.get("aircraft", config)
                        aircraft_id = yaml_file.stem
                        name = aircraft_data.get("name", aircraft_id)

                        self._aircraft_list.append(
                            {
                                "id": aircraft_id,
                                "name": name,
                                "config": config,
                                "path": str(yaml_file),
                            }
                        )
                except Exception as e:
                    logger.warning("Failed to load aircraft config %s: %s", yaml_file, e)

        except Exception as e:
            logger.error("Failed to scan aircraft directory: %s", e)

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        items = []

        for aircraft in self._aircraft_list:
            items.append(
                MenuItem(
                    aircraft["id"],
                    aircraft["name"],
                    action=partial(self._select, aircraft),
                )
            )

        if not items:
            items.append(MenuItem("none", t("common.none_available"), enabled=False))

        items.append(MenuItem("back", t("common.go_back"), action=self.close))
        return items

    def _select(self, aircraft: dict) -> None:
        """Select an aircraft."""
        self._speak(f"Selected: {aircraft['name']}")
        self._on_selected(aircraft["id"], aircraft["name"], aircraft["config"])
        self.close()


class AirportSubMenu(AudioMenu):
    """Airport selection submenu with autocomplete."""

    def __init__(
        self,
        parent: AudioMenu,
        title: str,
        on_selected: Callable[[str | None], None],
    ) -> None:
        """Initialize airport submenu."""
        super().__init__(title, parent)
        self._on_selected = on_selected
        self._widget: Any = None

    def open(self) -> None:
        """Open and create text input widget."""
        from airborne.ui.widgets.text_input import TextInputWidget

        self.is_open = True

        # Create text input widget with autocomplete
        self._widget = TextInputWidget(
            widget_id="airport",
            label=self.title,
            search_func=self._search_airports,
            min_query_length=2,
            max_suggestions=8,
            uppercase=True,
            on_submit=self._on_submit,
        )
        self._widget.set_audio_callbacks(
            speak=self._speak_callback,
            click=lambda path: self._play_sound_callback(path, 0.7)
            if self._play_sound_callback
            else None,
        )
        self._widget.activate()

        self._speak(f"{self.title}. Type ICAO code or city name.")

    def _search_airports(self, query: str) -> list[tuple[str, str]]:
        """Search airports for autocomplete."""
        try:
            from airborne.airports.airport_index import get_airport_index

            index = get_airport_index()
            results = index.search(query, limit=8)
            return [(a.icao, a.display_name()) for a in results]
        except Exception as e:
            logger.error("Airport search failed: %s", e)
            return []

    def _on_submit(self, event: Any) -> None:
        """Handle airport selection."""
        icao = event.value
        if icao:
            try:
                from airborne.airports.airport_index import get_airport_index

                index = get_airport_index()
                airport = index.get(icao)
                if airport:
                    self._speak(f"Selected: {airport.display_name()}")
                else:
                    self._speak(f"Selected: {icao}")
            except Exception:
                self._speak(f"Selected: {icao}")

        self._on_selected(icao)
        self.close()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input."""
        if not self.is_open:
            return False

        try:
            import pygame
        except ImportError:
            return False

        # Escape - go back without selecting
        if key == pygame.K_ESCAPE:
            self._play_click("switch")
            self._speak(t("common.cancelled"))
            self.close()
            return True

        # Delegate to widget
        if self._widget:
            return self._widget.handle_key(key, unicode)

        return False

    def _build_items(self) -> list[MenuItem]:
        """Not used - this menu uses a widget."""
        return []


class NumberInputSubMenu(AudioMenu):
    """Number input submenu."""

    def __init__(
        self,
        parent: AudioMenu,
        title: str,
        min_value: float,
        max_value: float,
        current_value: float | None,
        unit: str,
        on_selected: Callable[[float], None],
    ) -> None:
        """Initialize number input submenu."""
        super().__init__(title, parent)
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = current_value
        self._unit = unit
        self._on_selected = on_selected
        self._widget: Any = None

    def open(self) -> None:
        """Open and create number input widget."""
        from airborne.ui.widgets.number_input import NumberInputWidget

        self.is_open = True

        self._widget = NumberInputWidget(
            widget_id="number",
            label=self.title,
            min_value=self._min_value,
            max_value=self._max_value,
            default_value=self._current_value,
            allow_decimal=self._unit == "gallons",
            unit=self._unit,
            on_submit=self._on_submit,
        )
        self._widget.set_audio_callbacks(
            speak=self._speak_callback,
            click=lambda path: self._play_sound_callback(path, 0.7)
            if self._play_sound_callback
            else None,
        )
        self._widget.activate()

    def _on_submit(self, event: Any) -> None:
        """Handle number submission."""
        value = event.value
        if value is not None:
            self._on_selected(value)
        self.close()

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input."""
        if not self.is_open:
            return False

        if self._widget:
            consumed = self._widget.handle_key(key, unicode)
            # Check if widget closed (submitted)
            if not self.is_open:
                return True
            return consumed

        return False

    def _build_items(self) -> list[MenuItem]:
        """Not used - this menu uses a widget."""
        return []


class SelectionSubMenu(AudioMenu):
    """Generic selection submenu for options like position and state."""

    def __init__(
        self,
        parent: AudioMenu,
        title: str,
        options: list[tuple[Any, str]],
        current_value: Any,
        on_selected: Callable[[Any], None],
    ) -> None:
        """Initialize selection submenu."""
        super().__init__(title, parent)
        self._options = options
        self._current_value = current_value
        self._on_selected = on_selected

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        items = []

        for value, label in self._options:
            # Mark current selection
            display = f"{label} *" if value == self._current_value else label
            items.append(
                MenuItem(
                    str(value),
                    display,
                    action=partial(self._select, value, label),
                )
            )

        items.append(MenuItem("back", t("common.go_back"), action=self.close))
        return items

    def _select(self, value: Any, label: str) -> None:
        """Select an option."""
        self._speak(f"Selected: {label}")
        self._on_selected(value)
        self.close()


class SettingsMenu(AudioMenu):
    """Settings submenu.

    Contains Voice Settings, Language, and other configuration.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize settings menu."""
        super().__init__(t("menu.settings.title"), parent)
        self._voice_settings_menu: VoiceSettingsMenu | None = None
        self._language_menu: LanguageMenu | None = None
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback
        # Propagate to existing voice settings menu
        if self._voice_settings_menu:
            self._voice_settings_menu.set_on_ui_voice_change(callback)
        # Propagate to existing language menu
        if self._language_menu:
            self._language_menu.set_on_ui_voice_change(callback)

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback
        # Propagate to existing language menu
        if self._language_menu:
            self._language_menu.set_on_language_change(callback)

    def open(self) -> None:
        """Open the menu with updated title."""
        self.title = t("menu.settings.title")
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items."""
        if not self._voice_settings_menu:
            self._voice_settings_menu = VoiceSettingsMenu(self)
            if self._on_ui_voice_change:
                self._voice_settings_menu.set_on_ui_voice_change(self._on_ui_voice_change)
        if not self._language_menu:
            self._language_menu = LanguageMenu(self)
            if self._on_ui_voice_change:
                self._language_menu.set_on_ui_voice_change(self._on_ui_voice_change)
            if self._on_language_change:
                self._language_menu.set_on_language_change(self._on_language_change)

        return [
            MenuItem(
                "voice_settings",
                t("menu.settings.voice_settings"),
                submenu=self._voice_settings_menu,
            ),
            MenuItem(
                "language",
                t("menu.settings.language"),
                submenu=self._language_menu,
            ),
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            ),
        ]


class LanguageMenu(AudioMenu):
    """Language selection menu.

    Allows selecting the UI language.
    """

    def __init__(self, parent: AudioMenu | None = None) -> None:
        """Initialize language menu."""
        from airborne.core.i18n import SUPPORTED_LANGUAGES, get_language

        super().__init__(t("menu.settings.language"), parent)
        self._supported_languages = SUPPORTED_LANGUAGES
        self._current_language = get_language()
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback

    def open(self) -> None:
        """Open the menu with updated title and current language."""
        from airborne.core.i18n import get_language

        self.title = t("menu.settings.language")
        self._current_language = get_language()
        super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build menu items for each language."""
        from functools import partial

        items = []

        for lang_code, lang_name in self._supported_languages.items():
            # Show checkmark for current language
            label = f"{lang_name} *" if lang_code == self._current_language else lang_name
            items.append(
                MenuItem(
                    lang_code,
                    label,
                    action=partial(self._select_language, lang_code),
                )
            )

        items.append(
            MenuItem(
                "back",
                t("common.go_back"),
                action=self.close,
            )
        )

        return items

    def _select_language(self, lang_code: str) -> None:
        """Select a language and save to settings.

        Args:
            lang_code: Language code to select.
        """
        from airborne.core.i18n import set_language
        from airborne.settings import get_tts_settings

        if lang_code == self._current_language:
            self._speak(t("common.selected"))
            return

        # Update i18n system
        set_language(lang_code)
        self._current_language = lang_code

        # Save to settings and reset voices to language defaults
        settings = get_tts_settings()
        settings.set_language(lang_code, reset_voices=True)
        settings.save()

        # Notify about UI voice change so TTS uses the new language voice
        if self._on_ui_voice_change:
            ui_voice = settings.get_voice("ui")
            self._on_ui_voice_change(ui_voice.voice_name, ui_voice.rate)

        # Notify about language change to trigger voice cache refresh
        if self._on_language_change:
            self._on_language_change(lang_code)

        # Announce in new language
        self._speak(t("common.saved"))

        # Rebuild menu items to update checkmarks
        self.items = self._build_items()

        # Propagate translation reload to parent menus
        self.reload_translations()


class MainMenu(AudioMenu):
    """Main menu for AirBorne.

    Top-level menu shown at game startup.
    """

    # Menu result codes
    RESULT_NONE = None
    RESULT_FLY = "fly"
    RESULT_EXIT = "exit"

    def __init__(self) -> None:
        """Initialize main menu."""
        super().__init__(t("menu.main.title"))
        self._flight_settings_menu: FlightSettingsMenu | None = None
        self._settings_menu: SettingsMenu | None = None
        self._result: str | None = None

        # Callbacks for menu actions
        self._on_fly: Callable[[], None] | None = None
        self._on_exit: Callable[[], None] | None = None

        # UI voice change callback
        self._on_ui_voice_change: Callable[[str, int], None] | None = None
        self._on_language_change: Callable[[str], None] | None = None

    def set_on_ui_voice_change(self, callback: Callable[[str, int], None]) -> None:
        """Set callback for when UI voice settings change.

        Args:
            callback: Function(voice_name, rate) called on change.
        """
        self._on_ui_voice_change = callback
        # Propagate to existing settings menu
        if self._settings_menu:
            self._settings_menu.set_on_ui_voice_change(callback)

    def set_on_language_change(self, callback: Callable[[str], None]) -> None:
        """Set callback for when language changes.

        Args:
            callback: Function(language_code) called on change.
        """
        self._on_language_change = callback
        # Propagate to existing settings menu
        if self._settings_menu:
            self._settings_menu.set_on_language_change(callback)

    def set_callbacks(
        self,
        on_fly: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        """Set action callbacks.

        Args:
            on_fly: Called when Fly! is selected.
            on_exit: Called when Exit is selected.
        """
        self._on_fly = on_fly
        self._on_exit = on_exit

    def open(self, is_startup: bool = False) -> None:
        """Open the menu with welcome announcement on startup.

        Args:
            is_startup: If True, announce "AirBorne" first (initial launch).
        """
        self.title = t("menu.main.title")

        if is_startup:
            # Startup sequence: "AirBorne" -> menu title -> first item
            self.items = self._build_items()
            self.selected_index = 0
            self.is_open = True
            self._active_child = None

            # Build announcement: "AirBorne. Main Menu. 4 items. Fly!"
            welcome = t("menu.main.welcome")
            item_count = f"{len(self.items)} items."
            first_item = self.items[0].label if self.items else ""
            announcement = f"{welcome}. {self.title}. {item_count} {first_item}"
            self._speak(announcement)
        else:
            # Normal submenu return - standard behavior
            super().open()

    def _build_items(self) -> list[MenuItem]:
        """Build main menu items."""
        if not self._flight_settings_menu:
            self._flight_settings_menu = FlightSettingsMenu(self)
        if not self._settings_menu:
            self._settings_menu = SettingsMenu(self)
            if self._on_ui_voice_change:
                self._settings_menu.set_on_ui_voice_change(self._on_ui_voice_change)
            if self._on_language_change:
                self._settings_menu.set_on_language_change(self._on_language_change)

        # Check if ready to fly (aircraft and airport selected)
        ready_to_fly = self._flight_settings_menu.is_ready_to_fly()

        return [
            MenuItem(
                "fly",
                t("menu.main.fly") if ready_to_fly else t("menu.main.fly_disabled"),
                action=self._start_flight,
                enabled=ready_to_fly,
            ),
            MenuItem(
                "flight_settings",
                t("menu.main.fly_settings"),
                submenu=self._flight_settings_menu,
            ),
            MenuItem(
                "settings",
                t("menu.main.settings"),
                submenu=self._settings_menu,
            ),
            MenuItem(
                "about",
                t("menu.main.about"),
                action=self._show_about,
            ),
            MenuItem(
                "exit",
                t("menu.main.exit"),
                action=self._exit_game,
            ),
        ]

    def handle_key(self, key: int, unicode: str = "") -> bool:
        """Handle keyboard input with menu refresh after returning from submenus."""
        # Check if child closed - rebuild items in case flight settings changed
        if self._active_child and not self._active_child.is_open:
            self._active_child = None
            self.items = self._build_items()  # Refresh fly button state
            self._announce_current_item()
            return True

        return super().handle_key(key, unicode)

    def _start_flight(self) -> None:
        """Start the flight.

        Note: Does not close menu - the menu runner handles closing after
        the music fadeout completes.
        """
        self._result = self.RESULT_FLY
        self._speak(t("menu.main.starting_flight"))

        if self._on_fly:
            self._on_fly()

    def _show_about(self) -> None:
        """Show about information via TTS."""
        from airborne.version import get_about_info

        info = get_about_info()
        # Build about message: "AirBorne version 0.1.0. By Yannick Mauray. MIT License."
        about_text = t(
            "menu.main.about_text",
            name=info["name"],
            version=info["version"],
            author=info["author"],
            license=info["license"],
        )
        self._speak(about_text)

    def _exit_game(self) -> None:
        """Exit the game."""
        self._result = self.RESULT_EXIT
        self._speak(t("menu.main.goodbye"))

        if self._on_exit:
            self._on_exit()

        self.close()

    def get_result(self) -> str | None:
        """Get menu result.

        Returns:
            "fly", "exit", or None.
        """
        return self._result

    def get_flight_config(self) -> dict[str, Any]:
        """Get full flight configuration from menu selections.

        Returns:
            Dictionary with all flight settings.
        """
        config: dict[str, Any] = {
            "departure": None,
            "arrival": None,
            "aircraft": None,
            "circuit_training": False,
            "passengers": 0,
            "fuel_gallons": None,
            "initial_position": SpawnLocation.RAMP,
            "initial_state": EngineState.COLD_AND_DARK,
        }

        if self._flight_settings_menu:
            config["departure"] = self._flight_settings_menu.get_from_airport()
            config["arrival"] = self._flight_settings_menu.get_to_airport()
            config["aircraft"] = self._flight_settings_menu.get_aircraft()
            config["circuit_training"] = self._flight_settings_menu.get_circuit_training()
            config["passengers"] = self._flight_settings_menu.get_passengers()
            config["fuel_gallons"] = self._flight_settings_menu.get_fuel_gallons()
            config["initial_position"] = self._flight_settings_menu.get_initial_position()
            config["initial_state"] = self._flight_settings_menu.get_initial_state()

        return config
