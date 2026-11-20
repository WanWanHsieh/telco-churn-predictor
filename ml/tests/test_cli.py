import json
import shutil
from pathlib import Path

import pytest

from churn_ml import export
from churn_ml.cli import train_main, verify_main
from churn_ml.pipeline import TrainingResult


def test_train_missing_data_file_prints_friendly_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # AC-4.2
    code = train_main(
        ["--data", str(tmp_path / "missing.csv"), "--output-dir", str(tmp_path / "o")]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "找不到資料檔，請從 Kaggle 下載並放到 data/raw/" in captured.err
    assert "https://www.kaggle.com/datasets/blastchar/telco-customer-churn" in captured.err
    assert "Traceback" not in captured.err + captured.out
    assert not (tmp_path / "o").exists()


def test_train_bad_data_and_bad_arguments_exit_2(
    sample_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.csv"
    broken.write_text("a,b\n1,2\n", encoding="utf-8")
    assert train_main(["--data", str(broken), "--output-dir", str(tmp_path / "o")]) == 2
    assert "資料清理失敗" in capsys.readouterr().err

    assert train_main(["--data", str(sample_csv), "--epochs", "0"]) == 2
    assert "參數錯誤" in capsys.readouterr().err

    with pytest.raises(SystemExit) as info:
        train_main(["--imbalance-strategy", "bogus"])
    assert info.value.code == 2


def test_train_cli_runs_with_class_weight_strategy(
    sample_csv: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # AC-4.1、--imbalance-strategy
    out = tmp_path / "out"
    code = train_main(
        [
            "--data",
            str(sample_csv),
            "--output-dir",
            str(out),
            "--epochs",
            "2",
            "--imbalance-strategy",
            "class_weight",
            "--seed",
            "7",
        ]
    )
    captured = capsys.readouterr().out

    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == sorted(export.ARTIFACT_FILES)
    assert "=== 訓練完成：測試集成效 ===" in captured
    events = [
        json.loads(line)
        for line in captured.splitlines()
        if line.startswith("{") and "event" in line
    ]
    by_event = {e["event"]: e for e in events}
    assert by_event["data_cleaned"]["total_charges_blank"] == 3  # AC-4.3
    assert by_event["training_start"]["seed"] == 7  # AC-4.8
    assert {"ts", "level", "logger", "message"} <= set(by_event["data_cleaned"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 7
    assert manifest["imbalance_strategy"] == "class_weight"


@pytest.fixture
def relaxed_nfr(monkeypatch: pytest.MonkeyPatch) -> None:
    """合成樣本只有約 24 列測試資料，達不到 NFR-1；放寬門檻以測其他檢查。"""
    monkeypatch.setattr(export, "NFR1_MIN_AUC", 0.0)
    monkeypatch.setattr(export, "NFR1_MIN_RECALL", 0.0)
    monkeypatch.setattr(export, "NFR2_MAX_AUC_GAP", 1.0)


def _copy(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def test_verify_passes_on_good_artifacts(
    trained_run: TrainingResult, relaxed_nfr: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = verify_main(["--artifacts", str(trained_run.config.output_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[通過] manifest 雜湊相符" in out
    assert "[通過] NFR-1" in out
    assert "未達標" not in out


@pytest.mark.parametrize(
    ("attr", "value", "label"),
    [
        ("NFR1_MIN_AUC", 1.01, "NFR-1"),
        ("NFR1_MIN_RECALL", 1.01, "NFR-1"),
        ("NFR2_MAX_AUC_GAP", -1.0, "NFR-2"),
    ],
)
def test_verify_fails_when_nfr_not_met(
    trained_run: TrainingResult,
    relaxed_nfr: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    attr: str,
    value: float,
    label: str,
) -> None:
    monkeypatch.setattr(export, attr, value)
    code = verify_main(["--artifacts", str(trained_run.config.output_dir)])
    captured = capsys.readouterr()
    assert code == 1
    assert f"[未達標] {label}" in captured.out
    assert label in captured.err


def test_verify_detects_tampered_file_and_missing_file(
    trained_run: TrainingResult,
    relaxed_nfr: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tampered = _copy(trained_run.config.output_dir, tmp_path / "tampered")
    with (tampered / "explainer.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    assert verify_main(["--artifacts", str(tampered)]) == 1
    assert "[未達標] manifest 雜湊相符：不符：explainer.json" in capsys.readouterr().out

    missing = _copy(trained_run.config.output_dir, tmp_path / "missing")
    (missing / "metrics.json").unlink()
    assert verify_main(["--artifacts", str(missing)]) == 1
    assert "缺少：metrics.json" in capsys.readouterr().out

    assert verify_main(["--artifacts", str(tmp_path / "nonexistent")]) == 1


def test_verify_detects_customer_id_in_features(
    trained_run: TrainingResult,
    relaxed_nfr: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # AC-4.7
    leaked = _copy(trained_run.config.output_dir, tmp_path / "leaked")
    manifest = json.loads((leaked / "manifest.json").read_text(encoding="utf-8"))
    manifest["feature_names"].append("customerID")
    (leaked / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_main(["--artifacts", str(leaked)]) == 1
    assert "[未達標] customerID 不在特徵中" in capsys.readouterr().out


def test_verify_detects_invalid_json_and_bad_metrics_structure(
    trained_run: TrainingResult,
    relaxed_nfr: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken = _copy(trained_run.config.output_dir, tmp_path / "broken")
    (broken / "manifest.json").write_text("{not json", encoding="utf-8")
    assert verify_main(["--artifacts", str(broken)]) == 1
    assert "JSON 可讀" in capsys.readouterr().out

    bad_metrics = _copy(trained_run.config.output_dir, tmp_path / "badmetrics")
    (bad_metrics / "metrics.json").write_text("{}", encoding="utf-8")
    assert verify_main(["--artifacts", str(bad_metrics)]) == 1
    assert "[未達標] metrics.json 結構" in capsys.readouterr().out


def test_verify_compare_checks_auc_difference(
    trained_run: TrainingResult,
    relaxed_nfr: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # AC-4.6
    same = trained_run.config.output_dir
    assert verify_main(["--artifacts", str(same), "--compare", str(same)]) == 0
    assert "差 0.0000" in capsys.readouterr().out

    other = _copy(same, tmp_path / "other")
    metrics = json.loads((other / "metrics.json").read_text(encoding="utf-8"))
    metrics["models"][1]["metrics"]["roc_auc"] = round(
        min(1.0, metrics["models"][1]["metrics"]["roc_auc"] + 0.3)
        if metrics["models"][1]["metrics"]["roc_auc"] < 0.7
        else metrics["models"][1]["metrics"]["roc_auc"] - 0.3,
        4,
    )
    (other / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    assert verify_main(["--artifacts", str(same), "--compare", str(other)]) == 1
    assert "[未達標] AC-4.6" in capsys.readouterr().out

    assert verify_main(["--artifacts", str(same), "--compare", str(tmp_path / "none")]) == 1
    assert "--compare 可讀" in capsys.readouterr().out
