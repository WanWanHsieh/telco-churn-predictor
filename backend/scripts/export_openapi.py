"""匯出（或檢查）`contracts/openapi.json`。

用法（repo 根目錄）：
    uv run python backend/scripts/export_openapi.py          # 寫入 contracts/openapi.json
    uv run python backend/scripts/export_openapi.py --check  # 與程式不一致時 exit 1（CI 用）

OpenAPI 只依賴路由與 schema 定義，不載入模型、不讀環境變數（以預設設定建立應用程式）。
輸出固定為 UTF-8、LF 換行、縮排 2、保留中文，確保 `--check` 在 Windows 與 Linux 結果一致。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from churn_api.main import create_app
from churn_api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "contracts" / "openapi.json"


def generate_openapi() -> dict[str, Any]:
    """以預設設定建立應用程式並取得 OpenAPI 文件（不執行 lifespan，不載入模型）。"""
    app = create_app(Settings.model_construct())  # 只用預設值，不讀環境變數
    schema: dict[str, Any] = app.openapi()
    return schema


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="匯出或檢查 contracts/openapi.json")
    parser.add_argument("--check", action="store_true", help="只檢查檔案是否與程式一致")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="輸出路徑")
    args = parser.parse_args(argv)

    expected = render(generate_openapi())
    output: Path = args.output

    if args.check:
        if not output.is_file():
            print(f"找不到 {output}，請執行 export_openapi.py 產生。", file=sys.stderr)
            return 1
        current = output.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != expected:
            hint = "uv run python backend/scripts/export_openapi.py"
            print(f"{output} 與程式不一致，請重新執行：{hint}", file=sys.stderr)
            return 1
        print(f"{output} 與程式一致。")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8", newline="\n")
    print(f"已寫入 {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
