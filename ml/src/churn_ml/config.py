"""訓練設定（design.md 4.1）。選項會寫進 manifest，所以集中在一個不可變的資料類別。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal

ImbalanceStrategy = Literal["threshold_tuning", "class_weight"]
IMBALANCE_STRATEGIES: Final[tuple[str, ...]] = ("threshold_tuning", "class_weight")

DEFAULT_DATA_PATH: Final = Path("data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv")
DEFAULT_OUTPUT_DIR: Final = Path("models")
KAGGLE_URL: Final = "https://www.kaggle.com/datasets/blastchar/telco-customer-churn"


@dataclass(frozen=True)
class TrainConfig:
    """訓練參數。測試集與驗證集比例固定為 20%（design.md 4.2 步驟 6）。"""

    data_path: Path = DEFAULT_DATA_PATH
    output_dir: Path = DEFAULT_OUTPUT_DIR
    seed: int = 42
    epochs: int = 100  # 上限；實際由 EarlyStopping 決定
    imbalance_strategy: ImbalanceStrategy = "threshold_tuning"
    target_recall: float = 0.75
    test_size: float = 0.2
    validation_size: float = 0.2  # 佔「扣除測試集後」的比例
    batch_size: int = 64
    patience: int = 10

    def __post_init__(self) -> None:
        if self.epochs < 1:
            raise ValueError("epochs 需 >= 1")
        if self.imbalance_strategy not in IMBALANCE_STRATEGIES:
            raise ValueError(f"imbalance_strategy 需為 {'、'.join(IMBALANCE_STRATEGIES)}")
        if not 0.0 < self.target_recall <= 1.0:
            raise ValueError("target_recall 需介於 (0, 1]")
        if not (0.0 < self.test_size < 1.0 and 0.0 < self.validation_size < 1.0):
            raise ValueError("test_size、validation_size 需介於 (0, 1)")

    def to_dict(self) -> dict[str, object]:
        """可寫入 JSON 的設定（路徑轉字串）。"""
        data = asdict(self)
        data["data_path"] = str(self.data_path)
        data["output_dir"] = str(self.output_dir)
        return data
