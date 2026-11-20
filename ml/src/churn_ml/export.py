"""寫出 5 個模型產物（design.md 5.1）與驗證產物（churn-verify）。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from churn_core.preprocessing import Preprocessor
from churn_core.schema import ID_COLUMN
from churn_ml.evaluate import check_metrics_structure

MODEL_FILE = "churn_mlp.keras"
PREPROCESSOR_FILE = "preprocessor.json"
EXPLAINER_FILE = "explainer.json"
METRICS_FILE = "metrics.json"
MANIFEST_FILE = "manifest.json"
ARTIFACT_FILES = (MODEL_FILE, PREPROCESSOR_FILE, EXPLAINER_FILE, METRICS_FILE, MANIFEST_FILE)
# manifest.files 記錄雜湊的檔案（manifest 自己不能包含自己的雜湊）
HASHED_FILES = (MODEL_FILE, PREPROCESSOR_FILE, EXPLAINER_FILE, METRICS_FILE)

# 成效門檻（requirements NFR-1、NFR-2、AC-4.6）
NFR1_MIN_AUC = 0.82
NFR1_MIN_RECALL = 0.70
NFR2_MAX_AUC_GAP = 0.01
COMPARE_MAX_AUC_DIFF = 0.01


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    """UTF-8、縮排 2、結尾換行；浮點以 repr 輸出，往返不失真。"""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_artifacts(
    output_dir: Path,
    *,
    model: Any,
    preprocessor: Preprocessor,
    explainer: Mapping[str, Any],
    build_metrics: Callable[[str], Mapping[str, Any]],
    manifest_base: Mapping[str, Any],
    trained_at: datetime,
) -> dict[str, Any]:
    """寫出 5 個檔案並回傳 manifest。

    `model_version` = `YYYYMMDD-<churn_mlp.keras 的 SHA-256 前 8 碼>`，所以先存模型再建 metrics。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / MODEL_FILE
    model.save(str(model_path))
    model_version = f"{trained_at:%Y%m%d}-{sha256_file(model_path)[:8]}"

    (output_dir / PREPROCESSOR_FILE).write_text(preprocessor.to_json() + "\n", encoding="utf-8")
    write_json(output_dir / EXPLAINER_FILE, explainer)
    write_json(output_dir / METRICS_FILE, build_metrics(model_version))

    manifest: dict[str, Any] = {
        "model_version": model_version,
        "trained_at": trained_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        **manifest_base,
        "files": {name: sha256_file(output_dir / name) for name in HASHED_FILES},
    }
    write_json(output_dir / MANIFEST_FILE, manifest)
    return manifest


# ---------------------------------------------------------------- churn-verify
@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


def _keras_and_lr(metrics: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    by_key = {m["key"]: m for m in metrics["models"]}
    return by_key["keras_mlp"]["metrics"], by_key["logistic_regression"]["metrics"]


def verify_artifacts(artifacts: Path, compare: Path | None = None) -> list[Check]:
    """檢查產物；每一項回傳一個 Check，全部 ok 才算通過。"""
    checks: list[Check] = []
    missing = [name for name in ARTIFACT_FILES if not (artifacts / name).is_file()]
    checks.append(
        Check("5 個檔案存在", not missing, "缺少：" + "、".join(missing) if missing else "齊全")
    )
    if missing:
        return checks

    manifest = _load_json(artifacts / MANIFEST_FILE)
    metrics = _load_json(artifacts / METRICS_FILE)
    preprocessor = _load_json(artifacts / PREPROCESSOR_FILE)
    if manifest is None or metrics is None or preprocessor is None:
        checks.append(Check("JSON 可讀", False, "manifest／metrics／preprocessor 不是合法 JSON"))
        return checks

    listed = manifest.get("files", {})
    bad = [
        name
        for name in HASHED_FILES
        if listed.get(name) != sha256_file(artifacts / name)  # 缺漏或不符都算
    ]
    checks.append(Check("manifest 雜湊相符", not bad, "不符：" + "、".join(bad) if bad else "相符"))

    names = [*manifest.get("feature_names", []), *preprocessor.get("feature_names", [])]
    leaked = any(ID_COLUMN.lower() in str(n).lower() for n in names)
    checks.append(
        Check(f"{ID_COLUMN} 不在特徵中", not leaked and bool(names), f"{len(names)} 個名稱")
    )

    problems = check_metrics_structure(metrics)
    checks.append(Check("metrics.json 結構", not problems, "；".join(problems) or "符合 6.5.4"))
    if problems:
        return checks

    keras_m, lr_m = _keras_and_lr(metrics)
    auc, recall = float(keras_m["roc_auc"]), float(keras_m["recall"])
    checks.append(
        Check(
            "NFR-1 Keras ROC-AUC 與 Recall",
            auc >= NFR1_MIN_AUC and recall >= NFR1_MIN_RECALL,
            f"AUC {auc:.4f}（>= {NFR1_MIN_AUC}）、Recall {recall:.4f}（>= {NFR1_MIN_RECALL}）",
        )
    )
    lr_auc = float(lr_m["roc_auc"])
    checks.append(
        Check(
            "NFR-2 Keras AUC 不低於 LR 超過 0.01",
            auc >= lr_auc - NFR2_MAX_AUC_GAP,
            f"Keras {auc:.4f}、LR {lr_auc:.4f}",
        )
    )

    if compare is not None:
        other = _load_json(compare / METRICS_FILE)
        if other is None or check_metrics_structure(other):
            checks.append(
                Check("--compare 可讀", False, f"{compare} 的 metrics.json 不存在或結構錯誤")
            )
        else:
            other_auc = float(_keras_and_lr(other)[0]["roc_auc"])
            diff = abs(auc - other_auc)
            checks.append(
                Check(
                    "AC-4.6 兩次訓練 Keras AUC 差",
                    diff <= COMPARE_MAX_AUC_DIFF,
                    f"{auc:.4f} vs {other_auc:.4f}，差 {diff:.4f}（<= {COMPARE_MAX_AUC_DIFF}）",
                )
            )
    return checks
