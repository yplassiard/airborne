# Kokoro TTS Installation Script for Windows
# Installs Kokoro TTS with English voice models for AirBorne

$ErrorActionPreference = "Stop"

# ============================================
# Helper Functions - MUST be defined first
# ============================================

function Write-Header {
    param($message)
    Write-Host "`n========================================" -ForegroundColor Blue
    Write-Host $message -ForegroundColor Blue
    Write-Host "========================================`n" -ForegroundColor Blue
}

function Write-Success {
    param($message)
    Write-Host "[OK] $message" -ForegroundColor Green
}

function Write-Error-Message {
    param($message)
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

function Write-Warning-Message {
    param($message)
    Write-Host "[WARNING] $message" -ForegroundColor Yellow
}

function Write-Info {
    param($message)
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

# ============================================
# Installation Functions
# ============================================

# Check Python version
function Check-Python {
    Write-Header "Checking Python"
    
    # Try to find Python
    $pythonCmd = $null
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "Using uv's Python environment"
        $pythonCmd = "uv run python"
        $pythonVersion = & uv run python --version 2>&1
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonCmd = "python"
        $pythonVersion = & python --version 2>&1
    } elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        $pythonCmd = "python3"
        $pythonVersion = & python3 --version 2>&1
    } else {
        Write-Error-Message "Python 3 not found. Please install Python 3.10-3.12"
        exit 1
    }
    
    Write-Success "Python found: $pythonVersion"
    return $pythonCmd
}

# Install Python packages
function Install-Packages($pythonCmd) {
    Write-Header "Installing Python Packages"
    
    Write-Info "Installing kokoro-onnx and soundfile..."
    
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "Using uv for package installation..."
        & uv pip install kokoro-onnx soundfile
    } else {
        & $pythonCmd -m pip install --upgrade pip
        & $pythonCmd -m pip install kokoro-onnx soundfile
    }
    
    Write-Success "Python packages installed"
}

# Download ONNX models
function Download-Models {
    Write-Header "Downloading Kokoro ONNX Models"
    
    Write-Info "Downloading models (~337MB total) from GitHub..."
    
    # Create models directory
    $modelsDir = "assets\models"
    if (-not (Test-Path $modelsDir)) {
        New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
    }
    
    # Download ONNX model file (310MB)
    $onnxPath = "$modelsDir\kokoro-v1.0.onnx"
    if (Test-Path $onnxPath) {
        Write-Success "kokoro-v1.0.onnx already exists"
    } else {
        Write-Info "Downloading kokoro-v1.0.onnx (310MB)..."
        $onnxUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
        
        try {
            Invoke-WebRequest -Uri $onnxUrl -OutFile $onnxPath -UseBasicParsing
            Write-Success "kokoro-v1.0.onnx downloaded"
        } catch {
            Write-Error-Message "Failed to download kokoro-v1.0.onnx: $_"
            exit 1
        }
    }
    
    # Download voices binary (27MB)
    $voicesPath = "$modelsDir\voices-v1.0.bin"
    if (Test-Path $voicesPath) {
        Write-Success "voices-v1.0.bin already exists"
    } else {
        Write-Info "Downloading voices-v1.0.bin (27MB)..."
        $voicesUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
        
        try {
            Invoke-WebRequest -Uri $voicesUrl -OutFile $voicesPath -UseBasicParsing
            Write-Success "voices-v1.0.bin downloaded"
        } catch {
            Write-Error-Message "Failed to download voices-v1.0.bin: $_"
            exit 1
        }
    }
}

# Verify installation
function Verify-Installation($pythonCmd) {
    Write-Header "Verifying Installation"
    
    Write-Info "Testing Kokoro TTS..."
    
    if (Test-Path "scripts\test_kokoro.py") {
        try {
            if ($pythonCmd -eq "uv run python") {
                & uv run python scripts\test_kokoro.py
            } else {
                & $pythonCmd scripts\test_kokoro.py
            }
            Write-Success "Kokoro TTS verified successfully!"
        } catch {
            Write-Warning-Message "Verification test failed: $_"
            Write-Info "Models are installed, but there may be a configuration issue"
        }
    } else {
        Write-Warning-Message "test_kokoro.py not found, skipping verification"
    }
}

# List available voices
function List-Voices {
    Write-Header "Available English Voices"
    
    Write-Host "Female Voices (American English):" -ForegroundColor Green
    Write-Host "  - af_alloy"
    Write-Host "  - af_aoede"
    Write-Host "  - af_bella ⭐"
    Write-Host "  - af_heart"
    Write-Host "  - af_jessica"
    Write-Host "  - af_kore"
    Write-Host "  - af_nicole"
    Write-Host "  - af_nova"
    Write-Host "  - af_river"
    Write-Host "  - af_sarah ⭐"
    Write-Host "  - af_sky"
    
    Write-Host "`nMale Voices (American English):" -ForegroundColor Green
    Write-Host "  - am_adam ⭐"
    Write-Host "  - am_echo"
    Write-Host "  - am_eric"
    Write-Host "  - am_fenrir"
    Write-Host "  - am_liam"
    Write-Host "  - am_michael ⭐"
    Write-Host "  - am_onyx"
    Write-Host "  - am_puck"
}

# Print installation summary
function Print-Summary {
    Write-Header "Installation Complete"
    
    Write-Success "Kokoro TTS is ready to use!"
    Write-Host ""
    Write-Info "What was installed:"
    Write-Host "  ✓ kokoro-onnx (Python package with ONNX runtime)"
    Write-Host "  ✓ soundfile (audio I/O)"
    Write-Host "  ✓ ONNX models (310MB) + voice embeddings (27MB)"
    Write-Host "  ✓ 19 English voices available"
    Write-Host ""
    Write-Info "Next Steps:"
    Write-Host "  1. Test installation: python scripts\test_kokoro.py"
    Write-Host "  2. Generate speech: python scripts\generate_speech.py"
    Write-Host "  3. List voices: python scripts\generate_speech.py --list"
    Write-Host ""
    Write-Info "Note: listen_voices_auto.py requires modification for Windows audio playback"
    Write-Host "  Use test_kokoro.py instead for now, or wait for the Windows-compatible version"
    Write-Host ""
}

# Main installation flow
function Main {
    Clear-Host
    
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host "   Kokoro TTS Installation for AirBorne    " -ForegroundColor Blue
    Write-Host "            Windows Version                 " -ForegroundColor Blue
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host ""
    
    $pythonCmd = Check-Python
    Install-Packages $pythonCmd
    Download-Models
    Verify-Installation $pythonCmd
    List-Voices
    Print-Summary
}

# Run main
Main
