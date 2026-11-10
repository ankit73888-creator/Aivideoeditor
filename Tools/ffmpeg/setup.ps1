# FFmpeg setup (Windows) - ek baar chalana hai.
#
# Chalane ka tarika (repo folder ke andar, PowerShell mein):
#   powershell -ExecutionPolicy Bypass -File Tools\ffmpeg\setup.ps1

$ErrorActionPreference = "Stop"

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "FFmpeg pehle se installed hai:"
    & ffmpeg -version | Select-Object -First 1
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "FFmpeg install ho raha hai (winget)..."
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "Install ho gaya. PowerShell band karke dobara kholein, tab 'ffmpeg' command chalega."
} else {
    Write-Host "winget nahi mila. FFmpeg yahan se install karein: https://www.gyan.dev/ffmpeg/builds/"
}
