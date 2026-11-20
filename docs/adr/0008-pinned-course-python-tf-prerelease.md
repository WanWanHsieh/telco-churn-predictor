# ADR-0008：鎖定課程指定的 Python 3.14.8 與 TF／Keras 預發行版

- 狀態：已採用（2026-11-20）

## 非工程背景讀者閱讀版

- 開發電腦上的 Python 與 TensorFlow 是課程老師確認過的版本，專案刻意沿用，不升級也不降級，確保和上課環境一致。
- 專案另外建立獨立環境安裝相同版本，不會動到電腦原本的設定。
- 風險：TensorFlow 用的是「預發行版」（正式版之前的測試版本），未來可能被下架；目前所有版本都已鎖定並驗證，且只確認在 Windows 和 Linux 上可用。

以下是完整技術內容，供工程團隊實作參考。

## 背景

- 開發環境（全域 `C:\Program Files\Python314`）：Python 3.14.8、tensorflow 2.22.0rc0、keras-nightly 3.16.0.dev2026101704、numpy 2.5.4、pandas 3.0.6。
- 使用者要求不得修改全域環境，也不得更動版本。
- tensorflow 2.22.0rc0 依賴的套件名稱是 `keras-nightly`（不是 `keras`），已唯讀確認沒有命名衝突。

## 選項

| 選項 | 說明 | 問題 |
|---|---|---|
| A. 改用 Python 3.12＋TF 穩定版 | 社群支援廣 | 與課程環境不同，需另外下載直譯器 |
| B. 沿用課程版本並以 `==` 鎖定 | 與上課環境一致 | 預發行版的可用性與長期支援有風險 |

## 決定

採 B：

- 專案 `.venv` 以 `uv venv --python "C:\Program Files\Python314\python.exe"` 建立；uv 設定禁止下載直譯器。
- 核心套件以 `==` 鎖定上述版本；新套件（scikit-learn 1.9.1、fastapi 0.165.0 等）選與之相容的版本並鎖定，完整清單見 design.md 3.2.1。
- 前端 TypeScript 取 5.9.3：typescript-eslint 8.73.0 要求 < 6.1.0，openapi-typescript 7.13.0 要求 ^5.x。
- Docker 基底映像為 `python:3.14.8-slim-trixie`；`ml/tests/test_smoke.py` 斷言執行環境的 Python 與四個核心套件版本完全相同，CI 與容器內都會執行。

驗證結果（T1）：

- 全域 `pip freeze` 前後完全相同；uv 未下載任何直譯器。
- Windows `.venv` 與 Linux 容器內的 tensorflow、keras-nightly、numpy、pandas 版本完全相同。
- `tf.__version__` 顯示為 `2.22.0-rc0`，與發行版本 `2.22.0rc0` 等價。

## 後果

- 與課程環境完全一致，模型檔可在上課環境直接載入。
- backend 映像約 3.48 GB，其中 tensorflow 套件本身約 2.1 GB。
- 只驗證 Windows x86_64 與 Linux x86_64；macOS／ARM 不支援（design.md R8）。
- 預發行版若被 PyPI 撤下，`uv sync --frozen` 會失敗，屆時需重新評估版本（design.md R11）。
