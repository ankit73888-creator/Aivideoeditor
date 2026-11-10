# HyperFrames setup (Windows) - ek baar chalana hai.
# Kaam: Node.js 22+ aur ffmpeg check/install karta hai, phir HyperFrames ka apna health-check chalata hai.
#
# Chalane ka tarika (repo folder ke andar, PowerShell mein):
#   powershell -ExecutionPolicy Bypass -File Tools\hyperframes\setup.ps1

$ErrorActionPreference = "Stop"
$needRestart = $false
$hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# 1) Node.js 22 ya usse naya
$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $major = [int]((& node -v) -replace "^v", "" -split "\.")[0]
    if ($major -ge 22) {
        $nodeOk = $true
        Write-Host "Node.js theek hai: $(& node -v)"
    } else {
        Write-Host "Node.js purana hai ($(& node -v)); HyperFrames ko 22+ chahiye."
    }
}
if (-not $nodeOk) {
    if ($hasWinget) {
        Write-Host "Node.js LTS install ho raha hai (winget)..."
        winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
        $needRestart = $true
    } else {
        throw "Node.js 22+ chahiye. Yahan se install karein: https://nodejs.org/"
    }
}

# 2) ffmpeg
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg pehle se installed hai."
} elseif ($hasWinget) {
    Write-Host "ffmpeg install ho raha hai (winget)..."
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    $needRestart = $true
} else {
    Write-Host "ffmpeg nahi mila. Yahan se install karein: https://www.gyan.dev/ffmpeg/builds/"
}

if ($needRestart) {
    Write-Host ""
    Write-Host "Naye tools install hue hain. PowerShell band karke dobara kholein aur yeh script ek baar phir chalayein."
    exit 0
}

# 3) HyperFrames ka health-check (Chrome, ffmpeg, Node, memory)
Write-Host ""
Write-Host "HyperFrames check chal raha hai..."
& npx --yes hyperframes doctor

Write-Host ""
Write-Host "Setup complete. Naya video project banane ke liye:"
Write-Host "  cd Compositions"
Write-Host "  npx hyperframes init reel-ka-naam"
