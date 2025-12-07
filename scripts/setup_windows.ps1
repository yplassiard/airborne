# Windows Setup Script for AirBorne
# Complete environment setup for Windows 10/11

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

function Write-Info {
    param($message)
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

# ============================================
# Setup Functions
# ============================================

# Check virtual environment
function Check-VirtualEnv {
    Write-Header "Checking Virtual Environment"
    
    if (Test-Path ".venv") {
        Write-Success "Virtual environment exists"
        
        # Check if activated
        if ($env:VIRTUAL_ENV) {
            Write-Success "Virtual environment is activated"
        } else {
            Write-Info "Activating virtual environment..."
            & .\.venv\Scripts\Activate.ps1
            Write-Success "Virtual environment activated"
        }
    } else {
        Write-Info "Creating virtual environment..."
        python -m venv .venv
        Write-Success "Virtual environment created"
        
        Write-Info "Activating virtual environment..."
        & .\.venv\Scripts\Activate.ps1
        Write-Success "Virtual environment activated"
    }
}

# Install dependencies
function Install-Dependencies {
    Write-Header "Installing Dependencies"
    
    Write-Info "Installing from pyproject.toml..."
    
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "Using uv for installation (faster)..."
        & uv sync
    } else {
        Write-Info "Using pip for installation..."
        python -m pip install --upgrade pip
        python -m pip install -e .
    }
    
    Write-Success "Dependencies installed"
}

# Verify configuration files
function Verify-Config {
    Write-Header "Verifying Configuration"
    
    $configFiles = @(
        "config\speech.yaml",
        "config\logging.yaml",
        "config\atc_en.yaml"
    )
    
    $allExist = $true
    foreach ($file in $configFiles) {
        if (Test-Path $file) {
            Write-Success "$file exists"
        } else {
            Write-Error-Message "$file is missing!"
            $allExist = $false
        }
    }
    
    if (-not $allExist) {
        Write-Info "Some configuration files are missing."
        Write-Info "speech.yaml should have been created. Check the config directory."
    } else {
        Write-Success "All critical configuration files exist"
    }
}

# Check FMOD libraries
function Check-FMOD {
    Write-Header "Checking FMOD Libraries"
    
    $fmodPath = "lib\windows\x64\fmod.dll"
    
    if (Test-Path $fmodPath) {
        Write-Success "FMOD library found: $fmodPath"
    } else {
        Write-Info "FMOD library not found at: $fmodPath"
        Write-Info "You may need to download FMOD Engine 2.2.22 manually"
        Write-Info "Visit: https://www.fmod.com/download"
        Write-Info "Extract fmod.dll and fmodL.dll to: lib\windows\x64\"
    }
}

# Test basic functionality
function Test-Basic {
    Write-Header "Testing Basic Functionality"
    
    Write-Info "Testing Python imports..."
    
    $testScript = @"
import sys
try:
    import pygame
    print('✓ pygame imported')
except ImportError as e:
    print(f'✗ pygame import failed: {e}')
    
try:
    import yaml
    print('✓ yaml imported')
except ImportError as e:
    print(f'✗ yaml import failed: {e}')

try:
    import numpy
    print('✓ numpy imported')
except ImportError as e:
    print(f'✗ numpy import failed: {e}')

print('Basic imports test complete!')
"@
    
    $testScript | python
    Write-Success "Import test completed"
}

# Print summary
function Print-Summary {
    Write-Header "Setup Complete"
    
    Write-Success "AirBorne is configured for Windows!"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  1. Install Kokoro TTS (optional but recommended):"
    Write-Host "     .\scripts\install_kokoro.ps1"
    Write-Host ""
    Write-Host "  2. Test TTS configuration:"
    Write-Host "     python scripts\test_kokoro.py"
    Write-Host ""
    Write-Host "  3. Generate speech files:"
    Write-Host "     python scripts\generate_speech.py"
    Write-Host ""
    Write-Host "  4. Run a demo:"
    Write-Host "     python scripts\demo_autopilot.py"
    Write-Host ""
    Write-Info "For more information, see docs\WINDOWS_SETUP.md"
    Write-Host ""
}

# Main setup flow
function Main {
    Clear-Host
    
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host "     AirBorne Windows Setup Script         " -ForegroundColor Blue
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host ""
    
    Check-VirtualEnv
    Install-Dependencies
    Verify-Config
    Check-FMOD
    Test-Basic
    Print-Summary
}

# Run main
Main
