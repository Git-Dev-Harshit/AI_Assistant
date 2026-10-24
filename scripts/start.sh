#!/usr/bin/env sh
# Start the full stack, using an NVIDIA GPU when one is usable and the CPU otherwise.
#
#   ./scripts/start.sh            auto-detect GPU
#   ./scripts/start.sh --cpu      force CPU even if a GPU is present
#
# Any other arguments are passed to `docker compose up` (e.g. --detach).
set -eu

cd "$(dirname "$0")/.."

FORCE_CPU=0
for arg in "$@"; do
  case "$arg" in
    --cpu) FORCE_CPU=1 ;;
  esac
done

gpu_usable() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi >/dev/null 2>&1 || return 1
  # The host has a GPU; check that Docker can actually pass it into a container.
  docker run --rm --gpus all busybox true >/dev/null 2>&1
}

COMPOSE_FILES="-f docker-compose.yml"
if [ "$FORCE_CPU" -eq 0 ] && gpu_usable; then
  echo "NVIDIA GPU detected and usable from Docker -> GPU mode"
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu.yml"
else
  echo "No usable NVIDIA GPU (or --cpu given) -> CPU mode"
fi

PASSTHROUGH=""
for arg in "$@"; do
  case "$arg" in
    --cpu) ;;
    *) PASSTHROUGH="$PASSTHROUGH $arg" ;;
  esac
done

# shellcheck disable=SC2086
exec docker compose $COMPOSE_FILES up --build $PASSTHROUGH
