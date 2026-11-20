# 交接：telco-churn-predictor

## 目前狀態（2026-11-20）
- 分支：`feat/project-skeleton`（未 push）
- commit：`35c68dc` T1 骨架、`7b0995c` T2 core＋T8 前端表單＋規格更新
- tasks.md：T1、T2、T8 已完成打勾，其餘 15 個未開始
- 規格以 `docs/specs/churn-prediction/` 為準：requirements.md、ui.md、design.md、tasks.md、review.md

## 下一步
- 依 tasks.md 相依圖：T3（ml 訓練，backend-dev）∥ T5（backend 骨架，backend-dev）可開工；T9 需 T6＋T8
- 派工前先跟使用者確認角色與審核等級

## 已確認的重要決定（規格檔外的補充）
- 環境：沿用使用者上課版本，**不可動全域 Python**（C:\Program Files\Python314）。Python 3.14.8、tensorflow 2.22.0rc0、keras-nightly 3.16.0.dev2026101704、numpy 2.5.4、pandas 3.0.6、Node 22，一律 `uv run`／專案 `.venv`
- 改設定檔（vitest/vite/tsconfig/pyproject 等）與安裝套件前要先問使用者
- UI：Element Plus；不用 `@` 路徑別名（未裝 @types/node）
- commit message 用 Conventional Commits，不加 AI 署名
- Docker Desktop 需使用者手動啟動

## 派工時要提醒（來自 review.md 複查建議）
- T7、T12：`churn_core.examples` 是 MappingProxyType，轉 JSON 前先 `dict(...)`
- T7：批次逐列驗證效能，考慮把金額函式抽成 `money.py`
- T13：`frontend/src/__tests__/domain/examples.spec.ts` 讀 core fixture 改用 `new URL(..., import.meta.url)`
- design.md 6.2 補「乘法以 Decimal 精確計算」

## 子代理用量
- 本 session 已派 8 個（pm、designer、architect、devops、backend-dev、frontend-dev、reviewer 等），新 session 重新計算
