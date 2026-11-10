# whisper.cpp setup (Windows) - ek baar chalana hai.
# Kaam: whisper.cpp ka ready-made Windows build + Hindi-capable model download karta hai,
# aur ffmpeg na ho to install karta hai.
#
# Chalane ka tarika (repo folder ke andar, PowerShell mein):
#   powershell -ExecutionPolicy Bypass -File Tools\whisper\setup.ps1

param(
    # Model: large-v3-turbo (approx 1.6 GB, Hindi ke liye accha), medium (1.5 GB), small (470 MB, tez par kam accurate)
    [string]$Model = "large-v3-turbo"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$here   = Split-Path -Parent $MyInvocation.MyCommand.Path
$binDir = Join-Path $here "bin"
$modDir = Join-Path $here "models"
New-Item -ItemType Directory -Force -Path $binDir, $modDir | Out-Null

# 1) whisper.cpp ka latest Windows x64 build
$exe = Get-ChildItem -Path $binDir -Recurse -Include "whisper-cli.exe", "main.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($exe) {
    Write-Host "whisper.cpp pehle se hai: $($exe.FullName)"
} else {
    Write-Host "whisper.cpp ka latest release dhoondh raha hoon..."
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest" -Headers @{ "User-Agent" = "aivideoeditor-setup" }
    $asset = $rel.assets |
        Where-Object { $_.name -match "\.zip$" -and $_.name -match "x64" -and $_.name -notmatch "cuda|cublas|blas|arm|xcframework" } |
        Select-Object -First 1
    if (-not $asset) {
        Write-Host "Is release mein Windows x64 zip nahi mila. Available files:"
        $rel.assets | ForEach-Object { Write-Host "  $($_.name)" }
        throw "Zip khud download karke '$binDir' mein extract karein: https://github.com/ggml-org/whisper.cpp/releases"
    }
    $zip = Join-Path $binDir $asset.name
    Write-Host "Download: $($asset.name) ($($rel.tag_name))"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $binDir -Force
    Remove-Item $zip
    $exe = Get-ChildItem -Path $binDir -Recurse -Include "whisper-cli.exe", "main.exe" | Select-Object -First 1
    if (-not $exe) { throw "Zip extract hua par whisper-cli.exe nahi mila ($binDir dekhein)." }
    Write-Host "whisper.cpp ready: $($exe.FullName)"
}

# 2) Model
$modelFile = Join-Path $modDir "ggml-$Model.bin"
if (Test-Path $modelFile) {
    Write-Host "Model pehle se hai: $modelFile"
} else {
    Write-Host "Model download ho raha hai (ggml-$Model.bin) - bada file hai, time lagega..."
    Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$Model.bin" -OutFile $modelFile
    Write-Host "Model ready: $modelFile"
}

# 3) ffmpeg (video se audio nikalne ke liye)
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg pehle se installed hai."
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg install ho raha hai (winget)..."
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "ffmpeg install ho gaya. PowerShell band karke dobara kholein, tab ffmpeg chalega."
} else {
    Write-Host "ffmpeg nahi mila aur winget bhi nahi hai. Yahan se install karein: https://www.gyan.dev/ffmpeg/builds/"
}

Write-Host ""
Write-Host "Setup complete. Ab captions banane ke liye:"
Write-Host "  powershell -ExecutionPolicy Bypass -File Tools\whisper\transcribe.ps1 `"Raw\video.mp4`""
