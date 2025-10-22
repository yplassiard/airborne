"""Resource path resolution for development and packaged applications.

This module provides utilities to resolve file paths correctly whether running from
source (uv run) or from a packaged application (PyInstaller bundle).

Typical usage:
    from airborne.core.resource_path import get_resource_path, get_plugin_dir

    config_path = get_resource_path("config/logging.yaml")
    plugin_dir = get_plugin_dir()
"""

import sys
from pathlib import Path
from typing import Optional


def is_bundled() -> bool:
    """Check if running from a PyInstaller bundle.

    Returns:
        True if running from PyInstaller bundle, False if running from source.

    Examples:
        >>> is_bundled()
        False  # When running with uv run
        >>> is_bundled()
        True   # When running from packaged app
    """
    return hasattr(sys, '_MEIPASS')


def get_bundle_dir() -> Optional[Path]:
    """Get the PyInstaller bundle directory if running from bundle.

    Returns:
        Path to the bundle directory, or None if not bundled.

    Examples:
        >>> get_bundle_dir()
        None  # When running from source
        >>> get_bundle_dir()
        PosixPath('/private/var/.../Contents/Frameworks')  # When bundled
    """
    if is_bundled():
        return Path(getattr(sys, '_MEIPASS'))
    return None


def get_project_root() -> Path:
    """Get the project root directory.

    Returns:
        Path to project root:
        - When running from source: The actual project root directory
        - When bundled: The temporary bundle directory containing resources

    Examples:
        >>> get_project_root()
        PosixPath('/Users/user/dev/airborne')  # From source
        >>> get_project_root()
        PosixPath('/private/var/.../Contents/Frameworks')  # From bundle
    """
    if is_bundled():
        # PyInstaller extracts to sys._MEIPASS
        return Path(getattr(sys, '_MEIPASS'))
    else:
        # When running from source, go up from src/airborne/core to project root
        return Path(__file__).parent.parent.parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to a resource file or directory.

    Works correctly whether running from source or from a packaged application.

    Args:
        relative_path: Relative path from project root (e.g., "config/logging.yaml")

    Returns:
        Absolute path to the resource.

    Examples:
        >>> str(get_resource_path("config/logging.yaml"))
        '/Users/user/dev/airborne/config/logging.yaml'  # From source
        >>> str(get_resource_path("data/airports"))
        '/private/var/.../Contents/Frameworks/data/airports'  # From bundle
    """
    return get_project_root() / relative_path


def get_plugin_dir() -> Path:
    """Get the plugin directory path.

    Returns:
        Path to the plugin directory:
        - When running from source: src/airborne/plugins
        - When bundled: airborne/plugins (bundled as data files)

    Examples:
        >>> str(get_plugin_dir())
        '/Users/user/dev/airborne/src/airborne/plugins'  # From source
        >>> str(get_plugin_dir())
        '/private/var/.../Contents/Frameworks/airborne/plugins'  # From bundle
    """
    if is_bundled():
        # In bundle, plugins are included as data files
        return get_project_root() / "airborne" / "plugins"
    else:
        # When running from source
        return get_project_root() / "src" / "airborne" / "plugins"


def get_config_path(config_file: str) -> Path:
    """Get path to a configuration file.

    Args:
        config_file: Config filename or relative path (e.g., "logging.yaml" or
                    "input_bindings/menu_actions.yaml")

    Returns:
        Absolute path to the config file.

    Examples:
        >>> str(get_config_path("logging.yaml"))
        '/Users/user/dev/airborne/config/logging.yaml'
    """
    return get_resource_path(f"config/{config_file}")


def get_data_path(data_file: str) -> Path:
    """Get path to a data file or directory.

    Args:
        data_file: Data filename or relative path (e.g., "airports/airports.csv")

    Returns:
        Absolute path to the data file or directory.

    Examples:
        >>> str(get_data_path("airports"))
        '/Users/user/dev/airborne/data/airports'
    """
    return get_resource_path(f"data/{data_file}")


def get_asset_path(asset_file: str) -> Path:
    """Get path to an asset file.

    Args:
        asset_file: Asset filename or relative path (e.g., "sounds/aircraft/engine.wav")

    Returns:
        Absolute path to the asset file.

    Examples:
        >>> str(get_asset_path("sounds/aircraft/engine.wav"))
        '/Users/user/dev/airborne/assets/sounds/aircraft/engine.wav'
    """
    return get_resource_path(f"assets/{asset_file}")


def get_lib_path(lib_file: str) -> Path:
    """Get path to a library file (e.g., FMOD, BASS).

    Args:
        lib_file: Library filename or relative path (e.g., "fmod/libfmod.dylib")

    Returns:
        Absolute path to the library file.

    Examples:
        >>> str(get_lib_path("fmod/libfmod.dylib"))
        '/Users/user/dev/airborne/lib/fmod/libfmod.dylib'
        >>> str(get_lib_path("fmod/libfmod.dylib"))
        '/private/var/.../Contents/Frameworks/lib/fmod/libfmod.dylib'  # From bundle
    """
    return get_resource_path(f"lib/{lib_file}")
