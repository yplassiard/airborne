#!/bin/bash

# Build script for AirBorne - Creates macOS app, Linux tarball, and Windows installer
# Usage: ./scripts/build_app.sh [macos|linux|windows|all]

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

VERSION="0.1.0"
APP_NAME="AirBorne"
BUNDLE_ID="com.airborne.simulator"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Platform detection
PLATFORM="$(uname -s)"
case "$PLATFORM" in
    Darwin*) CURRENT_OS="macos";;
    Linux*)  CURRENT_OS="linux";;
    MINGW*|MSYS*|CYGWIN*) CURRENT_OS="windows";;
    *) CURRENT_OS="unknown";;
esac

# Determine what to build
BUILD_TARGET="${1:-$CURRENT_OS}"

# Functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅${NC} $1"
}

log_error() {
    echo -e "${RED}❌${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

clean_build() {
    log_info "Cleaning previous builds..."
    rm -rf build/ dist/
    log_success "Clean complete"
}

check_dependencies() {
    log_info "Checking dependencies..."

    # Check for uv
    if ! command -v uv &> /dev/null; then
        log_error "uv is not installed. Install it from https://docs.astral.sh/uv/"
        exit 1
    fi

    # Check for PyInstaller
    if ! uv run pyinstaller --version &> /dev/null; then
        log_warning "PyInstaller not found, installing..."
        uv add --dev pyinstaller
    fi

    log_success "Dependencies OK"
}

generate_spec_file() {
    log_info "Generating PyInstaller spec file..."

    # Create runtime hook for SDL environment variables
    mkdir -p build/rthooks
    cat > build/rthooks/pyi_rth_sdl_env.py << 'RTHOOK_EOF'
# PyInstaller runtime hook to set SDL environment variables for proper window handling
import os
os.environ['SDL_VIDEO_WINDOW_POS'] = 'center'
os.environ['SDL_VIDEO_CENTERED'] = '1'
RTHOOK_EOF

    cat > airborne.spec << 'SPEC_EOF'
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
SPEC_EOF

    log_success "Spec file generated"
}

build_macos() {
    if [ "$CURRENT_OS" != "macos" ]; then
        log_warning "Skipping macOS build (not on macOS)"
        return
    fi

    log_info "Building macOS app..."

    uv run pyinstaller airborne.spec

    if [ -d "dist/AirBorne.app" ]; then
        log_success "macOS app built successfully!"
        log_info "Location: $PROJECT_ROOT/dist/AirBorne.app"
        log_info "Size: $(du -sh dist/AirBorne.app | cut -f1)"
        echo ""
        log_info "To run: open 'dist/AirBorne.app'"
        log_info "Or double-click the app in Finder"
        echo ""
    else
        log_error "macOS build failed!"
        exit 1
    fi
}

build_linux() {
    log_info "Building Linux tarball..."

    # Build with PyInstaller (creates dist/airborne directory)
    uv run pyinstaller airborne.spec --onedir

    if [ -d "dist/airborne" ]; then
        # Create tarball
        cd dist
        tar -czf "airborne-${VERSION}-linux-x86_64.tar.gz" airborne
        cd ..

        log_success "Linux tarball built successfully!"
        log_info "Location: $PROJECT_ROOT/dist/airborne-${VERSION}-linux-x86_64.tar.gz"
        log_info "Size: $(du -sh dist/airborne-${VERSION}-linux-x86_64.tar.gz | cut -f1)"
        echo ""
        log_info "To extract: tar -xzf airborne-${VERSION}-linux-x86_64.tar.gz"
        log_info "To run: ./airborne/airborne"
        echo ""
    else
        log_error "Linux build failed!"
        exit 1
    fi
}

build_windows() {
    log_info "Building Windows installer..."

    # Check for makensis (NSIS compiler)
    if ! command -v makensis &> /dev/null; then
        log_error "makensis (NSIS) not found!"
        log_info "Install NSIS from https://nsis.sourceforge.io/"
        if [ "$CURRENT_OS" = "macos" ]; then
            log_info "Or use: brew install makensis"
        fi
        exit 1
    fi

    # Build with PyInstaller
    uv run pyinstaller airborne.spec --onedir

    if [ -d "dist/airborne" ]; then
        # Generate NSIS script
        log_info "Generating NSIS installer script..."
        cat > dist/airborne-installer.nsi << 'NSIS_EOF'
; AirBorne NSIS Installer Script

!define APPNAME "AirBorne"
!define COMPANYNAME "AirBorne Team"
!define DESCRIPTION "Blind-Accessible Flight Simulator"
!define VERSIONMAJOR 0
!define VERSIONMINOR 1
!define VERSIONBUILD 0
!define HELPURL "https://github.com/yourusername/airborne"
!define UPDATEURL "https://github.com/yourusername/airborne"
!define ABOUTURL "https://github.com/yourusername/airborne"
!define INSTALLSIZE 262144  # ~256 MB estimate

RequestExecutionLevel admin
InstallDir "$PROGRAMFILES64\${APPNAME}"
Name "${APPNAME}"
Icon "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
OutFile "AirBorne-Setup-${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}.exe"

!include MUI2.nsh
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "../LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath $INSTDIR

    # Install files
    File /r "airborne\*.*"

    # Create shortcuts
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\airborne.exe"
    CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\airborne.exe"

    # Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    # Registry information for add/remove programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME} - ${DESCRIPTION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$\"$INSTDIR$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
SectionEnd

Section "Uninstall"
    # Remove shortcuts
    Delete "$DESKTOP\${APPNAME}.lnk"
    Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
    RMDir "$SMPROGRAMS\${APPNAME}"

    # Remove files
    RMDir /r "$INSTDIR"

    # Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd
NSIS_EOF

        # Create LICENSE file if it doesn't exist
        if [ ! -f "LICENSE" ]; then
            echo "MIT License - See https://github.com/yourusername/airborne" > dist/LICENSE
        else
            cp LICENSE dist/
        fi

        # Build installer
        cd dist
        makensis airborne-installer.nsi
        cd ..

        log_success "Windows installer built successfully!"
        log_info "Location: $PROJECT_ROOT/dist/AirBorne-Setup-0.1.0.exe"
        log_info "Size: $(du -sh dist/AirBorne-Setup-0.1.0.exe | cut -f1)"
        echo ""
    else
        log_error "Windows build failed!"
        exit 1
    fi
}

# Main build process
main() {
    echo ""
    log_info "═══════════════════════════════════════════════════════"
    log_info "  AirBorne Flight Simulator - Build Script"
    log_info "  Version: $VERSION"
    log_info "  Platform: $CURRENT_OS"
    log_info "═══════════════════════════════════════════════════════"
    echo ""

    check_dependencies
    clean_build
    generate_spec_file

    case "$BUILD_TARGET" in
        macos)
            build_macos
            ;;
        linux)
            build_linux
            ;;
        windows)
            build_windows
            ;;
        all)
            build_macos
            build_linux
            build_windows
            ;;
        *)
            log_error "Unknown build target: $BUILD_TARGET"
            echo "Usage: $0 [macos|linux|windows|all]"
            exit 1
            ;;
    esac

    echo ""
    log_success "═══════════════════════════════════════════════════════"
    log_success "  Build Complete!"
    log_success "═══════════════════════════════════════════════════════"
    echo ""
}

main
