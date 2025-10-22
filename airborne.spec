# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path

# Add the project root to sys.path for imports
project_root = Path(SPECPATH)
sys.path.insert(0, str(project_root / 'src'))

block_cipher = None

# Platform detection for library inclusion
import platform
current_platform = platform.system().lower()

# Determine which audio libraries to include based on platform
binaries = []
if current_platform == 'darwin':
    if os.path.exists('lib/fmod/libfmod.dylib'):
        binaries.append(('lib/fmod/libfmod.dylib', 'lib/fmod'))
    if os.path.exists('lib/macos/libbass.dylib'):
        binaries.append(('lib/macos/libbass.dylib', 'lib'))
elif current_platform == 'linux':
    if os.path.exists('lib/fmod/libfmod.so'):
        binaries.append(('lib/fmod/libfmod.so', 'lib/fmod'))
    if os.path.exists('lib/linux/libbass.so'):
        binaries.append(('lib/linux/libbass.so', 'lib'))
elif current_platform == 'windows':
    if os.path.exists('lib/fmod/fmod.dll'):
        binaries.append(('lib/fmod/fmod.dll', 'lib/fmod'))
    if os.path.exists('lib/windows/bass.dll'):
        binaries.append(('lib/windows/bass.dll', 'lib'))

a = Analysis(
    ['src/airborne/main.py'],
    pathex=[str(project_root), str(project_root / 'src')],
    binaries=binaries,
    datas=[
        # Include ALL config files (YAML configs for checklists, input, speech, radio, etc.)
        ('config', 'config'),

        # Include ALL data files - CRITICAL for game operation!
        # This includes ~3000+ audio files:
        # - data/speech/en/*.wav (TTS-generated instrument readouts, messages)
        # - data/speech/pilot/en/*.mp3 (pre-recorded pilot voice messages)
        # - data/speech/atc/en/*.mp3 (pre-recorded ATC messages)
        # - data/sounds/* (aircraft, airport, environment, engine sounds)
        # - data/audio/* (audio effects configs)
        # - data/airports/* (airport database)
        # - data/navigation/* (nav data)
        # - data/aviation/* (aviation reference)
        ('data', 'data'),

        # Include sound assets
        ('assets/sounds', 'assets/sounds'),

        # Include plugins source files - CRITICAL for dynamic plugin loading!
        # Plugins are loaded dynamically at runtime by PluginLoader
        ('src/airborne/plugins', 'airborne/plugins'),
    ],
    hiddenimports=[
        # Runtime dependencies from pyproject.toml:
        'pygame',           # Main game framework
        'pybass3',          # BASS audio library
        'numpy',            # Math operations
        'yaml',             # Config file parsing (from pyyaml)
        'dateutil',         # Date utilities (from python-dateutil)
        'pyfmodex',         # FMOD audio engine
        'pyttsx3',          # Text-to-speech
        'pydub',            # Audio processing

        # AirBorne core modules
        'airborne',
        'airborne.core',
        'airborne.core.event_bus',
        'airborne.core.messaging',
        'airborne.core.plugin',
        'airborne.core.plugin_loader',
        'airborne.core.registry',
        'airborne.core.input',
        'airborne.core.input_config',
        'airborne.core.input_handler_manager',

        # Plugins
        'airborne.plugins',
        'airborne.plugins.audio',
        'airborne.plugins.core',
        'airborne.plugins.engine',
        'airborne.plugins.radio',
        'airborne.plugins.navigation',

        # Subsystems
        'airborne.audio',
        'airborne.physics',
        'airborne.navigation',
        'airborne.aircraft',
        'airborne.terrain',
        'airborne.ui',
        'airborne.systems',
        'airborne.adapters',
        'airborne.aviation',
        'airborne.airports',
        'airborne.scenario',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build/rthooks/pyi_rth_sdl_env.py'],
    excludes=[
        # Exclude dev/test tools (from pyproject.toml dev dependencies)
        'pytest',
        'pytest_cov',
        'mypy',
        'pylint',
        'ruff',
        'pre_commit',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='airborne',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='airborne',
)

# macOS app bundle
app = BUNDLE(
    coll,
    name='AirBorne.app',
    icon=None,
    bundle_identifier='com.airborne.simulator',
    version='0.1.0',
    info_plist={
        'CFBundleName': 'AirBorne',
        'CFBundleDisplayName': 'AirBorne Flight Simulator',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'CFBundleExecutable': 'airborne',
        'CFBundleIdentifier': 'com.airborne.simulator',
        'LSMinimumSystemVersion': '10.15.0',
        'NSHighResolutionCapable': True,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'NSMicrophoneUsageDescription': 'This app may use text-to-speech for accessibility.',
        'LSUIElement': False,  # Show in dock
        'LSBackgroundOnly': False,  # Not a background-only app
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': True
        },
        # Force app to activate and bring window to front
        'LSEnvironment': {
            'SDL_VIDEO_WINDOW_POS': 'center'
        },
    },
)
