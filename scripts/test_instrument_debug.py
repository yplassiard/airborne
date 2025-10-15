#!/usr/bin/env python3
"""Debug script to test instrument key speech - simulates pressing 'S' for airspeed."""

import sys

import pygame

from airborne.core.event_bus import EventBus
from airborne.core.input import InputConfig, InputManager
from airborne.core.logging_system import get_logger, initialize_logging

# Initialize logging to see all debug messages
initialize_logging(log_level="INFO")
logger = get_logger(__name__)

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("Instrument Debug Test")

# Setup event bus and input manager
event_bus = EventBus()
input_config = InputConfig()
input_manager = InputManager(event_bus, input_config)

logger.info("=" * 60)
logger.info("Instrument Debug Test - Press 'S' for airspeed readout")
logger.info("=" * 60)

# Simulate pressing the 'S' key for 2 seconds
clock = pygame.time.Clock()
frame_count = 0
max_frames = 120  # 2 seconds at 60 FPS

while frame_count < max_frames:
    # Create fake keydown event for 'S' key on first frame
    events = []
    if frame_count == 0:
        logger.info(">>> Simulating 'S' key press (READ_AIRSPEED)")
        keydown_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s)
        events.append(keydown_event)
    elif frame_count == 10:
        logger.info(">>> Simulating 'S' key release")
        keyup_event = pygame.event.Event(pygame.KEYUP, key=pygame.K_s)
        events.append(keyup_event)

    # Add quit events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            frame_count = max_frames
        events.append(event)

    # Process input
    input_manager.process_events(events)
    input_manager.update(1.0 / 60.0)

    # Render
    screen.fill((0, 0, 0))
    pygame.display.flip()

    frame_count += 1
    clock.tick(60)

logger.info("=" * 60)
logger.info("Test complete")
logger.info("=" * 60)

pygame.quit()
sys.exit(0)
