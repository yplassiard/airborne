#!/usr/bin/env python3
"""Test script to debug instrument key speech output."""

import pygame
from airborne.audio.tts.pyttsx_provider import PyTTSXProvider

from airborne.audio.tts.base import TTSPriority
from airborne.core.event_bus import EventBus
from airborne.core.input import InputActionEvent, InputConfig, InputManager

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("Instrument Keys Test")

# Setup event bus
event_bus = EventBus()

# Setup input manager
input_config = InputConfig()
input_manager = InputManager(event_bus, input_config)

# Setup TTS
tts = PyTTSXProvider()
tts.initialize({})


# Subscribe to input action events
def handle_input_action(event: InputActionEvent):
    print(f"InputActionEvent received: action={event.action}")

    # Test with sample data
    messages = {
        "read_airspeed": "Airspeed 120 knots",
        "read_altitude": "Altitude 5000 feet",
        "read_heading": "Heading 270 degrees",
        "read_vspeed": "Climbing 500 feet per minute",
        "read_attitude": "Bank 10 degrees left, pitch 5 degrees up",
    }

    message = messages.get(event.action)
    if message:
        print(f"Speaking: {message}")
        tts.speak(message, priority=TTSPriority.NORMAL)
    else:
        print(f"No message for action: {event.action}")


event_bus.subscribe(InputActionEvent, handle_input_action)

print("Instrument Keys Test")
print("=" * 50)
print("Press instrument readout keys:")
print("  S - Airspeed")
print("  L - Altitude")
print("  H - Heading")
print("  W - Vertical Speed")
print("  T - Attitude (bank/pitch)")
print("  ESC - Quit")
print("=" * 50)

# Main loop
clock = pygame.time.Clock()
running = True
while running:
    events = pygame.event.get()
    for event in events:
        if (
            event.type == pygame.QUIT
            or event.type == pygame.KEYDOWN
            and event.key == pygame.K_ESCAPE
        ):
            running = False

    # Process input events
    input_manager.process_events(events)
    input_manager.update(0.016)

    # Fill screen
    screen.fill((0, 0, 0))
    pygame.display.flip()

    clock.tick(60)

# Cleanup
tts.shutdown()
pygame.quit()
print("Test complete")
