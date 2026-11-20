# ADR-0007：Monorepo 與 uv workspace

- 狀態：已採用（2026-11-20）

## 非工程背景讀者閱讀版

- 整個專案（資料整理、模型訓練、後端、前端）放在同一個程式庫，一次就能下載、一次就能測試。
- Python 套件的版本統一記在一份清單裡，開發電腦、自動測試、正式環境安裝的版本完全相同，避免「我的電腦可以跑、別人的不行」。

以下是完整技術內容，供工程團隊實作參考。

## 背景

- `core`、`ml`、`backend` 三個 Python 套件互相依賴（`ml`、`backend` 依賴 `core`）。
- 訓練與推論的 TensorFlow 版本必須完全一致，否則模型檔可能無法載入或行為不同。

## 選項

| 選項 | 說明 | 問題 |
|---|---|---|
| A. 多個 repo | 邊界清楚 | `core` 改動需跨 repo 發版，版本難同步 |
| B. monorepo＋pip／requirements.txt | 熟悉 | 多份 requirements 容易漂移，沒有 workspace 概念 |
| C. monorepo＋uv workspace | 單一 `uv.lock` 鎖定全部成員 | 需要安裝 uv |

## 決定

採 C：根目錄 `pyproject.toml` 宣告 workspace 成員 `core`、`ml`、`backend`，`uv.lock` 鎖定所有依賴；前端獨立以 `package-lock.json` 鎖定。

- 所有 Python 依賴以 `==` 宣告；`[tool.uv]` 設定 `required-version = "==0.10.2"`、`python-downloads = "never"`、`python-preference = "only-system"`。
- `environments` 只解析 Windows AMD64 與 Linux x86_64，避免為用不到的平台卡在預發行版沒有 wheel。
- Docker 與 CI 都以 `uv sync --frozen` 安裝。

## 後果

- Windows `.venv` 與 Linux 容器內的套件版本已驗證完全相同（design.md R11）。
- 一個 PR 可同時修改前處理、訓練與 API，CI 一次驗證。
- 開發者需安裝 uv 0.10.2；README 列出指令。
