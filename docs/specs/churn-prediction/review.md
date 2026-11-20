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
