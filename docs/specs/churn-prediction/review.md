# 審核紀錄：churn-prediction

## R1：T2 共用核心＋T8 前端外殼與表單（2026-11-20）

- 審核等級：完整（opus）。理由：T2 是新的商業邏輯（清理、TotalCharges 估算、前處理），且訓練與推論共用，錯誤會造成 training-serving skew。
- 結果：第一輪「修完再合併」，複查後「可以合併」。

### 第一輪：必須修（已修）
| # | 問題 | 位置 | 狀態 |
|---|---|---|---|
| 1 | 錯誤修到 0 個後，摘要仍顯示「有 0 個欄位需要修正」 | `frontend/src/stores/prediction.ts` `setValue` | ✅ 已修，補測試 |

### 第一輪：建議修（已修）
| # | 問題 | 狀態 |
|---|---|---|
| 1 | `cleaning.py` 以 `astype("int64")` 截斷非整數（吞錯） | ✅ 改 `_strict_int` 拋錯 |
| 2 | `labels.py` 拒絕 `np.int64` 等 numpy 型別 | ✅ 改 `numbers.Integral/Real` |
| 3 | 範例為可變全域 dict | ✅ 改 `MappingProxyType` |
| 4 | `_self_check` 用 `assert` | ✅ 改 `RuntimeError` |
| 5 | 前端範例只比對 7 欄 | ✅ 19 欄完整比對＋讀 core fixture |
| 6 | `aria-describedby` 未涵蓋說明與錯誤訊息 | ✅ 已補 |
| 7 | Esc 收合選單後焦點未回漢堡按鈕 | ✅ 已補 |
| 8 | `NAV_ITEMS` 註解與實作不符 | ✅ 改由 routes 推導 |
| 9 | 測試註解簡體字 | ✅ 已改 |

### 第一輪：規格待確認（使用者已決定）
1. 估算值 > 10,000 → 驗證錯誤（API 422、前端提示「估算累計費用超過上限，請手動填寫」）。
2. 手填與估算值一律 Decimal half-up 到 2 位後才用於預測。
- 已更新 design.md 6.2／6.5.3、requirements.md AC-1.7、1.16、1.17（新增）、6.13。

### 複查：建議修（不擋合併，留待後續）
1. `schema._estimate_errors` 改直接呼叫純 Decimal 的 `estimate_total_charges`；可考慮把金額函式抽成不依賴 pandas 的 `money.py`，消除函式內延遲 import。（T7 逐列驗證效能相關）
2. `PredictForm.vue` 的 `syncDescribedBy` 可改成自訂指令，作用範圍限單一欄位。
3. `examples.spec.ts` 讀 core fixture 改用 `new URL(..., import.meta.url)`，不依賴 `process.cwd()`。（T13 CI 前處理）
4. `MappingProxyType` 範例不能直接 `json.dumps`，T7 範本、T12 冒煙測試需先 `dict(...)`。（派工時提醒）
5. design.md 6.2 補一句「乘法以 Decimal 精確計算」，與實作一致。
6. 日後加 404／萬用路由時，`NAV_ITEMS` 需加過濾條件（如 `meta.nav`）。

### 複查驗證重點
- 前端 `Math.round` 與後端 half-up：窮舉 tenure 0–72 × MonthlyCharges 0.00–200.00（146 萬組）0 筆不一致。
- 主管重跑：core 136 passed（覆蓋率 99.04%）；frontend lint／type-check／format／84 tests 通過。

## R2：T3 訓練管線＋T5 後端基礎層（2026-11-20）

- 審核等級：完整（opus）。理由：T3 為新的 ML 商業邏輯；T5 涉及錯誤碼合約、環境設定、CORS、log。
- 結果：可以合併，無必須修。
- 主管另行處理：補 `core/src/churn_core/py.typed`，移除 ml／backend 共 12 個 `# type: ignore[import-untyped]`；全部 pytest 311 passed、mypy／ruff 全專案通過。

### 重點驗證
- 資料洩漏：無（前處理只 fit 訓練子集、門檻只用驗證集、測試集只做評估）。
- 可重現性：合成資料兩個獨立行程訓練結果完全相同。
- T3 產物 → T5 `load_artifacts`：手動端到端載入成功，格式一致。
- T5：錯誤回應不洩漏堆疊／路徑；CORS 白名單且不給 credentials；X-Request-ID 白名單字元；log 不記輸入值。

### 建議修（T4 前處理第 1、2 項）
| # | 問題 | 位置 | 主管確認 |
|---|---|---|---|
| 1 | churn-verify 用四捨五入到 4 位後的值判斷 NFR，AUC 0.81996 會被誤判通過 | `ml/src/churn_ml/export.py:137-151`、`evaluate.py:129` | ✅ 已讀程式確認 |
| 2 | 傳絕對路徑時 manifest 會記本機完整路徑（含 Windows 使用者名稱），manifest 進版控會公開 | `ml/src/churn_ml/config.py:42-47` | ✅ 已讀程式確認 |
| 3 | 缺「T3 實際產物 → T5 載入」自動化測試 | T6 `test_feature_parity` 或 T14 | — |
| 4a | `reproducibility.py` 的 TF 環境變數在 `import keras` 之後才設定，來不及生效 | `ml/src/churn_ml/models.py:7` | — |
| 4b | inference 層 import `schemas.common.ModelInfo`，違反 design 1.3 分層 | `backend/src/churn_api/inference/artifacts.py:26` | — |
| 4c | middleware 產生的 500 未經 CORS；log path 為 None | `backend/src/churn_api/middleware.py:73-75` | — |
| 4d | `manifest.files` 非 dict 時 verify 崩潰 | `ml/src/churn_ml/export.py:117` | — |
| 4e | ROC 降採樣遇 fpr 重複值取值不精確（只影響畫面） | `ml/src/churn_ml/evaluate.py:165` | — |

### 給 T6 的提醒
- Pydantic `Literal[0,1]` 會接受 JSON `true` 與 `1.0`（strict 模式也接受 `true`）；`tenure: int` 會接受 `10.0`。SeniorCitizen、tenure 須用 `StrictInt`＋範圍，並補 `true`、`1.0`、`10.0` 的 422 測試。

### R2 複查（2026-11-20）
- 結果：可以合併，無必須修。建議修 1、2、4a–4e 均已修正。
- ml：NFR 判斷改用 manifest 的 `unrounded_metrics`（metrics.json 結構不變），0.81996 判未達標；manifest 只記檔名；環境變數移至 `churn_ml/__init__.py`；`files` 非 dict 判未達標；ROC 降採樣改自行內插並保留全部原始點。
- backend：inference 改回傳 `ModelDescriptor`；例外攔截拆為 `UnhandledExceptionMiddleware` 置於 CORS 內側，跨來源 500 帶正確 CORS 標頭與 X-Request-ID，log path 正確。
- 複查唯一建議（註解不精確）已由主管修正。
- 主管驗證：全專案 pytest 321 passed，mypy 34 檔、ruff check／format 全過。
- 已知且保留：TF 啟動時的 oneDNN 說明訊息（關閉需 `TF_ENABLE_ONEDNN_OPTS=0`，會改變數值運算與可重現性）。

## R3：T6＋T7 後端 API、T9 前端串接（2026-11-20）

- 審核等級：輕量（專案 CLAUDE.md：作品集專案一律輕量審核）。
- 結果：可以合併。
- 必須修（已修）：`csv_parser._convert` 對超長整數字面值呼叫 `int()` 觸發位數上限而回 500 → `_INT_PATTERN` 限 1–9 位，補回歸測試。
- 已採納的建議：`stores/prediction.submit` 進行中不重複送出；`api/client` 讀取本體也受逾時保護。
- 保留不處理：csv 一次讀入記憶體（5 MB 上限內可接受）、impact 四捨五入為 0.0 時的方向（前端顯示「0.0」）、`+10`／`010` 字面值、422 對不到欄位時顯示服務錯誤框、後端 422 後未移動焦點、`role="alert"` 與 `aria-live` 可能重複朗讀。
- 主管實測：uvicorn＋vite 以正式模型在瀏覽器預測高風險範例 → 73.9% 高風險、5 個因素、估算註記正確、無橫向捲動。

## R4：T12 Docker＋T17 README（2026-11-20）

- 審核等級：輕量。結果：可以合併，無必須修。
- 已採納建議：README 成效數字改用 metrics.json 4 位值經 `toFixed(3)`（LR AUC 0.843、Keras Precision 0.516，與成效頁一致）；`uv venv` 路徑註明依平台替換；nginx `/assets/` 補齊安全標頭；backend 埠只綁 127.0.0.1；README 註明 Swagger UI 需連網。
- 主管驗證：compose up 約 9 秒 healthy；預測、/docs、SPA fallback 正常；兩容器非 root；容器內版本與 design 3.2.1 相同；MODEL_DIR 指向不存在目錄時 health 503、meta 200（以此取代「移走模型檔重建」，因 `COPY models/` 需要目錄存在）。
- 映像大小：backend 3.48 GB（tensorflow 預發行版 2.1 GB，超出 design 預估 1.3–1.6 GB）、frontend 92 MB。

## R5：T10 成效頁、T11 批次頁、T13 CI、T16 ADR、README（2026-11-20）

- 審核等級：輕量。結果：修正後可以合併。
- 必須修（已修）：結果 CSV 欄名與格式不符 design 6.5.5 → 表頭改為「流失機率／風險等級／累計費用為估算」，機率改為百分比 1 位（如 `73.9%`），測試同步更新。
- 已採納建議：CSV 公式注入防護（字串以 `= + - @` 開頭時加前綴 `'`，數字不受影響）；成效頁「固定 0.5」改為具名常數並註明為概念說明。
- 主管實測：Docker 重建後以 Edge 檢查成效頁與批次頁（上傳範本 2 筆 → 高 1、低 1），1280／375 無橫向捲動、console 無錯誤；修正成效頁「（基準）（基準）」重複字樣。
- 未驗證：ci.yml 尚未在 GitHub 實跑（需使用者同意 push）；`setup-python` 能否取得 3.14.8 待實跑確認。
