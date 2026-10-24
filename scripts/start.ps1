# Start the full stack in the background, using an NVIDIA GPU when one is usable and the
# CPU otherwise.
#
#   .\scripts\start.ps1            auto-detect GPU, real local LLM (Ollama)
#   .\scripts\start.ps1 -Cpu       force CPU even if a GPU is present
#   .\scripts\start.ps1 -Mock      demo mode: no LLM download, answers quote the sources
#   .\scripts\start.ps1 -Attach    stay in the foreground and stream logs (Ctrl+C stops)
param(
    [switch]$Cpu,
    [switch]$Mock,
    [switch]$Attach,
    [switch]$Detach  # accepted for compatibility; running in the background is the default
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
    $mode = "GPU"
    Write-Host "NVIDIA GPU detected and usable from Docker -> GPU mode"
    $composeArgs += @("-f", "docker-compose.gpu.yml")
} else {
    $mode = "CPU"
    Write-Host "No usable NVIDIA GPU (or -Cpu given) -> CPU mode"
}

if ($Mock) {
    Write-Host "Demo mode: LLM_PROVIDER=mock (Ollama is not started)"
    $env:LLM_PROVIDER = "mock"
} else {
    $env:LLM_PROVIDER = "ollama"
    $composeArgs += @("--profile", "llm")
}

$composeArgs += @("up", "--build")
if ($Attach) {
    & docker @composeArgs
    exit $LASTEXITCODE
}

# --wait returns once every service is running/healthy (and the model is pulled).
$composeArgs += @("--detach", "--wait")
Write-Host "Building and starting in the background. The first run downloads images and the model; this can take a while..."
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Startup failed. Inspect the logs with: docker compose logs" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Knowledge Assistant is running ($mode mode)." -ForegroundColor Green
Write-Host "  Web UI:                http://localhost:5173"
Write-Host "  API docs:              http://localhost:8000/docs"
Write-Host "  Load sample articles:  docker compose exec backend python -m scripts.seed"
Write-Host "  Follow logs:           docker compose logs -f backend"
Write-Host "  Stop everything:       docker compose --profile llm down"
