# Build script for fast_math_rs Rust module
# Run this script to build and install the Rust acceleration module

Write-Host "Building fast_math_rs Rust acceleration module..." -ForegroundColor Cyan

# Check if maturin is installed
$maturinCheck = pip show maturin 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing maturin..." -ForegroundColor Yellow
    pip install maturin
}

# Navigate to the Rust module directory
Push-Location "$PSScriptRoot\fast_math_rs"

try {
    # Build in release mode
    Write-Host "Running maturin develop --release..." -ForegroundColor Green
    maturin develop --release
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build successful! fast_math_rs is now available." -ForegroundColor Green
        Write-Host "Test with: python -c `"import fast_math_rs; print(fast_math_rs.__version__)`"" -ForegroundColor Cyan
    } else {
        Write-Host "Build failed. Make sure Rust is installed: https://rustup.rs/" -ForegroundColor Red
    }
} finally {
    Pop-Location
}
