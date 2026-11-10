# Video/audio se captions (.srt) banata hai - whisper.cpp se, poora offline.
#
# Chalane ka tarika (repo folder ke andar, PowerShell mein):
#   powershell -ExecutionPolicy Bypass -File Tools\whisper\transcribe.ps1 "Raw\video.mp4"
#
# Options:
#   -Language hi        Bhasha (hi = Hindi, en = English, auto = khud pehchane). Default: hi
#   -Translate          Hindi bolkar English captions banaye
#   -MaxLen 30          Har caption line ke max characters (reels ke chhote captions ke liye). 0 = whisper ka default
#   -Model large-v3-turbo   Wahi model jo setup.ps1 se download kiya tha

param(
    [Parameter(Mandatory = $true, Position = 0)][string]$InputFile,
    [string]$Language = "hi",
    [switch]$Translate,
    [int]$MaxLen = 0,
    [string]$Model = "large-v3-turbo"
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe  = Get-ChildItem -Path (Join-Path $here "bin") -Recurse -Include "whisper-cli.exe", "main.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$modelFile = Join-Path $here "models\ggml-$Model.bin"

if (-not $exe)                   { throw "whisper.cpp nahi mila. Pehle Tools\whisper\setup.ps1 chalayein." }
if (-not (Test-Path $modelFile)) { throw "Model nahi mila ($modelFile). Pehle Tools\whisper\setup.ps1 chalayein." }
if (-not (Test-Path $InputFile)) { throw "File nahi mili: $InputFile" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "ffmpeg nahi mila. setup.ps1 chalayein, phir PowerShell dobara kholein." }

$in      = Get-Item $InputFile
$outBase = Join-Path $in.DirectoryName $in.BaseName
$wav     = Join-Path $env:TEMP ("whisper_" + [guid]::NewGuid().ToString("N") + ".wav")

try {
    Write-Host "Audio nikal raha hoon..."
    & ffmpeg -y -loglevel error -i $in.FullName -vn -ar 16000 -ac 1 -c:a pcm_s16le $wav
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg audio nahi nikal paya." }

    $wargs = @("-m", $modelFile, "-f", $wav, "-l", $Language, "-osrt", "-of", $outBase)
    if ($Translate)    { $wargs += "-tr" }
    if ($MaxLen -gt 0) { $wargs += @("-ml", "$MaxLen", "-sow") }

    Write-Host "Transcribe ho raha hai (video ki length ke hisaab se time lagega)..."
    & $exe.FullName @wargs
    if ($LASTEXITCODE -ne 0) { throw "whisper.cpp fail ho gaya." }
} finally {
    Remove-Item $wav -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Captions ready: $outBase.srt"
Write-Host "Is .srt ko Premiere Pro / DaVinci Resolve mein import kar sakte hain."
