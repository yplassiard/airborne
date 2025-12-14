"""Resource path resolution for development and packaged applications.

This module provides utilities to resolve file paths correctly whether running from
source (uv run) or from a packaged application (PyInstaller bundle).

Typical usage:
    from airborne.core.resource_path import get_resource_path, get_plugin_dir

    config_path = get_resource_path("config/logging.yaml")
    plugin_dir = get_plugin_dir()
"""

import os
import sys
from pathlib import Path


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
    return hasattr(sys, "_MEIPASS")


def get_bundle_dir() -> Path | None:
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
        return Path(sys._MEIPASS)
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
        return Path(sys._MEIPASS)
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


def get_architecture() -> str:
    """Get the current CPU architecture.

    Returns:
        Architecture identifier: 'arm64', 'x86_64', 'x86', or 'amd64'.

    Examples:
        >>> get_architecture()  # On Apple Silicon Mac
        'arm64'
        >>> get_architecture()  # On Intel Mac or 64-bit Linux
        'x86_64'
    """
    import platform

    machine = platform.machine().lower()

    if machine in ("arm64", "aarch64"):
        return "arm64"
    elif machine in ("x86_64", "amd64"):
        if sys.platform == "win32":
            return "amd64"
        return "x86_64"
    elif machine in ("i386", "i686", "x86"):
        return "x86"
    else:
        # Default fallback
        if sys.maxsize > 2**32:
            return "x86_64" if sys.platform != "win32" else "amd64"
        return "x86"


def get_platform_lib_dir() -> Path:
    """Get the platform-specific library directory.

    Returns the appropriate library directory based on the current platform:
    - macOS: lib/macos
    - Linux: lib/linux
    - Windows: lib/windows

    Returns:
        Path to the platform-specific library directory.

    Examples:
        >>> str(get_platform_lib_dir())  # On macOS
        '/Users/user/dev/airborne/lib/macos'
    """
    if sys.platform == "darwin":
        platform_dir = "macos"
    elif sys.platform == "win32":
        platform_dir = "windows"
    else:
        platform_dir = "linux"

    return get_resource_path(f"lib/{platform_dir}")


def get_fmod_lib_dir() -> Path:
    """Get the FMOD library directory for current platform and architecture.

    Returns the appropriate FMOD library directory based on the current
    platform and CPU architecture:
    - macOS ARM: res/darwin/arm64
    - macOS Intel: res/darwin/x86_64
    - Linux 32-bit: res/linux/x86
    - Linux 64-bit: res/linux/x86_64
    - Windows 32-bit: res/windows/x86
    - Windows 64-bit: res/windows/amd64
    - Windows ARM: res/windows/arm64

    Returns:
        Path to the FMOD library directory.

    Examples:
        >>> str(get_fmod_lib_dir())  # On Apple Silicon Mac
        '/Users/user/dev/airborne/res/darwin/arm64'
        >>> str(get_fmod_lib_dir())  # On Windows 64-bit
        'C:/dev/airborne/res/windows/amd64'
    """
    arch = get_architecture()

    if sys.platform == "darwin":
        platform_dir = "darwin"
    elif sys.platform == "win32":
        platform_dir = "windows"
    else:
        platform_dir = "linux"

    return get_resource_path(f"res/{platform_dir}/{arch}")


def setup_library_paths() -> None:
    """Set up platform-specific library paths for native libraries.

    This function must be called BEFORE importing any modules that use
    native libraries (like pyfmodex). It preloads required native libraries
    and sets up environment variables.

    On macOS: Preloads libfmod.dylib using ctypes (DYLD_LIBRARY_PATH doesn't
              work at runtime due to SIP)
    On Linux: Sets LD_LIBRARY_PATH
    On Windows: Adds to PATH

    Examples:
        # At the very start of main.py, before other imports:
        from airborne.core.resource_path import setup_library_paths
        setup_library_paths()
    """
    import ctypes

    # Try FMOD lib directory first (res/platform/arch), then fall back to old lib dir
    fmod_lib_dir = get_fmod_lib_dir()
    lib_dir = get_platform_lib_dir()

    # Use FMOD lib dir if it exists, otherwise fall back to platform lib dir
    if fmod_lib_dir.exists():
        active_lib_dir = fmod_lib_dir
    elif lib_dir.exists():
        active_lib_dir = lib_dir
    else:
        return

    lib_dir_str = str(active_lib_dir)

    if sys.platform == "darwin":
        # macOS: Preload libfmod.dylib directly using ctypes
        # DYLD_LIBRARY_PATH changes don't work at runtime due to SIP
        fmod_path = active_lib_dir / "libfmod.dylib"
        if fmod_path.exists():
            try:
                ctypes.CDLL(str(fmod_path))
            except OSError:
                pass  # Will fail later with more context
    elif sys.platform == "win32":
        # Windows: Add to DLL search path and preload fmod.dll
        # Use os.add_dll_directory() (Python 3.8+) for proper DLL discovery
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(lib_dir_str)
        # Also add to PATH as fallback
        current = os.environ.get("PATH", "")
        if lib_dir_str not in current:
            os.environ["PATH"] = f"{lib_dir_str};{current}" if current else lib_dir_str
        # Preload fmod.dll directly (similar to macOS approach)
        fmod_path = active_lib_dir / "fmod.dll"
        if fmod_path.exists():
            try:
                ctypes.CDLL(str(fmod_path))
            except OSError:
                pass  # Will fail later with more context
    else:
        # Linux: LD_LIBRARY_PATH
        current = os.environ.get("LD_LIBRARY_PATH", "")
        if lib_dir_str not in current:
            os.environ["LD_LIBRARY_PATH"] = (
                f"{lib_dir_str}:{current}" if current else lib_dir_str
            )
