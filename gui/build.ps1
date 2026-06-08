# Build any2md.exe (setup wizard)
# Usage: .\build.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Resolve-BuildPython {
    $candidates = @()
    if ($env:ANY2MD_PYTHON) { $candidates += $env:ANY2MD_PYTHON }
    $candidates += @(
        "F:\Python\Python 3.13.0\python.exe",
        "F:\Python\Python312\python.exe",
        "F:\Python\Python311\python.exe"
    )
    foreach ($p in $candidates) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    foreach ($ver in @("3.13", "3.12", "3.11")) {
        try {
            $py = (& py "-$ver" -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
            if ($py -and (Test-Path $py)) { return $py.Trim() }
        } catch { }
    }
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $p = $cmd.Source
        if ($p -match "WindowsApps") { continue }
        try {
            & $p -c "import sys" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $p }
        } catch { }
    }
    throw "No usable Python found. Install Python 3.11+ or set ANY2MD_PYTHON to python.exe path."
}

$EngineSrc = Join-Path (Split-Path $Root -Parent) "engine"
$Bundle = Join-Path $Root "_bundle\engine"
$CollectName = "any2md_stage"
$Dist = Join-Path $Root "dist\$CollectName"
$DistLegacy = Join-Path $Root "dist\any2md"

Set-Location $Root

if (-not (Test-Path $EngineSrc)) {
    Write-Error "Engine not found: $EngineSrc"
}

Get-Process -Name "any2md" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping running any2md (PID $($_.Id))..." -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
    Start-Sleep -Seconds 1
}

# Preserve user data from either live or legacy dist folder
$Backup = Join-Path $Root "dist\_rebuild_backup"
$BackupFrom = if (Test-Path $DistLegacy) { $DistLegacy } elseif (Test-Path $Dist) { $Dist } else { $null }
if ($BackupFrom) {
    Write-Host "== Backup config/models/output ==" -ForegroundColor Cyan
    if (Test-Path $Backup) { Remove-Item $Backup -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    foreach ($name in @("config.json", "models", "output")) {
        $src = Join-Path $BackupFrom $name
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $Backup $name) -Recurse -Force
        }
    }
}

Write-Host "== Sync engine -> _bundle/engine ==" -ForegroundColor Cyan
if (Test-Path (Split-Path $Bundle -Parent)) {
    Remove-Item (Split-Path $Bundle -Parent) -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null
Copy-Item -Path (Join-Path $EngineSrc "*") -Destination $Bundle -Recurse -Force

$Python = Resolve-BuildPython
Write-Host "Python: $Python" -ForegroundColor Cyan

Write-Host "== Install build deps ==" -ForegroundColor Cyan
& $Python -m pip install -q -r requirements-build.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

Write-Host "== Remove stage dist ==" -ForegroundColor Cyan
if (Test-Path $Dist) {
    Remove-Item $Dist -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "== PyInstaller -> dist\$CollectName ==" -ForegroundColor Cyan
$env:ANY2MD_COLLECT_NAME = $CollectName
& $Python -m PyInstaller --noconfirm --clean any2md.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path (Join-Path $Dist "_internal\python313.dll"))) {
    Write-Error "Build incomplete: missing $Dist\_internal\python313.dll"
}

if (Test-Path $Backup) {
    Write-Host "== Restore config/models/output ==" -ForegroundColor Cyan
    foreach ($name in @("config.json", "models", "output")) {
        $src = Join-Path $Backup $name
        if (Test-Path $src) {
            Copy-Item -Path $src -Destination (Join-Path $Dist $name) -Recurse -Force
        }
    }
    Remove-Item $Backup -Recurse -Force
}

Write-Host ""
Write-Host "Done: $Dist\any2md.exe" -ForegroundColor Green
if (Test-Path $DistLegacy) {
    Write-Host "Note: broken/locked legacy folder still at dist\any2md — use dist\$CollectName instead." -ForegroundColor Yellow
    Write-Host "After closing IDE tabs there, delete dist\any2md and optionally rename $CollectName -> any2md." -ForegroundColor Yellow
}
Write-Host "Copy optional runtime/python.exe beside exe for offline downloads."
