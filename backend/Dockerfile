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

RUN useradd --create-home --uid 1000 appuser && chown appuser /app

# Bake the embedding model into the image: no download at runtime, works offline,
# and every container starts with exactly the same model files.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')" \
    && chown -R appuser /opt/hf-cache
ENV HF_HUB_OFFLINE=1

# Source changes only invalidate this layer. Ownership is set while copying, so no
# recursive chown layer duplicates the application or model files on every rebuild.
COPY --chown=appuser . .
USER appuser

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
