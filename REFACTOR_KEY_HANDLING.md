# Key Handling System Refactoring Proposal

## Current Problems

### 1. Hard-coded Priority in main.py
```python
# Priority is implicit in if/elif order
if checklist_menu.is_open():
    ...
elif atc_menu.is_open():
    ...
elif ground_services_menu.is_open():
    ...
elif control_panel.handle_key_press():
    ...
```

### 2. Scattered Configuration
- Passthrough keys defined inside `control_panel_plugin.py` (lines 905-954)
- Menu key bindings in `main.py`
- Flight controls in `input.py`
- No single source of truth

### 3. Tight Coupling
- main.py directly checks each menu's `is_open()` state
- main.py calls menu-specific handlers (`_handle_checklist_menu_key`, etc.)
- Adding new menus requires modifying main.py

### 4. No Standard Interface
- Menus return bool (handled/not handled)
- Control panel returns bool (consumed/passthrough)
- InputManager receives remaining events
- Inconsistent semantics

### 5. Context-Awareness Complexity
- Keys have dual purposes (S = speed OR starter)
- Panel-specific handling mixed with global handling
- Comments explain conflicts ("unless in Flight Controls panel")

---

## Proposed Architecture

### Core Concepts

1. **KeyHandler Interface**: All key consumers implement standard interface
2. **Priority Chain**: Ordered list of handlers with explicit priorities
3. **Key Registry**: Central database of all key bindings
4. **External Config**: YAML files for all key configurations
5. **Handler Manager**: Coordinates event dispatch

---

## Phase 1: Extract Key Handler Interface (2-3 hours)

### Goal
Create a standard interface for all key handlers without changing existing behavior.

### Steps

**1.1: Create KeyHandler ABC** (`src/airborne/core/key_handler.py`)
```python
from abc import ABC, abstractmethod

class KeyHandler(ABC):
    """Standard interface for keyboard input handlers."""

    @abstractmethod
    def get_priority(self) -> int:
        """Return handler priority (lower = higher priority).

        Suggested ranges:
        - 0-99: Modal overlays (menus, dialogs)
        - 100-199: Context handlers (control panel)
        - 200+: Default handlers (flight controls)
        """
        pass

    @abstractmethod
    def can_handle_key(self, key: int, mods: int) -> bool:
        """Check if this handler wants to process this key.

        Args:
            key: pygame key constant
            mods: pygame modifier flags

        Returns:
            True if this handler should receive the key
        """
        pass

    @abstractmethod
    def handle_key(self, key: int, mods: int) -> bool:
        """Process a key press.

        Args:
            key: pygame key constant
            mods: pygame modifier flags

        Returns:
            True if key was consumed (stop propagation)
            False if key should continue to next handler
        """
        pass

    def is_active(self) -> bool:
        """Check if handler is currently active.

        Default: always active.
        Override for conditional handlers (e.g., menus).

        Returns:
            True if handler should be considered
        """
        return True
```

**1.2: Create Handler Manager** (`src/airborne/core/key_handler_manager.py`)
```python
class KeyHandlerManager:
    """Manages priority-based key event dispatch."""

    def __init__(self):
        self._handlers: list[KeyHandler] = []

    def register(self, handler: KeyHandler) -> None:
        """Register a key handler and sort by priority."""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.get_priority())

    def unregister(self, handler: KeyHandler) -> None:
        """Remove a handler from the chain."""
        self._handlers.remove(handler)

    def process_key(self, key: int, mods: int) -> bool:
        """Dispatch key to handlers in priority order.

        Returns:
            True if any handler consumed the key
        """
        for handler in self._handlers:
            if not handler.is_active():
                continue

            if handler.can_handle_key(key, mods):
                if handler.handle_key(key, mods):
                    return True  # Key consumed, stop propagation

        return False  # Key not handled
```

**1.3: Wrap Existing Handlers**

Create adapter classes that wrap existing code:

```python
class MenuKeyHandler(KeyHandler):
    """Adapter for menu-based key handling."""

    def __init__(self, menu, handler_func, priority: int = 10):
        self._menu = menu
        self._handler_func = handler_func
        self._priority = priority

    def get_priority(self) -> int:
        return self._priority

    def is_active(self) -> bool:
        return self._menu.is_open()

    def can_handle_key(self, key: int, mods: int) -> bool:
        # All keys when menu is open
        return True

    def handle_key(self, key: int, mods: int) -> bool:
        return self._handler_func(key)


class ControlPanelKeyHandler(KeyHandler):
    """Adapter for control panel key handling."""

    def __init__(self, panel_plugin):
        self._panel = panel_plugin

    def get_priority(self) -> int:
        return 100  # After menus

    def can_handle_key(self, key: int, mods: int) -> bool:
        # Panel always gets a chance
        return True

    def handle_key(self, key: int, mods: int) -> bool:
        return self._panel.handle_key_press(key, mods)
```

**1.4: Update main.py**

Replace the if/elif chain with handler manager:

```python
def __init__(self, ...):
    # ... existing init ...

    # Create handler manager
    self.key_handler_manager = KeyHandlerManager()

def _initialize_key_handlers(self):
    """Register all key handlers in priority order."""

    # Priority 10: Checklist menu
    if hasattr(self, 'checklist_plugin'):
        handler = MenuKeyHandler(
            self.checklist_plugin.checklist_menu,
            self._handle_checklist_menu_key,
            priority=10
        )
        self.key_handler_manager.register(handler)

    # Priority 20: ATC menu
    if hasattr(self, 'radio_plugin'):
        handler = MenuKeyHandler(
            self.radio_plugin.atc_menu,
            self._handle_atc_menu_key,
            priority=20
        )
        self.key_handler_manager.register(handler)

    # Priority 30: Ground services menu
    if hasattr(self, 'ground_services_plugin'):
        handler = MenuKeyHandler(
            self.ground_services_plugin.ground_services_menu,
            self._handle_ground_services_menu_key,
            priority=30
        )
        self.key_handler_manager.register(handler)

    # Priority 100: Control panel
    if hasattr(self, 'control_panel_plugin'):
        handler = ControlPanelKeyHandler(self.control_panel_plugin)
        self.key_handler_manager.register(handler)

def _process_events(self) -> None:
    """Process pygame events."""
    events = pygame.event.get()
    remaining_events = []

    for event in events:
        if event.type == pygame.QUIT:
            self.running = False
            remaining_events.append(event)
        elif event.type == pygame.VIDEORESIZE:
            # ... handle resize ...
            remaining_events.append(event)
        elif event.type == pygame.KEYDOWN:
            # Try handler chain
            mods = pygame.key.get_mods()
            handled = self.key_handler_manager.process_key(event.key, mods)

            if not handled:
                remaining_events.append(event)
        else:
            remaining_events.append(event)

    # Pass remaining to InputManager
    self.input_manager.process_events(remaining_events)
```

**Benefits:**
- ✅ Explicit priority order (no more if/elif guessing)
- ✅ Easier to add new handlers (no main.py changes)
- ✅ Clear separation of concerns
- ✅ Backward compatible (wraps existing code)

**Testing:**
- All existing tests should pass unchanged
- Behavior identical to current implementation

---

## Phase 2: External Key Configuration (3-4 hours)

### Goal
Move all key bindings to YAML files for easy configuration.

### Steps

**2.1: Create Key Binding Config** (`config/keybindings/`)

```yaml
# config/keybindings/passthrough_keys.yaml
# Keys that control panel should NOT consume
passthrough:
  flight_controls:
    - UP
    - DOWN
    - LEFT
    - RIGHT
    - HOME
    - END
    - PAGEUP
    - PAGEDOWN
    - COMMA  # Yaw left
    - PERIOD  # Yaw right

  menus:
    - F1  # ATC menu
    - F2  # Checklist menu
    - F3  # Ground services menu
    - TAB  # Menu toggle
    - RETURN  # Menu select
    - ESCAPE  # Menu back

  instruments:
    - S  # Speed
    - L  # Altitude
    - H  # Heading
    - W  # Vertical speed
    - T  # Attitude

  tts:
    - N  # Next
    - R  # Repeat
    - I  # Interrupt

  numbers:
    - "1"
    - "2"
    - "3"
    - "4"
    - "5"
    - "6"
    - "7"
    - "8"
    - "9"

  system:
    - SPACE  # Pause

blocked:
  - G  # Always block to prevent gear toggle conflict
```

```yaml
# config/keybindings/panel_contexts.yaml
# Context-specific key bindings for each panel
panels:
  instrument_panel:
    controls:
      M: master_switch
      A: avionics_master_switch
      B: beacon_switch
      N: nav_lights_switch
      S: strobe_switch
      T: taxi_light_switch
      L: landing_light_switch

  pedestal:
    controls:
      M: mixture_lever
      C: carburetor_heat_lever
      T: throttle_lever
      F: fuel_selector_valve
      V: fuel_shutoff_valve
      P: fuel_pump_switch
      R: primer_pump

  engine_controls:
    controls:
      G: magneto_switch
      S: starter_button

  overhead_panel:
    controls:
      H: pitot_heat_switch

  flight_controls:
    controls:
      F: flaps_lever
      E: elevator_trim_wheel
      B: parking_brake_lever
```

**2.2: Create Config Loader**

```python
# src/airborne/core/key_config.py
class KeyBindingConfig:
    """Loads and manages key binding configuration."""

    def __init__(self, config_dir: Path):
        self.passthrough_keys = self._load_passthrough(config_dir)
        self.blocked_keys = self._load_blocked(config_dir)
        self.panel_contexts = self._load_panel_contexts(config_dir)

    def _load_passthrough(self, config_dir: Path) -> set[int]:
        """Load passthrough keys from YAML."""
        config = yaml.load(config_dir / "keybindings" / "passthrough_keys.yaml")

        keys = set()
        for category, key_names in config['passthrough'].items():
            for key_name in key_names:
                keys.add(getattr(pygame, f"K_{key_name.upper()}"))

        return keys

    def is_passthrough(self, key: int) -> bool:
        """Check if key should pass through control panel."""
        return key in self.passthrough_keys

    def is_blocked(self, key: int) -> bool:
        """Check if key should be blocked by control panel."""
        return key in self.blocked_keys
```

**2.3: Update ControlPanelKeyHandler**

```python
class ControlPanelKeyHandler(KeyHandler):
    """Control panel key handler with external config."""

    def __init__(self, panel_plugin, config: KeyBindingConfig):
        self._panel = panel_plugin
        self._config = config

    def handle_key(self, key: int, mods: int) -> bool:
        # Check blocked keys first
        if self._config.is_blocked(key):
            return True  # Consume

        # Try panel-specific handling
        handled = self._panel.handle_panel_key(key, mods)
        if handled:
            return True

        # Check passthrough
        if self._config.is_passthrough(key):
            return False  # Don't consume

        # Default: consume all other keys
        return True
```

**Benefits:**
- ✅ All key bindings in one place (config/)
- ✅ Easy to customize without code changes
- ✅ Can create different profiles (beginner, advanced, custom)
- ✅ Documentation lives with configuration

---

## Phase 3: Plugin-Based Handler Registration (2-3 hours)

### Goal
Plugins register their own key handlers automatically.

### Steps

**3.1: Add Handler Registration to Plugin Interface**

```python
# src/airborne/core/plugin.py
class IPlugin(ABC):
    # ... existing methods ...

    def register_key_handlers(self, manager: KeyHandlerManager) -> None:
        """Register plugin's key handlers.

        Optional method - only implement if plugin handles keys.

        Args:
            manager: Key handler manager to register with
        """
        pass  # Default: no handlers
```

**3.2: Update Menu Plugins**

```python
# src/airborne/plugins/checklist/checklist_plugin.py
class ChecklistPlugin(IPlugin):
    # ... existing code ...

    def register_key_handlers(self, manager: KeyHandlerManager) -> None:
        """Register checklist menu key handler."""
        handler = MenuKeyHandler(
            menu=self.checklist_menu,
            handler_func=self._handle_menu_key,
            priority=10,  # High priority
            name="checklist_menu"
        )
        manager.register(handler)

    def _handle_menu_key(self, key: int) -> bool:
        """Handle key when menu is open."""
        # Move existing _handle_checklist_menu_key logic here
        if key == pygame.K_ESCAPE:
            self.checklist_menu.close()
            return True
        # ... etc
```

**3.3: Auto-register Handlers in main.py**

```python
def _load_plugin(self, plugin_class):
    """Load and initialize a plugin."""
    plugin = plugin_class()
    plugin.initialize(context)

    # Auto-register key handlers
    if hasattr(plugin, 'register_key_handlers'):
        plugin.register_key_handlers(self.key_handler_manager)

    return plugin
```

**Benefits:**
- ✅ Plugins self-contained (own key handling logic)
- ✅ main.py doesn't need to know about plugin keys
- ✅ Easy to disable plugin → keys automatically unregistered
- ✅ Plugin can register multiple handlers (menu, shortcuts, etc.)

---

## Phase 4: Handler Priority Configuration (1-2 hours)

### Goal
Make handler priorities externally configurable.

**4.1: Priority Configuration**

```yaml
# config/keybindings/handler_priorities.yaml
# Lower number = higher priority
priorities:
  checklist_menu: 10
  atc_menu: 20
  ground_services_menu: 30
  control_panel: 100
  flight_controls: 200
```

**4.2: Load Priorities**

```python
class KeyHandlerManager:
    def __init__(self, config_path: Path):
        self._handlers = []
        self._priorities = self._load_priorities(config_path)

    def register(self, handler: KeyHandler, name: str):
        """Register with configured priority."""
        priority = self._priorities.get(name, 999)
        handler.set_priority(priority)
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.get_priority())
```

**Benefits:**
- ✅ Easy to reorder handlers without code changes
- ✅ Can create profiles (menu-first vs panel-first)
- ✅ User customization supported

---

## Phase 5: Key Event System (Optional, 4-5 hours)

### Goal
Replace direct handling with event-driven system.

**5.1: Key Events**

```python
@dataclass
class KeyEvent:
    """Keyboard event with metadata."""
    key: int
    mods: int
    pressed: bool  # True = press, False = release
    repeat: bool   # True if key repeat
    timestamp: float

    def matches(self, key: int, mod: int = 0) -> bool:
        """Check if event matches key/modifier combo."""
        if mod:
            return self.key == key and (self.mods & mod)
        return self.key == key
```

**5.2: Handler Subscribes to Events**

```python
class KeyHandler(ABC):
    def subscribe_keys(self) -> list[KeyBinding]:
        """Return list of keys this handler wants.

        Returns:
            List of key bindings (key, mods, priority)
        """
        return []

    @abstractmethod
    def handle_event(self, event: KeyEvent) -> bool:
        """Handle a key event."""
        pass
```

**Benefits:**
- ✅ Handlers only receive keys they care about
- ✅ More efficient (no polling all handlers)
- ✅ Can subscribe to key combinations (Ctrl+S, etc.)
- ✅ Event history for debugging

---

## Summary: Phased Timeline

| Phase | Time | Benefit | Breaking Changes |
|-------|------|---------|------------------|
| 1: Interface | 2-3h | Clean architecture | None (adapters) |
| 2: Config | 3-4h | Easy customization | None (backward compat) |
| 3: Plugin Registration | 2-3h | Decoupling | Minor (plugin API) |
| 4: Priority Config | 1-2h | User customization | None |
| 5: Event System | 4-5h | Performance | Moderate (handler API) |

**Recommended Path:**
1. Start with **Phase 1** (interface) - immediate readability improvement
2. Add **Phase 2** (config) - unlocks user customization
3. Optionally add **Phase 3** (plugins) - cleaner architecture
4. **Phase 4-5** - only if needed (polish)

**Total Core Refactor: 5-7 hours (Phases 1-2)**

---

## Migration Strategy

1. **Phase 1**: Create new system alongside old
2. **Test**: Verify identical behavior with unit tests
3. **Switch**: Flip flag to use new system
4. **Monitor**: Run for 1 week with both systems
5. **Remove**: Delete old code once confident

**No user-facing changes until Phase 2.**
