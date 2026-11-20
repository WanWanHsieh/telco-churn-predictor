"""共用 fixture：合成樣本與只訓練一次的產物（session 範圍，避免重複訓練拖慢測試）。"""

from pathlib import Path

import pytest

from churn_ml.config import TrainConfig
from churn_ml.pipeline import TrainingResult, run_training

SAMPLE_CSV = Path(__file__).parent / "fixtures" / "sample_telco.csv"


@pytest.fixture(scope="session")
def sample_csv() -> Path:
    return SAMPLE_CSV


@pytest.fixture(scope="session")
def trained_run(tmp_path_factory: pytest.TempPathFactory) -> TrainingResult:
    """以合成樣本、`epochs=2`、預設策略訓練一次；產物寫在臨時目錄（不碰 models/）。"""
    config = TrainConfig(
        data_path=SAMPLE_CSV,
        output_dir=tmp_path_factory.mktemp("run_default"),
        epochs=2,
    )
    return run_training(config)
