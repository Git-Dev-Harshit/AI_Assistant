#!/usr/bin/env sh
# Start the full stack, using an NVIDIA GPU when one is usable and the CPU otherwise.
#
#   ./scripts/start.sh            auto-detect GPU, real local LLM (Ollama)
#   ./scripts/start.sh --cpu      force CPU even if a GPU is present
#   ./scripts/start.sh --mock     demo mode: no LLM download, answers quote the sources
#
# Any other arguments are passed to `docker compose up` (e.g. --detach).
set -eu

cd "$(dirname "$0")/.."

FORCE_CPU=0
MOCK=0
PASSTHROUGH=""
for arg in "$@"; do
  case "$arg" in
    --cpu) FORCE_CPU=1 ;;
    --mock) MOCK=1 ;;
    *) PASSTHROUGH="$PASSTHROUGH $arg" ;;
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
  echo "NVIDIA GPU detected and usable from Docker -> GPU mode"
  COMPOSE_ARGS="$COMPOSE_ARGS -f docker-compose.gpu.yml"
else
  echo "No usable NVIDIA GPU (or --cpu given) -> CPU mode"
fi

if [ "$MOCK" -eq 1 ]; then
  echo "Demo mode: LLM_PROVIDER=mock (Ollama is not started)"
  export LLM_PROVIDER=mock
else
  export LLM_PROVIDER=ollama
  COMPOSE_ARGS="$COMPOSE_ARGS --profile llm"
fi

# shellcheck disable=SC2086
exec docker compose $COMPOSE_ARGS up --build $PASSTHROUGH
