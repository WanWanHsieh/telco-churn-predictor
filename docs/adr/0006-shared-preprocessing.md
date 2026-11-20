# ADR-0006：訓練與推論共用前處理套件，參數存 JSON

- 狀態：已採用（2026-11-20）

## 非工程背景讀者閱讀版

- 模型訓練時和網站實際預測時，資料必須用「完全相同」的方式整理，否則模型會看到沒學過的格式，預測會悄悄失準，而且不會有任何錯誤訊息。
- 我們把資料整理的程式獨立成一份，訓練和網站都用同一份，並用自動測試確認兩邊產生的資料一模一樣。
- 整理用的參數存成一般文字檔，任何人都能打開檢查，也不需要額外安裝工具。

以下是完整技術內容，供工程團隊實作參考。

## 背景

- training–serving skew（訓練與服務的前處理不一致）是 ML 系統常見且難察覺的錯誤來源。
- 前處理包含：清理（空白字串、整數欄嚴格檢查）、TotalCharges 估算、15 個類別欄 one-hot（41 維）、SeniorCitizen 直通（1 維）、3 個數值欄標準化，共 45 維。

## 選項

| 選項 | 說明 | 問題 |
|---|---|---|
| A. 訓練與 API 各自實作 | 各自最方便 | 極易不一致 |
| B. scikit-learn Pipeline＋pickle | 生態成熟 | backend 需裝 scikit-learn；pickle 有安全疑慮且綁版本 |
| C. 自製 `Preprocessor`，參數存 JSON，獨立成套件 | 可讀、可審查、無 pickle | 需自行實作與測試 |

## 決定

採 C：`core/` 下的 `churn_core` 套件（只依賴 numpy、pandas），`ml/` 與 `backend/` 都 import 它。

- `Preprocessor.fit` 只在訓練子集上擬合；`to_json`／`from_json` 往返後輸出逐位元相同。
- `from_dict` 嚴格比對類別清單、維度配置與目前 schema，不一致即拋錯。
- `backend/tests/test_feature_parity.py` 比對訓練路徑、單筆 API 路徑、批次路徑的特徵向量逐位元相同。

## 後果

- 訓練與推論的差異只可能來自模型本身，不會來自前處理。
- `churn_core` 不依賴 TensorFlow／FastAPI／scikit-learn，可在 CI 快速測試（覆蓋率 99%）。
- 新增特徵時只需改一處，但必須重新訓練並更新 `models/`。
