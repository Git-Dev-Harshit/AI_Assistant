# Start the full stack, using an NVIDIA GPU when one is usable and the CPU otherwise.
#
#   .\scripts\start.ps1            auto-detect GPU
#   .\scripts\start.ps1 -Cpu       force CPU even if a GPU is present
#   .\scripts\start.ps1 -Detach    run in the background
param(
    [switch]$Cpu,
    [switch]$Detach
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Test-GpuUsable {
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { return $false }
    & nvidia-smi *> $null
    if ($LASTEXITCODE -ne 0) { return $false }
    # The host has a GPU; check that Docker can actually pass it into a container.
    & docker run --rm --gpus all busybox true *> $null
    return ($LASTEXITCODE -eq 0)
}

$composeArgs = @("compose", "-f", "docker-compose.yml")
if (-not $Cpu -and (Test-GpuUsable)) {
    Write-Host "NVIDIA GPU detected and usable from Docker -> GPU mode"
    $composeArgs += @("-f", "docker-compose.gpu.yml")
} else {
    Write-Host "No usable NVIDIA GPU (or -Cpu given) -> CPU mode"
}

$composeArgs += @("up", "--build")
if ($Detach) { $composeArgs += "--detach" }

& docker @composeArgs
exit $LASTEXITCODE
