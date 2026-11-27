# syntax=docker/dockerfile:1
# 單一容器映像（Hugging Face Spaces 等只能跑一個容器的平台）：
# 前端建置產物由 FastAPI 直接提供（STATIC_DIR），不需要 nginx。
# 本機兩容器版本請用 docker compose（backend/Dockerfile、frontend/Dockerfile）。
# build context = repo 根目錄。

FROM ghcr.io/astral-sh/uv:0.10.2 AS uv

# ---------- 前端建置 ----------
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 後端依賴（同 backend/Dockerfile） ----------
FROM python:3.14.8-slim-trixie AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package churn-api --no-install-workspace
COPY core/ core/
COPY ml/ ml/
COPY backend/ backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package churn-api --no-editable

# ---------- runtime ----------
FROM python:3.14.8-slim-trixie AS runtime
# PORT 預設 7860（Hugging Face Spaces 的預設埠）；同網域提供前端，不需設定 CORS
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    KERAS_BACKEND=tensorflow \
    TF_CPP_MIN_LOG_LEVEL=2 \
    MODEL_DIR=/app/models \
    STATIC_DIR=/app/static \
    PORT=7860
WORKDIR /app

# Hugging Face Spaces 以 uid 1000 執行容器
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app models/ /app/models/
COPY --from=frontend --chown=app:app /app/dist /app/static/

USER app
EXPOSE 7860

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4).status == 200 else 1)"]

# 單一 worker：TF 模型每個 process 各佔記憶體
CMD ["sh", "-c", "exec uvicorn churn_api.main:app --host 0.0.0.0 --port \"$PORT\" --workers 1"]
