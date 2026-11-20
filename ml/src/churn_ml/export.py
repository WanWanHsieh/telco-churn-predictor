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
from churn_ml.evaluate import METRIC_NAMES, check_metrics_structure

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
    write_text_lf(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_text_lf(path: Path, text: str) -> None:
    """固定以 LF 寫出：Windows 預設會轉成 CRLF，雜湊就會因平台而不同。"""
    path.write_text(text, encoding="utf-8", newline="\n")


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

    write_text_lf(output_dir / PREPROCESSOR_FILE, preprocessor.to_json() + "\n")
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


def _raw_metrics(
    manifest: Mapping[str, Any], metrics: Mapping[str, Any]
) -> tuple[dict[str, float] | None, dict[str, float] | None, str | None]:
    """取出 manifest 的未四捨五入指標（Keras、LR），並確認四捨五入後與 metrics.json 相同。

    回傳（keras, lr, 問題說明）；有問題時前兩者為 None。
    """
    raw = manifest.get("unrounded_metrics")
    if not isinstance(raw, dict):
        return None, None, "manifest 缺少 unrounded_metrics"
    shown = {m["key"]: m["metrics"] for m in metrics["models"]}
    result: dict[str, dict[str, float]] = {}
    for key in ("keras_mlp", "logistic_regression"):
        values = raw.get(key)
        if not isinstance(values, dict):
            return None, None, f"unrounded_metrics 缺少 {key}"
        parsed: dict[str, float] = {}
        for name in METRIC_NAMES:
            value = values.get(name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None, None, f"unrounded_metrics.{key}.{name} 不是數字"
            if round(float(value), 4) != shown[key][name]:
                return None, None, f"unrounded_metrics.{key}.{name} 與 metrics.json 不一致"
            parsed[name] = float(value)
        result[key] = parsed
    return result["keras_mlp"], result["logistic_regression"], None


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

    listed = manifest.get("files")
    if not isinstance(listed, dict):
        listed = {}  # 型別不對視為全部缺漏，回報未達標而不是崩潰
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

    # NFR 以未四捨五入的值判斷（metrics.json 只存 4 位小數，0.81996 會被進位成 0.82）
    raw_keras, raw_lr, raw_problem = _raw_metrics(manifest, metrics)
    checks.append(
        Check("未四捨五入指標", raw_problem is None, raw_problem or "與 metrics.json 一致")
    )
    if raw_keras is None or raw_lr is None:
        return checks
    auc, recall = raw_keras["roc_auc"], raw_keras["recall"]
    checks.append(
        Check(
            "NFR-1 Keras ROC-AUC 與 Recall",
            auc >= NFR1_MIN_AUC and recall >= NFR1_MIN_RECALL,
            f"AUC {auc:.6f}（>= {NFR1_MIN_AUC}）、Recall {recall:.6f}（>= {NFR1_MIN_RECALL}）",
        )
    )
    lr_auc = raw_lr["roc_auc"]
    checks.append(
        Check(
            "NFR-2 Keras AUC 不低於 LR 超過 0.01",
            auc >= lr_auc - NFR2_MAX_AUC_GAP,
            f"Keras {auc:.6f}、LR {lr_auc:.6f}",
        )
    )

    if compare is not None:
        other_manifest = _load_json(compare / MANIFEST_FILE)
        other_metrics = _load_json(compare / METRICS_FILE)
        other_keras = None
        if (
            other_manifest is not None
            and other_metrics is not None
            and not check_metrics_structure(other_metrics)
        ):
            other_keras, _, _ = _raw_metrics(other_manifest, other_metrics)
        if other_keras is None:
            checks.append(
                Check("--compare 可讀", False, f"{compare} 的 manifest／metrics 不存在或結構錯誤")
            )
        else:
            other_auc = other_keras["roc_auc"]
            diff = abs(auc - other_auc)
            checks.append(
                Check(
                    "AC-4.6 兩次訓練 Keras AUC 差",
                    diff <= COMPARE_MAX_AUC_DIFF,
                    f"{auc:.6f} vs {other_auc:.6f}，差 {diff:.6f}（<= {COMPARE_MAX_AUC_DIFF}）",
                )
            )
    return checks
