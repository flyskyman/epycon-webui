# 运行测试并生成覆盖率报告的脚本
# 使用方法: .\run_tests.ps1

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  运行测试 + 覆盖率报告" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

# 设置 PYTHONPATH
$env:PYTHONPATH = $PWD

# 运行测试
Write-Host "运行 pytest..." -ForegroundColor Yellow
& "$PWD\venv\Scripts\python.exe" -m pytest tests/ `
    --cov=epycon `
    --cov-report=term-missing `
    --cov-report=html `
    --cov-report=xml `
    -v

# 检查结果
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ 测试通过！" -ForegroundColor Green
    Write-Host "`n查看覆盖率报告:" -ForegroundColor Cyan
    Write-Host "  • 终端: 见上方输出" -ForegroundColor Gray
    Write-Host "  • HTML: htmlcov\index.html" -ForegroundColor Gray
    Write-Host "  • XML: coverage.xml (用于 CI)" -ForegroundColor Gray
    
    # 询问是否打开 HTML 报告
    Write-Host "`n打开 HTML 报告? (Y/n): " -ForegroundColor Yellow -NoNewline
    $response = Read-Host
    if ($response -eq '' -or $response -eq 'Y' -or $response -eq 'y') {
        Start-Process htmlcov\index.html
    }
} else {
    Write-Host "`n❌ 测试失败！" -ForegroundColor Red
    exit 1
}
