"""`GET /api/v1/model/metrics` 回應（design.md 6.5.4）。

結構與 `models/metrics.json` 完全相同；後端以此模型驗證後原樣轉發。
`extra="forbid"`：檔案出現合約外的欄位時視為格式錯誤，而不是靜默丟棄。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


class DatasetInfo(_Strict):
    train_size: int
    validation_size: int
    test_size: int
    test_churn_rate: float = Field(description="測試集流失比例（0–1）")
    majority_class_accuracy: float = Field(
        description="1 − test_churn_rate（全猜不流失的 Accuracy）"
    )


class ModelMetrics(_Strict):
    roc_auc: float
    precision: float
    recall: float
    f1: float
    accuracy: float


class ConfusionMatrix(_Strict):
    tn: int
    fp: int
    fn: int
    tp: int


class RocCurve(_Strict):
    fpr: list[float]
    tpr: list[float]

    @model_validator(mode="after")
    def _same_length(self) -> RocCurve:
        if len(self.fpr) != len(self.tpr):
            raise ValueError("roc_curve 的 fpr 與 tpr 長度需相同")
        return self


class ModelResult(_Strict):
    key: Literal["logistic_regression", "keras_mlp"]
    display_name: str
    decision_threshold: float
    metrics: ModelMetrics
    confusion_matrix: ConfusionMatrix
    roc_curve: RocCurve


class ImbalanceExperimentRow(_Strict):
    model: Literal["logistic_regression", "keras_mlp"]
    strategy: Literal["none", "class_weight"]
    threshold_rule: Literal["default_0.5", "tuned"]
    threshold: float
    recall: float
    precision: float
    roc_auc: float


class MetricsResponse(_Strict):
    """成效頁資料（＝ models/metrics.json）。"""

    primary_model: str
    model_version: str
    trained_at: str
    random_seed: int
    imbalance_strategy: Literal["threshold_tuning", "class_weight"]
    target_recall: float
    dataset: DatasetInfo
    models: list[ModelResult] = Field(description="恰 2 筆：logistic_regression、keras_mlp")
    decision_threshold: float = Field(description="主模型（keras_mlp）的決策門檻")
    imbalance_experiment: list[ImbalanceExperimentRow]
    warnings: list[str]

    @model_validator(mode="after")
    def _two_models_in_order(self) -> MetricsResponse:
        if [m.key for m in self.models] != ["logistic_regression", "keras_mlp"]:
            raise ValueError("models 需恰為 logistic_regression、keras_mlp（依此順序）")
        return self
