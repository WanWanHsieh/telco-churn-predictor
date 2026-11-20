"""命令列入口：`churn-train`（訓練）與 `churn-verify`（驗證產物）。

結束碼：0 成功；1 驗證未達標；2 資料檔缺失或內容不符（友善訊息、不印堆疊）。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from churn_ml.config import (
    DEFAULT_DATA_PATH,
    DEFAULT_OUTPUT_DIR,
    IMBALANCE_STRATEGIES,
    ImbalanceStrategy,
    TrainConfig,
)
from churn_ml.data import DataFileNotFoundError, DataValidationError
from churn_ml.evaluate import MODEL_KEYS
from churn_ml.export import verify_artifacts
from churn_ml.pipeline import run_training


class JsonFormatter(logging.Formatter):
    """一行一個 JSON（design.md 8）：ts、level、logger、event、message 與事件欄位。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False, default=str)


def _configure_logging() -> None:
    logger = logging.getLogger("churn_ml")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _print_summary(metrics: dict[str, Any], output_dir: Path) -> None:
    """結束時印人類可讀的成效摘要表。"""
    print("\n=== 訓練完成：測試集成效 ===")
    print(
        f"{'模型':<14}{'門檻':>6}{'ROC-AUC':>10}{'Precision':>11}{'Recall':>8}{'F1':>8}{'Accuracy':>10}"
    )
    for entry in metrics["models"]:
        m = entry["metrics"]
        print(
            f"{entry['key']:<14}{entry['decision_threshold']:>6.2f}{m['roc_auc']:>10.4f}"
            f"{m['precision']:>11.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}{m['accuracy']:>10.4f}"
        )
    for warning in metrics["warnings"]:
        print(f"警告：{warning}")
    print(f"模型版本：{metrics['model_version']}；產物目錄：{output_dir}")


def _train_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="churn-train", description="訓練流失預測模型並匯出產物")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="原始 CSV 路徑")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="產物輸出目錄")
    parser.add_argument("--seed", type=int, default=42, help="亂數種子（預設 42）")
    parser.add_argument("--epochs", type=int, default=100, help="Keras epoch 上限（預設 100）")
    parser.add_argument(
        "--imbalance-strategy",
        choices=IMBALANCE_STRATEGIES,
        default="threshold_tuning",
        help="匯出哪一版：threshold_tuning（預設）或 class_weight",
    )
    parser.add_argument("--target-recall", type=float, default=0.75, help="選門檻的 Recall 目標")
    return parser


def train_main(argv: Sequence[str] | None = None) -> int:
    """churn-train 入口。"""
    args = _train_parser().parse_args(argv)
    strategy: ImbalanceStrategy = args.imbalance_strategy
    try:
        config = TrainConfig(
            data_path=args.data,
            output_dir=args.output_dir,
            seed=args.seed,
            epochs=args.epochs,
            imbalance_strategy=strategy,
            target_recall=args.target_recall,
        )
    except ValueError as exc:
        print(f"參數錯誤：{exc}", file=sys.stderr)
        return 2

    _configure_logging()
    try:
        result = run_training(config)
    except (DataFileNotFoundError, DataValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _print_summary(result.metrics, config.output_dir)
    return 0


def verify_main(argv: Sequence[str] | None = None) -> int:
    """churn-verify 入口：逐項印出檢查結果，任一項未達標 exit 1。"""
    parser = argparse.ArgumentParser(prog="churn-verify", description="驗證模型產物")
    parser.add_argument("--artifacts", type=Path, required=True, help="產物目錄（如 models）")
    parser.add_argument("--compare", type=Path, default=None, help="另一次訓練的產物目錄")
    args = parser.parse_args(argv)

    checks = verify_artifacts(args.artifacts, args.compare)
    for check in checks:
        print(f"[{'通過' if check.ok else '未達標'}] {check.name}：{check.detail}")
    failed = [c for c in checks if not c.ok]
    if failed:
        print(f"\n共 {len(failed)} 項未達標：{'、'.join(c.name for c in failed)}", file=sys.stderr)
        return 1
    print(f"\n全部 {len(checks)} 項通過（{' / '.join(MODEL_KEYS)}）")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(train_main())
