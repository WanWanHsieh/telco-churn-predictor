"""後端設定（design.md 第 7 節）：全部由環境變數讀取，皆有預設值，不設定 .env 也能啟動。

啟動時驗證：風險切點需 0 < medium < high < 1、CORS 不允許 `*`、IG 步數 16–256；
任何一項不合法都會拋 `pydantic.ValidationError`，讓服務拒絕啟動。
"""

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:8080"]


class Settings(BaseSettings):
    """後端環境變數。欄位名稱即環境變數名稱（不分大小寫）。"""

    # model_dir 以 model_ 開頭，需關閉 pydantic 的保留命名空間警告
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    app_env: Literal["production", "development"] = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    model_dir: Path = Path("./models")
    # NoDecode：以逗號分隔的字串讀入，不當成 JSON 解析（解析在下方 validator）
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS)
    )
    risk_medium_threshold: float = 0.30
    risk_high_threshold: float = 0.60
    batch_max_file_bytes: int = Field(default=5_242_880, gt=0)
    batch_max_rows: int = Field(default=10_000, gt=0)
    ig_steps: int = Field(default=64, ge=16, le=256)
    # 設定時由後端一併提供前端靜態檔（單一容器部署，例如 Hugging Face Spaces）
    static_dir: Path | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """逗號分隔字串 → 清單；逐一檢查格式，拒絕 `*` 與非 http(s) 來源。"""
        if isinstance(value, str):
            items: list[object] = [part for part in value.split(",")]
        elif isinstance(value, list | tuple):
            items = list(value)
        else:
            return value
        origins: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ValueError("CORS_ALLOW_ORIGINS 的每個來源都需為字串")
            origin = item.strip()
            if not origin:
                continue
            if origin == "*":
                raise ValueError("CORS_ALLOW_ORIGINS 不允許使用 *，請列出明確的來源")
            parts = urlsplit(origin)
            if (
                parts.scheme not in ("http", "https")
                or not parts.netloc
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise ValueError(f"CORS 來源格式需為 http(s)://主機[:埠]，收到：{origin}")
            origins.append(f"{parts.scheme}://{parts.netloc}")
        return origins

    @model_validator(mode="after")
    def _check_thresholds(self) -> Settings:
        if not 0 < self.risk_medium_threshold < self.risk_high_threshold < 1:
            raise ValueError(
                "風險切點需滿足 0 < RISK_MEDIUM_THRESHOLD < RISK_HIGH_THRESHOLD < 1，"
                f"目前為 {self.risk_medium_threshold}、{self.risk_high_threshold}"
            )
        return self
