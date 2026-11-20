# 架構決策紀錄（ADR）

每篇記錄一個重要技術決定：背景、考慮過的選項、決定、後果。每篇開頭都有「非工程背景讀者閱讀版」，後面是給工程師的完整內容。數字皆引用 `models/metrics.json`、`models/manifest.json`（2026-11-20 訓練，模型版本 `20261120-fc673697`）。

| 編號 | 主題 | 狀態 |
|---|---|---|
| [0001](0001-model-selection.md) | 模型選擇：Keras MLP 為線上模型、邏輯迴歸為基準 | 已採用 |
| [0002](0002-class-imbalance-and-metrics.md) | 類別不平衡處理、主要指標與決策門檻 | 已採用 |
| [0003](0003-totalcharges-missing-values.md) | TotalCharges 空值與估算規則 | 已採用 |
| [0004](0004-no-database.md) | 不使用資料庫 | 已採用 |
| [0005](0005-explanation-integrated-gradients.md) | 以 Integrated Gradients 解釋單筆預測 | 已採用 |
| [0006](0006-shared-preprocessing.md) | 訓練與推論共用前處理套件，參數存 JSON | 已採用 |
| [0007](0007-monorepo-uv-workspace.md) | Monorepo 與 uv workspace | 已採用 |
| [0008](0008-pinned-course-python-tf-prerelease.md) | 鎖定課程指定的 Python 3.14.8 與 TF／Keras 預發行版 | 已採用 |
