#!/usr/bin/env sh
# Start the full stack in the background, using an NVIDIA GPU when one is usable and the
# CPU otherwise.
#
#   ./scripts/start.sh            auto-detect GPU, real local LLM (Ollama)
#   ./scripts/start.sh --cpu      force CPU even if a GPU is present
#   ./scripts/start.sh --mock     demo mode: no LLM download, answers quote the sources
#   ./scripts/start.sh --attach   stay in the foreground and stream logs (Ctrl+C stops)
set -eu

cd "$(dirname "$0")/.."

FORCE_CPU=0
MOCK=0
ATTACH=0
for arg in "$@"; do
  case "$arg" in
    --cpu) FORCE_CPU=1 ;;
    --mock) MOCK=1 ;;
    --attach) ATTACH=1 ;;
    --detach) ;;  # accepted for compatibility; running in the background is the default
    *) echo "Unknown option: $arg (use --cpu, --mock, --attach)" >&2; exit 2 ;;
  esac
done

gpu_usable() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi >/dev/null 2>&1 || return 1
  # The host has a GPU; check that Docker can actually pass it into a container.
  docker run --rm --gpus all busybox true >/dev/null 2>&1
}

COMPOSE_ARGS="-f docker-compose.yml"
if [ "$FORCE_CPU" -eq 0 ] && gpu_usable; then
  MODE=GPU
  echo "NVIDIA GPU detected and usable from Docker -> GPU mode"
  COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.gpu.yml"
else
  MODE=CPU
  echo "No usable NVIDIA GPU (or --cpu given) -> CPU mode"
fi

if [ "$MOCK" -eq 1 ]; then
  echo "Demo mode: LLM_PROVIDER=mock (Ollama is not started)"
  export LLM_PROVIDER=mock
else
  export LLM_PROVIDER=ollama
  COMPOSE_ARGS="$COMPOSE_ARGS --profile llm"
fi

if [ "$ATTACH" -eq 1 ]; then
  # shellcheck disable=SC2086
  exec docker compose $COMPOSE_ARGS up --build
fi

echo "Building and starting in the background. The first run downloads images and the model; this can take a while..."
# --wait returns once every service is running/healthy (and the model is pulled).
# shellcheck disable=SC2086
if ! docker compose $COMPOSE_ARGS up --build --detach --wait; then
  echo "Startup failed. Inspect the logs with: docker compose logs" >&2
  exit 1
fi

cat <<EOF

Knowledge Assistant is running ($MODE mode).
  Web UI:                http://localhost:5173
  API docs:              http://localhost:8000/docs
  Load sample articles:  docker compose exec backend python -m scripts.seed
  Follow logs:           docker compose logs -f backend
  Stop everything:       docker compose --profile llm down
EOF
