"""Settings：預設值、環境變數、切點與 CORS 驗證（design.md 第 7 節、NFR-8）。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from churn_api.settings import Settings

ENV_NAMES = [
    "APP_ENV",
    "LOG_LEVEL",
    "MODEL_DIR",
    "CORS_ALLOW_ORIGINS",
    "RISK_MEDIUM_THRESHOLD",
    "RISK_HIGH_THRESHOLD",
    "BATCH_MAX_FILE_BYTES",
    "BATCH_MAX_ROWS",
    "IG_STEPS",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_design() -> None:
    s = Settings(_env_file=None)
    assert s.app_env == "production"
    assert s.log_level == "INFO"
    assert s.model_dir == Path("./models")
    assert s.cors_allow_origins == ["http://localhost:5173", "http://localhost:8080"]
    assert (s.risk_medium_threshold, s.risk_high_threshold) == (0.30, 0.60)
    assert s.batch_max_file_bytes == 5_242_880
    assert s.batch_max_rows == 10_000
    assert s.ig_steps == 64


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_DIR", "/app/models")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("RISK_MEDIUM_THRESHOLD", "0.25")
    monkeypatch.setenv("RISK_HIGH_THRESHOLD", "0.7")
    monkeypatch.setenv("IG_STEPS", "128")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.example.com, http://localhost:3000/")
    s = Settings(_env_file=None)
    assert s.model_dir == Path("/app/models")
    assert s.log_level == "DEBUG"
    assert (s.risk_medium_threshold, s.risk_high_threshold) == (0.25, 0.7)
    assert s.ig_steps == 128
    assert s.cors_allow_origins == ["https://a.example.com", "http://localhost:3000"]


@pytest.mark.parametrize(
    ("medium", "high"),
    [
        (0.6, 0.3),  # 順序顛倒
        (0.5, 0.5),  # 相等
        (0.0, 0.6),  # medium 需 > 0
        (0.3, 1.0),  # high 需 < 1
        (-0.1, 0.6),
        (0.3, 1.5),
    ],
)
def test_invalid_thresholds_refuse_to_start(medium: float, high: float) -> None:
    with pytest.raises(ValidationError, match="RISK_MEDIUM_THRESHOLD"):
        Settings(_env_file=None, risk_medium_threshold=medium, risk_high_threshold=high)


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "http://a.com,*",
        "localhost:5173",
        "ftp://a.com",
        "http://a.com/path",
        "http://a.com?x=1",
    ],
)
def test_cors_rejects_wildcard_and_malformed(origins: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_allow_origins=origins)


def test_cors_empty_means_no_origin_allowed() -> None:
    assert Settings(_env_file=None, cors_allow_origins="").cors_allow_origins == []


@pytest.mark.parametrize("steps", [15, 257, 0])
def test_ig_steps_range(steps: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ig_steps=steps)


@pytest.mark.parametrize("field", ["batch_max_file_bytes", "batch_max_rows"])
def test_batch_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})


def test_invalid_app_env_and_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="LOUD")  # type: ignore[arg-type]
