"""Platform-specific BASS library loader.

This module handles loading the BASS and BASS_FX libraries from the bundled
lib directory based on the current platform.
"""

import os
import sys
from pathlib import Path

from airborne.core.logging_system import get_logger

logger = get_logger(__name__)


def get_bass_library_path() -> tuple[Path, Path]:
    """Get the platform-specific paths to BASS and BASS_FX libraries.

    Returns:
        Tuple of (bass_path, bass_fx_path)

    Raises:
        FileNotFoundError: If libraries are not found for current platform
    """
    # Get project root (3 levels up from this file)
    project_root = Path(__file__).parent.parent.parent.parent.parent

    # Determine platform-specific subdirectory and library names
    if sys.platform == "win32":
        lib_dir = project_root / "lib" / "windows"
        bass_lib = "bass.dll"
        bass_fx_lib = "bass_fx.dll"
    elif sys.platform == "darwin":
        lib_dir = project_root / "lib" / "macos"
        bass_lib = "libbass.dylib"
        bass_fx_lib = "libbass_fx.dylib"
    elif sys.platform.startswith("linux"):
        lib_dir = project_root / "lib" / "linux"
        bass_lib = "libbass.so"
        bass_fx_lib = "libbass_fx.so"
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")

    bass_path = lib_dir / bass_lib
    bass_fx_path = lib_dir / bass_fx_lib

    # Check if libraries exist
    if not bass_path.exists():
        raise FileNotFoundError(
            f"BASS library not found: {bass_path}\n"
            f"Expected location: {lib_dir}\n"
            f"Please ensure the BASS library is present for your platform."
        )

    if not bass_fx_path.exists():
        logger.warning(f"BASS_FX library not found: {bass_fx_path} (optional)")

    logger.info(f"BASS library path: {bass_path}")
    logger.info(f"BASS_FX library path: {bass_fx_path}")

    return bass_path, bass_fx_path


def load_bass_library() -> tuple[str, str]:
    """Load platform-specific BASS libraries and return their paths as strings.

    This function should be called before importing pybass3 to ensure the
    libraries are loaded from the correct location.

    Returns:
        Tuple of (bass_lib_path_str, bass_fx_lib_path_str)

    Raises:
        FileNotFoundError: If libraries not found
        OSError: If platform not supported
    """
    bass_path, bass_fx_path = get_bass_library_path()

    # Add library directory to system path so pybass3 can find it
    lib_dir = bass_path.parent
    if str(lib_dir) not in os.environ.get("PATH", ""):
        if sys.platform == "win32":
            os.environ["PATH"] = str(lib_dir) + os.pathsep + os.environ.get("PATH", "")
        else:
            # For Unix-like systems, add to LD_LIBRARY_PATH (Linux) or DYLD_LIBRARY_PATH (macOS)
            if sys.platform == "darwin":
                os.environ["DYLD_LIBRARY_PATH"] = (
                    str(lib_dir) + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", "")
                )
            else:
                os.environ["LD_LIBRARY_PATH"] = (
                    str(lib_dir) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
                )

    return str(bass_path), str(bass_fx_path)
