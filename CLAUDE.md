# telco-churn-predictor

## 專案定位
作品集等級的流失預測網頁。模型已定案（Keras MLP，AUC 約 0.84），不再調模型。

## 做法（覆寫全域團隊流程）
- 主對話直接實作，不派 pm／architect／designer；完成一個段落才派一次 reviewer（輕量審核）。
- 規格以 docs/specs/churn-prediction/ 為準，但不再擴寫；新決定只在 tasks.md 補一行。
- 派工或自己讀規格時，只讀該任務指定的段落，不整份讀。

## 優先順序
1. T6＋T9：單筆預測從頭到尾跑通（最優先）
2. T12 Docker、T17 README
3. 其餘（T7、T10、T13～T16、T18）跑通後再跟使用者確認要不要做

## 省 token
- 訓練與測試輸出只看最後摘要；完整 log 寫檔，需要時再看最後幾行。
- 不讀 data/ 原始 CSV、.tmp/、models/*.keras。
