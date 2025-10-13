#!/usr/bin/env python3
"""Download OurAirports database files.

This script downloads the latest airport, runway, and frequency data
from the OurAirports project (https://ourairports.com/data/).

Usage:
    uv run python scripts/download_airport_data.py
"""

import sys
from pathlib import Path
from urllib import request
from urllib.error import URLError

# OurAirports data URLs
URLS = [
    "https://davidmegginson.github.io/ourairports-data/airports.csv",
    "https://davidmegginson.github.io/ourairports-data/runways.csv",
    "https://davidmegginson.github.io/ourairports-data/airport-frequencies.csv",
]

# Output directory
DATA_DIR = Path("data/airports")


def download_file(url: str, output_path: Path) -> bool:
    """Download a file from URL to output path.

    Args:
        url: URL to download from.
        output_path: Path to save file to.

    Returns:
        True if successful, False otherwise.
    """
    try:
        print(f"Downloading {url}...")
        with request.urlopen(url) as response:
            content = response.read()

        with open(output_path, "wb") as f:
            f.write(content)

        size_mb = len(content) / (1024 * 1024)
        print(f"✓ Downloaded {output_path.name} ({size_mb:.2f} MB)")
        return True

    except URLError as e:
        print(f"✗ Failed to download {url}: {e}")
        return False
    except OSError as e:
        print(f"✗ Failed to write {output_path}: {e}")
        return False


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success).
    """
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {DATA_DIR.absolute()}\n")

    # Download all files
    success_count = 0
    for url in URLS:
        filename = url.split("/")[-1]
        output_path = DATA_DIR / filename

        if download_file(url, output_path):
            success_count += 1

    # Summary
    print(f"\n{success_count}/{len(URLS)} files downloaded successfully")

    if success_count == len(URLS):
        print("\n✓ All airport data downloaded!")
        return 0
    else:
        print("\n✗ Some downloads failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
