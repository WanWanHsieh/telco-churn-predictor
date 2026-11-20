"""訓練管線：讀檔 → 清理 → 估算 → 切分 → 前處理 → LR／Keras（不平衡實驗）→ 門檻 → 評估 → 匯出。"""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from churn_core.imputation import impute_total_charges
from churn_core.preprocessing import Preprocessor
from churn_core.schema import TARGET
from churn_ml.config import TrainConfig
from churn_ml.data import Split, load_raw_csv, prepare_frame, split_indices
from churn_ml.evaluate import MODEL_KEYS, evaluate, roc_curve_downsampled
from churn_ml.export import export_artifacts, sha256_file
from churn_ml.models import (
    build_logreg,
    predict_proba_logreg,
    predict_proba_mlp,
    train_mlp,
)
from churn_ml.reproducibility import set_global_seed
from churn_ml.thresholds import ThresholdChoice, select_threshold

logger = logging.getLogger("churn_ml")

DISPLAY_NAMES = {"logistic_regression": "邏輯迴歸（基準）", "keras_mlp": "Keras 神經網路"}
STRATEGY_TO_VARIANT = {"threshold_tuning": "none", "class_weight": "class_weight"}
PACKAGE_DISTRIBUTIONS = ("tensorflow", "keras-nightly", "numpy", "pandas", "scikit-learn")


def log_event(event: str, **fields: object) -> None:
    """結構化 log：CLI 的 JSON formatter 會把 event 與 fields 展開成一行 JSON。"""
    logger.info(event, extra={"event": event, "fields": fields})


@dataclass
class _Variant:
    """一個（模型, 不平衡策略）組合的訓練結果。"""

    model_key: str
    strategy: str  # "none" | "class_weight"
    model: Any
    test_proba: NDArray[np.float64]
    choice: ThresholdChoice
    epochs_run: int | None = None


@dataclass(frozen=True)
class TrainingResult:
    config: TrainConfig
    metrics: dict[str, Any]
    manifest: dict[str, Any]
    split: Split


def _round_threshold(value: float) -> float:
    return round(float(value), 2)


def estimate_error_stats(train_cleaned: pd.DataFrame) -> dict[str, Any]:
    """訓練子集中「有填 TotalCharges 且 > 0」的列，|實際 − tenure×月費| / 實際 的中位數與 P90。"""
    total = train_cleaned["TotalCharges"]
    mask = total.notna() & (total > 0)
    if not bool(mask.any()):
        return {"computed_on": "training_subset", "n_rows": 0, "median": None, "p90": None}
    actual = total[mask].to_numpy(dtype=np.float64)
    estimate = (
        train_cleaned.loc[mask, "tenure"] * train_cleaned.loc[mask, "MonthlyCharges"]
    ).to_numpy(dtype=np.float64)
    relative = np.abs(actual - estimate) / actual
    return {
        "computed_on": "training_subset",
        "n_rows": int(mask.sum()),
        "median": round(float(np.median(relative)), 6),
        "p90": round(float(np.percentile(relative, 90)), 6),
    }


def _package_versions() -> dict[str, str]:
    packages = {"python": platform.python_version()}
    packages.update({name: version(name) for name in PACKAGE_DISTRIBUTIONS})
    return packages


def run_training(config: TrainConfig) -> TrainingResult:
    """執行完整訓練並寫出 5 個產物到 `config.output_dir`。"""
    started_at = datetime.now(UTC)
    set_global_seed(config.seed)
    packages = _package_versions()

    raw = load_raw_csv(config.data_path)
    data_sha = sha256_file(config.data_path)
    cleaned, report = prepare_frame(raw)
    log_event("data_cleaned", **report.to_dict())

    imputed, is_estimated = impute_total_charges(cleaned)
    log_event("total_charges_imputed", estimated_rows=int(is_estimated.sum()))

    y = cleaned[TARGET].to_numpy(dtype=np.int64)
    split = split_indices(
        y, seed=config.seed, test_size=config.test_size, validation_size=config.validation_size
    )
    log_event(
        "data_split",
        train=len(split.train),
        validation=len(split.validation),
        test=len(split.test),
    )

    # 前處理只以訓練子集擬合（AC-4.4）
    preprocessor = Preprocessor().fit(imputed.iloc[split.train])
    x_train = preprocessor.transform(imputed.iloc[split.train])
    x_val = preprocessor.transform(imputed.iloc[split.validation])
    x_test = preprocessor.transform(imputed.iloc[split.test])
    y_train, y_val, y_test = y[split.train], y[split.validation], y[split.test]
    log_event(
        "training_start",
        seed=config.seed,
        rows=len(cleaned),
        n_features=preprocessor.n_features,
        packages=packages,
    )

    variants: dict[tuple[str, str], _Variant] = {}
    for strategy in ("none", "class_weight"):
        weighted = strategy == "class_weight"

        logreg = build_logreg(config.seed, class_weight="balanced" if weighted else None)
        logreg.fit(x_train, y_train)
        variants[("logistic_regression", strategy)] = _Variant(
            "logistic_regression",
            strategy,
            logreg,
            predict_proba_logreg(logreg, x_test),
            select_threshold(y_val, predict_proba_logreg(logreg, x_val), config.target_recall),
        )

        mlp, epochs_run = train_mlp(
            x_train,
            y_train,
            x_val,
            y_val,
            seed=config.seed,
            epochs=config.epochs,
            batch_size=config.batch_size,
            patience=config.patience,
            weighted=weighted,
        )
        variants[("keras_mlp", strategy)] = _Variant(
            "keras_mlp",
            strategy,
            mlp,
            predict_proba_mlp(mlp, x_test),
            select_threshold(y_val, predict_proba_mlp(mlp, x_val), config.target_recall),
            epochs_run,
        )
        log_event("models_trained", strategy=strategy, keras_epochs=epochs_run)

    # 不平衡實驗：兩模型 × 不加權／加權 × 預設 0.5／驗證集調整後門檻（AC-4.5）
    experiment: list[dict[str, Any]] = []
    for strategy in ("none", "class_weight"):
        for key in MODEL_KEYS:
            variant = variants[(key, strategy)]
            for rule, threshold in (("default_0.5", 0.5), ("tuned", variant.choice.threshold)):
                result = evaluate(y_test, variant.test_proba, threshold)
                experiment.append(
                    {
                        "model": key,
                        "strategy": strategy,
                        "threshold_rule": rule,
                        "threshold": _round_threshold(threshold),
                        "recall": round(result.recall, 4),
                        "precision": round(result.precision, 4),
                        "roc_auc": round(result.roc_auc, 4),
                    }
                )

    exported = STRATEGY_TO_VARIANT[config.imbalance_strategy]
    model_entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    for key in MODEL_KEYS:
        variant = variants[(key, exported)]
        result = evaluate(y_test, variant.test_proba, variant.choice.threshold)
        model_entries.append(
            {
                "key": key,
                "display_name": DISPLAY_NAMES[key],
                "decision_threshold": _round_threshold(variant.choice.threshold),
                "metrics": result.metrics_dict(),
                "confusion_matrix": result.confusion_dict(),
                "roc_curve": roc_curve_downsampled(y_test, variant.test_proba),
            }
        )
        if variant.choice.warning:
            warnings.append(f"{DISPLAY_NAMES[key]}：{variant.choice.warning}")
            log_event("threshold_warning", model=key, message=variant.choice.warning)
    keras_model = variants[("keras_mlp", exported)].model
    keras_epochs = variants[("keras_mlp", exported)].epochs_run

    baseline = x_train.astype(np.float64).mean(axis=0)
    baseline_probability = float(
        predict_proba_mlp(keras_model, baseline.astype(np.float32)[np.newaxis, :])[0]
    )
    explainer = {
        "method": "integrated_gradients",
        "baseline": [float(v) for v in baseline],
        "baseline_probability": baseline_probability,
    }

    test_churn_rate = float(np.mean(y_test))
    finished_at = datetime.now(UTC).replace(microsecond=0)

    def build_metrics(model_version: str) -> dict[str, Any]:
        return {
            "primary_model": "keras_mlp",
            "model_version": model_version,
            "trained_at": finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "random_seed": config.seed,
            "imbalance_strategy": config.imbalance_strategy,
            "target_recall": config.target_recall,
            "dataset": {
                "train_size": len(split.train),
                "validation_size": len(split.validation),
                "test_size": len(split.test),
                "test_churn_rate": round(test_churn_rate, 4),
                "majority_class_accuracy": round(1.0 - test_churn_rate, 4),
            },
            "models": model_entries,
            "decision_threshold": model_entries[1]["decision_threshold"],
            "imbalance_experiment": experiment,
            "warnings": warnings,
        }

    manifest_base: dict[str, Any] = {
        "seed": config.seed,
        "data": {
            "file_name": config.data_path.name,
            "rows": report.rows,
            "sha256": data_sha,
            "cleaning_report": report.to_dict(),
        },
        "split": {
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
        },
        "n_features": preprocessor.n_features,
        "feature_names": preprocessor.feature_names,
        "packages": packages,
        "total_charges_estimate_error": estimate_error_stats(cleaned.iloc[split.train]),
        "imbalance_strategy": config.imbalance_strategy,
        "training": {
            "config": config.to_dict(),
            "started_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "keras_epochs_run": keras_epochs,
        },
    }

    manifest = export_artifacts(
        config.output_dir,
        model=keras_model,
        preprocessor=preprocessor,
        explainer=explainer,
        build_metrics=build_metrics,
        manifest_base=manifest_base,
        trained_at=finished_at,
    )
    log_event(
        "artifacts_written",
        output_dir=str(config.output_dir),
        model_version=manifest["model_version"],
    )
    metrics = build_metrics(manifest["model_version"])
    return TrainingResult(config=config, metrics=metrics, manifest=manifest, split=split)
