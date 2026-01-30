# PowerShell cleanup script for epycon project
# Run this script to clean temporary files while preserving valuable files

Write-Host "Cleaning temporary files..."

# Clean Python cache
Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Cleaned __pycache__ directories"

# Clean pytest cache
Remove-Item -Path ".pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Cleaned pytest cache"

# Clean coverage data
Remove-Item -Path ".coverage" -ErrorAction SilentlyContinue
Write-Host "Cleaned coverage data"

# Clean temporary log files
Remove-Item -Path "flask_debug.txt", "flask_route_called.txt" -ErrorAction SilentlyContinue
Write-Host "Cleaned temporary log files"

# Clean other temp files
Get-ChildItem -Path . -Recurse -Include "*.tmp", "*.bak", "*.swp", "*~" | Remove-Item -Force -ErrorAction SilentlyContinue
Write-Host "Cleaned other temporary files"

Write-Host "Cleanup completed!"