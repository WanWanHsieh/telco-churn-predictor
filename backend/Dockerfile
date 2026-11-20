# syntax=docker/dockerfile:1
# 後端映像（build context = repo 根目錄，需帶入 core/、uv.lock、models/）
# 版本鎖定依 design.md 3.2.1：Python 3.14.8、uv 0.10.2，依賴以 uv.lock --frozen 安裝。

FROM ghcr.io/astral-sh/uv:0.10.2 AS uv

# ---------- builder：安裝依賴到 /app/.venv ----------
FROM python:3.14.8-slim-trixie AS builder
COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

# 先只複製依賴宣告，讓依賴層可被快取
COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
COPY backend/pyproject.toml backend/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package churn-api --no-install-workspace

# 再複製原始碼並安裝 workspace 成員（非 editable，runtime 不需要原始碼目錄）
COPY core/ core/
COPY ml/ ml/
COPY backend/ backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package churn-api --no-editable

# ---------- runtime：只帶 .venv 與模型 ----------
FROM python:3.14.8-slim-trixie AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    KERAS_BACKEND=tensorflow \
    TF_CPP_MIN_LOG_LEVEL=2 \
    MODEL_DIR=/app/models
WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app models/ /app/models/

USER app
EXPOSE 8000

# 只用標準函式庫呼叫 health；模型缺失時回 503 → unhealthy（前端仍會啟動，見 compose）
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]

# 單一 worker：TF 模型每個 process 各佔記憶體，展示用途流量低（design.md 10.2）
CMD ["uvicorn", "churn_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
