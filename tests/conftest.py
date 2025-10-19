"""Pytest configuration and fixtures for all tests."""

import os

import pygame
import pytest


@pytest.fixture(scope="session", autouse=True)
def initialize_pygame():
    """Initialize pygame for all tests that need it.

    This is a session-scoped fixture that runs automatically
    at the start of the test session.
    """
    # Set SDL to use dummy video driver for headless testing
    os.environ["SDL_VIDEODRIVER"] = "dummy"

    # Initialize pygame modules that tests might use
    pygame.init()

    yield

    # Cleanup after all tests
    pygame.quit()


@pytest.fixture
def pygame_display():
    """Create a pygame display for tests that need it.

    Note: This uses the dummy video driver set in initialize_pygame.
    """
    screen = pygame.display.set_mode((640, 480))
    yield screen
    # Display is automatically cleaned up when pygame.quit() is called
