param(
    [string]$OutputRoot = "$PSScriptRoot\..\out"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Dist = Join-Path $OutputRoot "dist"
$Build = Join-Path $OutputRoot "build"

Set-Location $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.11+ from python.org first."
}

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

$Ffmpeg = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
$Ffprobe = (Get-Command ffprobe.exe -ErrorAction SilentlyContinue).Source

if (-not $Ffmpeg -or -not $Ffprobe) {
    throw "ffmpeg.exe and ffprobe.exe were not found on PATH. Install FFmpeg for Windows, then rerun this script."
}

.\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name "Auralis" `
    --icon ".\assets\Auralis.ico" `
    --add-data ".\assets;assets" `
    --add-data ".\Resources;Resources" `
    --add-binary "$Ffmpeg;." `
    --add-binary "$Ffprobe;." `
    --distpath $Dist `
    --workpath $Build `
    --specpath $OutputRoot `
    .\Auralis_launcher.py

Write-Host "Built: $(Join-Path $Dist 'Auralis.exe')"
