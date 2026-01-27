<#
Cleanup repository temporary artifacts (safe):
- removes: htmlcov, coverage.xml, .coverage, .pytest_cache, __pycache__ directories
- does NOT remove: `venv`, `.venv`, or any virtualenvs

Usage: Run from repo root in PowerShell:
    .\scripts\clean_repo.ps1
#>

Write-Host "Running safe repo cleanup..." -ForegroundColor Cyan

# remove htmlcov
if (Test-Path 'htmlcov') { Remove-Item -LiteralPath 'htmlcov' -Recurse -Force; Write-Host 'Removed htmlcov' }

# remove coverage xml and data file
if (Test-Path 'coverage.xml') { Remove-Item -LiteralPath 'coverage.xml' -Force; Write-Host 'Removed coverage.xml' }
if (Test-Path '.coverage') { Remove-Item -LiteralPath '.coverage' -Force; Write-Host 'Removed .coverage' }

# remove pytest cache
if (Test-Path '.pytest_cache') { Remove-Item -LiteralPath '.pytest_cache' -Recurse -Force; Write-Host 'Removed .pytest_cache' }

# remove __pycache__ directories inside repository (but skip venv paths)
Get-ChildItem -Recurse -Directory -Force | Where-Object { $_.Name -eq '__pycache__' -and $_.FullName -notlike '*\\venv\\*' -and $_.FullName -notlike '*\\.venv\\*' } | ForEach-Object { Remove-Item -Recurse -Force $_.FullName; Write-Host ("Removed: " + $_.FullName) }

Write-Host "Cleanup complete." -ForegroundColor Green
