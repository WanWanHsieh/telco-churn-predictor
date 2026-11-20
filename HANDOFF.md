# 交接：telco-churn-predictor

## 目前狀態（2026-11-20）
- 分支：`feat/project-skeleton`（未 push）。最新 commit：成效頁、批次頁、CI、ADR。
- 已完成：T1–T12、T16、T17（tasks.md 打勾）；T13 ci.yml 已寫，待 push 後在 GitHub 實跑確認。
- 單筆預測已從頭到尾跑通：`docker compose up --build` → http://localhost:8080。
- 做法以專案根目錄 `CLAUDE.md` 為準：主對話直接實作、輕量審核、只讀指定規格段落。
- 審核紀錄：`docs/specs/churn-prediction/review.md`（R1–R4）。

## 尚未完成
- T13：push 到 GitHub 後確認三個 job 皆綠（需使用者同意 push）
- T14 整合／效能測試、T15 Playwright E2E、T18 整合審核（使用者尚未決定是否做）

## 重要決定（規格檔外）
- 不可動全域 Python（C:\Program Files\Python314）；一律 `uv run`／專案 `.venv`。版本：Python 3.14.8、tensorflow 2.22.0rc0、keras-nightly 3.16.0.dev2026101704、numpy 2.5.4、pandas 3.0.6、Node 22。
- 改設定檔、安裝或下載套件／映像前要先問使用者。
- commit 用 Conventional Commits，不加 AI 署名。
- backend 映像 3.48 GB（TF 預發行版 2.1 GB），已列入 README 已知限制。

## 給後續任務的提醒
- T13：`frontend/src/__tests__/domain/examples.spec.ts` 讀 core fixture 改用 `new URL(..., import.meta.url)`；CI 用 Linux，`contracts/openapi.json` 的 `--check` 不受 Windows 換行影響。
- T10：成效數字用 `formatMetric`（`toFixed(3)`），與 README 一致。
- 本機若有殘留的 uvicorn 佔用 8000 埠，`docker compose up` 會失敗。
