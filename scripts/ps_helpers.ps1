# PowerShell Helper Functions for Epycon
# Usage: . .\scripts\ps_helpers.ps1

function Invoke-PyScript {
    param([Parameter(Mandatory = $true)][string]$ScriptPath)
    if (Test-Path $ScriptPath) {
        python $ScriptPath
    }
    else {
        Write-Host "File not found: $ScriptPath" -ForegroundColor Red
    }
}

function Test-H5Files {
    param([string]$Path = "examples\data\out")
    if (Test-Path "scripts\inspect_h5_attrs.py") {
        python scripts\inspect_h5_attrs.py $Path
    }
    else {
        Write-Host "scripts\inspect_h5_attrs.py not found" -ForegroundColor Red
    }
}

function Test-Master {
    if (Test-Path "scripts\verify_master.py") {
        python scripts\verify_master.py
    }
    else {
        Write-Host "scripts\verify_master.py not found" -ForegroundColor Red
    }
}

function Get-H5Attributes {
    param([Parameter(Mandatory = $true)][string]$FilePath)
    if (Test-Path "scripts\inspect_h5_attrs.py") {
        python scripts\inspect_h5_attrs.py $FilePath
    }
    else {
        Write-Host "scripts\inspect_h5_attrs.py not found" -ForegroundColor Red
    }
}

function Start-EpyconGUI {
    python app_gui.py
}

Write-Host "Loaded Epycon helper functions:" -ForegroundColor Green
Write-Host "  - Invoke-PyScript <path>  Run Python script" -ForegroundColor Cyan
Write-Host "  - Test-H5Files [path]     Check H5 files in directory" -ForegroundColor Cyan
Write-Host "  - Get-H5Attributes <file> Inspect single H5 file" -ForegroundColor Cyan
Write-Host "  - Test-Master              Verify MASTER info" -ForegroundColor Cyan
Write-Host "  - Start-EpyconGUI          Start GUI" -ForegroundColor Cyan
