"""Volume management with categories and master control.

This module provides centralized volume management with support for
multiple categories (master, music, sfx, etc.) and hierarchical volume
control where category volumes are multiplied by master volume.

Categories:
    - master: Global volume control (affects all sounds)
    - music: Background music volume
    - engine: Aircraft engine sounds
    - environment: Wind, weather, ambient sounds
    - ui: User interface sounds
    - cockpit: Cockpit sounds (instruments, warnings)
    - atc: ATC radio communications
    - pilot: Pilot voice communications
    - cue: Tutorial and guidance cues

Typical usage example:
    from airborne.audio.volume_manager import VolumeManager

    vol_mgr = VolumeManager()
    vol_mgr.set_master_volume(0.8)
    vol_mgr.set_category_volume("music", 0.5)
    final_volume = vol_mgr.get_final_volume("music")  # 0.4 (0.8 * 0.5)
"""

from typing import Literal

# Volume categories
VolumeCategory = Literal[
    "master",
    "music",
    "engine",
    "environment",
    "ui",
    "cockpit",
    "atc",
    "pilot",
    "cue",
]


class VolumeManager:
    """Manages volume levels for different audio categories.

    The VolumeManager provides hierarchical volume control where each
    category has its own volume that is multiplied by the master volume
    to get the final playback volume.

    Examples:
        >>> vol_mgr = VolumeManager()
        >>> vol_mgr.set_master_volume(0.8)
        >>> vol_mgr.set_category_volume("music", 0.5)
        >>> vol_mgr.get_final_volume("music")
        0.4
    """

    def __init__(self) -> None:
        """Initialize the volume manager with default volumes."""
        self._master_volume: float = 1.0
        self._category_volumes: dict[str, float] = {
            "music": 1.0,
            "engine": 1.0,
            "environment": 1.0,
            "ui": 1.0,
            "cockpit": 1.0,
            "atc": 1.0,
            "pilot": 1.0,
            "cue": 1.0,
        }

    def set_master_volume(self, volume: float) -> None:
        """Set the master volume level.

        Args:
            volume: Volume level from 0.0 (silent) to 1.0 (full).

        Examples:
            >>> vol_mgr.set_master_volume(0.8)
        """
        self._master_volume = max(0.0, min(1.0, volume))

    def get_master_volume(self) -> float:
        """Get the current master volume level.

        Returns:
            Master volume from 0.0 to 1.0.

        Examples:
            >>> vol_mgr.get_master_volume()
            1.0
        """
        return self._master_volume

    def set_category_volume(self, category: VolumeCategory, volume: float) -> None:
        """Set volume for a specific category.

        Args:
            category: Category name (e.g., "music", "engine").
            volume: Volume level from 0.0 (silent) to 1.0 (full).

        Examples:
            >>> vol_mgr.set_category_volume("music", 0.5)
        """
        self._category_volumes[category] = max(0.0, min(1.0, volume))

    def get_category_volume(self, category: VolumeCategory) -> float:
        """Get volume for a specific category.

        Args:
            category: Category name to query.

        Returns:
            Category volume from 0.0 to 1.0, or 1.0 if category unknown.

        Examples:
            >>> vol_mgr.get_category_volume("music")
            1.0
        """
        return self._category_volumes.get(category, 1.0)

    def get_final_volume(self, category: VolumeCategory) -> float:
        """Get final volume after applying master volume.

        The final volume is the category volume multiplied by the master
        volume, providing hierarchical control.

        Args:
            category: Category name to calculate volume for.

        Returns:
            Final volume from 0.0 to 1.0.

        Examples:
            >>> vol_mgr.set_master_volume(0.8)
            >>> vol_mgr.set_category_volume("music", 0.5)
            >>> vol_mgr.get_final_volume("music")
            0.4
        """
        category_vol = self.get_category_volume(category)
        return self._master_volume * category_vol
