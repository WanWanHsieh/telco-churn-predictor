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
