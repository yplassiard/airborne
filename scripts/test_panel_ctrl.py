#!/usr/bin/env python3
"""Test panel control with Ctrl key press."""

import sys
import traceback

# Add parent directory to path
sys.path.insert(0, "src")

import pygame

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((800, 600))

# Import after pygame init
from airborne.core.message_queue import MessageQueue
from airborne.core.plugin_context import PluginContext

from airborne.core.event_bus import EventBus
from airborne.core.registry import ComponentRegistry
from airborne.plugins.panel.control_panel_plugin import ControlPanelPlugin

# Create plugin context
event_bus = EventBus()
message_queue = MessageQueue(event_bus)
registry = ComponentRegistry()
context = PluginContext(
    event_bus=event_bus,
    message_queue=message_queue,
    plugin_registry=registry,
    config={"panels": {"definition": "config/panels/cessna172_panel.yaml"}},
)

# Create and initialize plugin
plugin = ControlPanelPlugin()
plugin.initialize(context)

print("Plugin initialized successfully")
print(f"Current panel: {plugin.current_panel_index}")
print(f"Has {len(plugin.panels)} panels")

# Test Ctrl+1 key press
print("\nTesting Ctrl+1 key press...")
try:
    result = plugin.handle_key_press(pygame.K_1, pygame.KMOD_CTRL)
    print(f"Result: {result}")
    print(f"Current panel after Ctrl+1: {plugin.current_panel_index}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()

# Test Ctrl+Q (should not crash, just return False)
print("\nTesting Ctrl+Q key press...")
try:
    result = plugin.handle_key_press(pygame.K_q, pygame.KMOD_CTRL)
    print(f"Result: {result}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()

print("\nTest complete")
pygame.quit()
