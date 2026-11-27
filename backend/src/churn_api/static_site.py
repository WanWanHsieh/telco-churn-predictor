"""單一容器部署時，由 FastAPI 直接提供前端建置產物（SPA）。

只有設定 `STATIC_DIR` 時才掛載；本機開發與 docker compose（nginx 提供前端）不受影響。
路由順序：API、/docs、/openapi.json 先註冊，這裡的 catch-all 最後註冊，因此不會蓋掉它們。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# /api/ 底下找不到的路徑仍回 JSON 404，不回前端頁面
_API_PREFIX = "api/"
# 對齊 frontend/nginx.conf；不加 X-Frame-Options，因為 Hugging Face Spaces 以 iframe 嵌入
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """掛載 `static_dir`（Vite 的 dist）：/assets 走靜態檔，其餘路徑回 index.html。"""
    root = static_dir.resolve()
    index_file = root / "index.html"
    if not index_file.is_file():
        raise RuntimeError(f"STATIC_DIR 內找不到 index.html：{root}")

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa_fallback(path: str) -> FileResponse:
        if path == "api" or path.startswith(_API_PREFIX):
            raise StarletteHTTPException(status_code=404)
        if path:
            try:
                candidate = (root / path).resolve()
            except ValueError, OSError:  # 例如含 NUL 字元的路徑
                candidate = None
            # 只回 static_dir 內的實體檔（例如 favicon），防止 ../ 路徑穿越
            if candidate is not None and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate, headers=_SECURITY_HEADERS)
        return FileResponse(index_file, headers={**_SECURITY_HEADERS, "Cache-Control": "no-cache"})
