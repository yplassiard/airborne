"""Tests for main application module.

Note: Full integration testing of the main application requires
a display and is best done manually. These tests verify the module
can be imported and basic structure is correct.
"""


def test_main_module_exists() -> None:
    """Test that main module can be imported."""
    import airborne.main  # noqa: F401


def test_main_function_exists() -> None:
    """Test that main function exists."""
    from airborne.main import main

    assert callable(main)


def test_airborne_class_exists() -> None:
    """Test that AirBorne class exists."""
    from airborne.main import AirBorne

    assert AirBorne is not None
