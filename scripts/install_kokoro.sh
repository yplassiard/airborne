#!/bin/bash
#
# Kokoro TTS Installation Script for macOS
# Installs Kokoro TTS with English voice models
#
# This script:
# 1. Checks system compatibility
# 2. Installs espeak-ng via Homebrew
# 3. Installs Python packages (kokoro, soundfile)
# 4. Downloads English voice models
# 5. Verifies installation

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if running on macOS
check_platform() {
    print_header "Checking Platform"

    if [[ "$OSTYPE" != "darwin"* ]]; then
        print_error "This script is designed for macOS only."
        print_info "For other platforms, install manually:"
        echo "  - Linux: apt-get install espeak-ng"
        echo "  - Windows: Download espeak-ng from GitHub"
        echo "  - All platforms: pip install kokoro>=0.9.4 soundfile"
        exit 1
    fi

    print_success "Running on macOS"
}

# Check Python version
check_python() {
    print_header "Checking Python"

    # Try uv's Python first, then fall back to system Python
    if command -v uv &> /dev/null; then
        print_info "Using uv's Python environment"
        PYTHON_CMD="uv run python"
        PYTHON_VERSION=$(uv run python --version | cut -d' ' -f2)
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    else
        print_error "Python 3 not found. Please install Python 3.10-3.12"
        exit 1
    fi

    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        print_error "Python 3.10+ required. Found: $PYTHON_VERSION"
        exit 1
    fi

    print_success "Python $PYTHON_VERSION found"
}

# Check/install Homebrew
check_homebrew() {
    print_header "Checking Homebrew"

    if ! command -v brew &> /dev/null; then
        print_warning "Homebrew not found"
        print_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        print_success "Homebrew installed"
    else
        print_success "Homebrew found"
    fi
}

# Install espeak-ng
install_espeak() {
    print_header "Installing espeak-ng"

    if command -v espeak-ng &> /dev/null; then
        print_success "espeak-ng already installed"
    else
        print_info "Installing espeak-ng via Homebrew..."
        brew install espeak-ng
        print_success "espeak-ng installed"
    fi

    # Verify installation
    if command -v espeak-ng &> /dev/null; then
        ESPEAK_VERSION=$(espeak-ng --version | head -n1)
        print_success "espeak-ng verified: $ESPEAK_VERSION"
    else
        print_error "espeak-ng installation failed"
        exit 1
    fi
}

# Install Python packages
install_python_packages() {
    print_header "Installing Python Packages"

    print_info "Installing kokoro-onnx and soundfile..."
    print_warning "Note: Installing globally (not in uv project, as per requirements)"

    # Install packages using uv if available, otherwise use pip
    if command -v uv &> /dev/null; then
        print_info "Using uv for package installation..."
        uv pip install kokoro-onnx soundfile
    else
        $PYTHON_CMD -m pip install --upgrade pip
        $PYTHON_CMD -m pip install kokoro-onnx soundfile
    fi

    print_success "Python packages installed"
}

# Download ONNX models
download_models() {
    print_header "Downloading Kokoro ONNX Models"

    print_info "Downloading models (~337MB total) from GitHub..."

    # Create models directory
    mkdir -p assets/models

    # Download ONNX model file (310MB)
    if [ -f "assets/models/kokoro-v1.0.onnx" ]; then
        print_success "kokoro-v1.0.onnx already exists"
    else
        print_info "Downloading kokoro-v1.0.onnx (310MB)..."
        if curl -L -o assets/models/kokoro-v1.0.onnx \
            https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx; then
            print_success "kokoro-v1.0.onnx downloaded"
        else
            print_error "Failed to download kokoro-v1.0.onnx"
            exit 1
        fi
    fi

    # Download voices binary (27MB)
    if [ -f "assets/models/voices-v1.0.bin" ]; then
        print_success "voices-v1.0.bin already exists"
    else
        print_info "Downloading voices-v1.0.bin (27MB)..."
        if curl -L -o assets/models/voices-v1.0.bin \
            https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin; then
            print_success "voices-v1.0.bin downloaded"
        else
            print_error "Failed to download voices-v1.0.bin"
            exit 1
        fi
    fi

    # Verify models work
    print_info "Verifying installation..."
    if $PYTHON_CMD scripts/test_kokoro.py; then
        print_success "Models verified successfully"
    else
        print_error "Model verification failed"
        exit 1
    fi
}

# List available voices
list_voices() {
    print_header "Available English Voices"

    echo -e "${GREEN}Female Voices (American English):${NC}"
    echo "  - af_alloy"
    echo "  - af_aoede"
    echo "  - af_bella"
    echo "  - af_heart"
    echo "  - af_jessica"
    echo "  - af_kore"
    echo "  - af_nicole"
    echo "  - af_nova"
    echo "  - af_river"
    echo "  - af_sarah"
    echo "  - af_sky"

    echo -e "\n${GREEN}Male Voices (American English):${NC}"
    echo "  - am_adam"
    echo "  - am_echo"
    echo "  - am_eric"
    echo "  - am_fenrir"
    echo "  - am_liam"
    echo "  - am_michael"
    echo "  - am_onyx"
    echo "  - am_puck"

    echo -e "\n${BLUE}Usage Example:${NC}"
    echo "  from kokoro import KPipeline"
    echo "  pipeline = KPipeline(lang_code='a')  # 'a' = American, 'b' = British"
    echo "  audio = pipeline('Hello world', voice='af_bella')"
}

# Print installation summary
print_summary() {
    print_header "Installation Complete"

    print_success "Kokoro TTS is ready to use!"
    echo ""
    print_info "What was installed:"
    echo "  ✓ espeak-ng (speech synthesizer)"
    echo "  ✓ kokoro-onnx (Python package with ONNX runtime)"
    echo "  ✓ soundfile (audio I/O)"
    echo "  ✓ ONNX models (310MB) + voice embeddings (27MB)"
    echo "  ✓ 19 English voices available"
    echo ""
    print_info "Performance:"
    echo "  • 3-8x faster than realtime on your M4 Mac"
    echo "  • First generation: ~3x realtime"
    echo "  • Subsequent generations: ~8x realtime"
    echo ""
    print_info "Next Steps:"
    echo "  1. Listen to all voices: uv run python scripts/listen_voices_auto.py"
    echo "  2. Update scripts/generate_speech.py to use Kokoro backend"
    echo "  3. Configure config/speech.yaml with preferred voices"
    echo ""
    print_info "Available Scripts:"
    echo "  • scripts/test_kokoro.py           - Quick installation test"
    echo "  • scripts/listen_voices_auto.py    - Auto-play all 19 voices"
    echo "  • scripts/listen_voices.py         - Interactive voice listener"
    echo "  • scripts/sample_voices.py         - Generate voice samples to files"
    echo ""
    print_info "Usage Example:"
    echo '  from kokoro_onnx import Kokoro'
    echo '  kokoro = Kokoro("assets/models/kokoro-v1.0.onnx", "assets/models/voices-v1.0.bin")'
    echo '  samples, rate = kokoro.create("Hello world", voice="af_bella", lang="en-us")'
    echo ""
}

# Main installation flow
main() {
    clear
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════╗"
    echo "║   Kokoro TTS Installation for AirBorne   ║"
    echo "╚═══════════════════════════════════════════╝"
    echo -e "${NC}"

    check_platform
    check_python
    check_homebrew
    install_espeak
    install_python_packages
    download_models
    list_voices
    print_summary
}

# Run main
main
