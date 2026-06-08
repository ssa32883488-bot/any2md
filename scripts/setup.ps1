# Install any2md engine dependencies (NVIDIA GPU only).
# Usage: .\scripts\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = "python"
if ($env:ANY2MD_PYTHON -and (Test-Path $env:ANY2MD_PYTHON)) {
    $Python = $env:ANY2MD_PYTHON
}

Write-Host "== any2md setup (NVIDIA GPU) ==" -ForegroundColor Cyan
Write-Host "Python: $Python"

$nvidia = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "NVIDIA" }
if (-not $nvidia) {
    Write-Host "WARN: No NVIDIA GPU detected. any2md requires NVIDIA GPU." -ForegroundColor Yellow
}
else {
    Write-Host ("Detected: " + $nvidia[0].Name) -ForegroundColor Green
}

Write-Host "Installing paddlepaddle-gpu 3.2.1 (CUDA 12.6)..." -ForegroundColor Green
& $Python -m pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

Write-Host "Installing paddleocr[doc-parser] (Tsinghua PyPI mirror)..." -ForegroundColor Green
& $Python -m pip install -U "paddleocr[doc-parser]>=3.6.0" -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "Installing fast-path & chunking deps..." -ForegroundColor Green
& $Python -m pip install pymupdf python-docx openpyxl sentence-transformers modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "Installing any2md (editable)..." -ForegroundColor Green
& $Python -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
$env:PADDLE_PDX_MODEL_SOURCE = "bos"
$env:PADDLE_PDX_HUGGING_FACE_ENDPOINT = "https://hf-mirror.com"
$env:HF_ENDPOINT = "https://hf-mirror.com"
$modelsDir = Join-Path $Root "models"
$env:ANY2MD_MODELS_DIR = $modelsDir
Write-Host "Models dir (not C:): $modelsDir" -ForegroundColor Cyan
Write-Host "Model source: bos (Baidu CDN), HF fallback: hf-mirror.com" -ForegroundColor Cyan

Write-Host ""
Write-Host "Done. Verify GPU:" -ForegroundColor Cyan
Write-Host '  python scripts/check_env.py'
Write-Host ('  ' + $Python + ' engine/run_parser.py -i scan.pdf -o ./output')
