# Run tests and generate coverage report
# Usage: .\scripts\run_tests.ps1

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  Run tests and generate coverage report" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

# Set PYTHONPATH so tests can import local package
$env:PYTHONPATH = $PWD

# Run pytest (single-line to avoid continuation/backtick issues)
Write-Host "Running pytest..." -ForegroundColor Yellow
& "$PWD\venv\Scripts\python.exe" -m pytest tests/ --cov=epycon --cov-report=term-missing --cov-report=html --cov-report=xml -v

# Check result
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nTESTS PASSED" -ForegroundColor Green
    Write-Host "`nCoverage reports:" -ForegroundColor Cyan
    Write-Host "  - Terminal: see above output" -ForegroundColor Gray
    Write-Host "  - HTML: htmlcov\index.html" -ForegroundColor Gray
    Write-Host "  - XML: coverage.xml" -ForegroundColor Gray

    # Offer to open HTML report
    Write-Host "`nOpen HTML report? (Y/n): " -ForegroundColor Yellow -NoNewline
    $response = Read-Host
    if ($response -eq '' -or $response -eq 'Y' -or $response -eq 'y') {
        Start-Process htmlcov\index.html
    }
} else {
    Write-Host "`nTESTS FAILED" -ForegroundColor Red
    exit 1
}
