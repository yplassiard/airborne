#!/usr/bin/env python3
"""Test script to diagnose TTS cache service startup issues."""

import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Testing TTS cache service imports and initialization...")
print("=" * 60)

# Test 1: Import dependencies
print("\n1. Testing websockets import...")
try:
    import websockets
    print(f"   ✓ websockets {websockets.__version__}")
except ImportError as e:
    print(f"   ✗ ERROR: {e}")
    sys.exit(1)

# Test 2: Import service module
print("\n2. Testing service module import...")
try:
    from airborne.tts_cache_service import service
    print("   ✓ Service module imported")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 3: Try to create service instance
print("\n3. Testing service instance creation...")
try:
    config = {
        "server": {"host": "127.0.0.1", "port": 51127},
        "cache": {"base_dir": None},
        "generation": {},
    }
    svc = service.TTSCacheService(config)
    print("   ✓ Service instance created")
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 4: Check pyttsx3
print("\n4. Testing pyttsx3 (optional)...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    print("   ✓ pyttsx3 available")
    engine.stop()
except Exception as e:
    print(f"   ⚠ pyttsx3 not working: {e}")

print("\n" + "=" * 60)
print("All basic tests passed!")
print("\nThe service should be able to start.")
print("If it still fails, the issue is in the async event loop or server setup.")
