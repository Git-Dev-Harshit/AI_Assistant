# syntax=docker/dockerfile:1
FROM python:3.12-slim

# CPU wheel by default (small, works everywhere). docker-compose.gpu.yml overrides this
# with the CUDA wheel index so the same image can use an NVIDIA GPU when one is passed in.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_VERSION=2.7.1
# Override only if PyPI is unreachable from your network (e.g. a corporate mirror).
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

# The pip cache mount keeps large wheels (torch/CUDA) between rebuilds without
# baking the cache into the image.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url "${TORCH_INDEX_URL}" --extra-index-url "${PIP_INDEX_URL}" "torch==${TORCH_VERSION}"

COPY requirements.txt requirements-dev.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url "${PIP_INDEX_URL}" -r requirements.txt -r requirements-dev.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
