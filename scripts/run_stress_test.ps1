# Batch stress test using testset/
# Usage: .\scripts\run_stress_test.ps1 [-Route text|auto|ocr] [-Chunk]

param(
    [ValidateSet("text", "auto", "ocr")]
    [string]$Route = "text",
    [switch]$Chunk
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = "python"
if ($env:ANY2MD_PYTHON -and (Test-Path $env:ANY2MD_PYTHON)) {
    $Python = $env:ANY2MD_PYTHON
}

$ModelsDir = Join-Path $Root "models"
$ModelArgs = @("--models-dir", $ModelsDir)

$OutBase = Join-Path $Root "testset\output"
New-Item -ItemType Directory -Force -Path $OutBase | Out-Null

$chunkArg = if ($Chunk) { @("--chunk-model", "bge-base-zh-v1.5") } else { @("--chunk-model", "none") }

$files = @()
switch ($Route) {
    "text" {
        $files += Get-ChildItem (Join-Path $Root "testset\office\*.docx")
        $files += Get-ChildItem (Join-Path $Root "testset\office\*.xlsx")
    }
    "auto" {
        $files += Get-ChildItem (Join-Path $Root "testset\digital\*.pdf")
        $files += Get-ChildItem (Join-Path $Root "testset\office\*.pdf")
    }
    "ocr" {
        $files += Get-ChildItem (Join-Path $Root "testset\scan\*_scan.pdf") -ErrorAction SilentlyContinue
    }
}

if (-not $files) {
    Write-Host "No input files for route=$Route" -ForegroundColor Yellow
    if ($Route -eq "ocr") {
        Write-Host "Put scanned PDFs in testset\scan\ (see testset\scan\README.txt)" -ForegroundColor Yellow
    }
    exit 1
}

# One timestamp batch for the whole run
$ts = Get-Date -Format "yyyy-MM-dd_HHmmss"
$BatchRoot = Join-Path $OutBase $ts
foreach ($sub in @("md", "json", "chunks", "assets")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $BatchRoot $sub) | Out-Null
}
Write-Host "Batch: $BatchRoot" -ForegroundColor Cyan

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$ok = 0
$fail = 0

foreach ($f in $files) {
    Write-Host "`n== $($f.Name) ==" -ForegroundColor Cyan
    & $Python engine/run_parser.py -i $f.FullName -o $BatchRoot --route $Route @ModelArgs @chunkArg
    if ($LASTEXITCODE -eq 0) { $ok++ } else { $fail++ }
}

$sw.Stop()
Write-Host "`nDone: $ok ok, $fail failed, $([math]::Round($sw.Elapsed.TotalSeconds,1))s" -ForegroundColor Green
Write-Host "  md/     -> $(Join-Path $BatchRoot 'md')"
Write-Host "  json/   -> $(Join-Path $BatchRoot 'json')"
Write-Host "  chunks/ -> $(Join-Path $BatchRoot 'chunks')"
