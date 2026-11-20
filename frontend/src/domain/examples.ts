// 載入範例（design.md 6.7；須與 churn_core/examples.py 一致）。
import type { FormValues } from './fields'

export const HIGH_RISK_EXAMPLE: Readonly<FormValues> = Object.freeze({
  gender: 'Female',
  SeniorCitizen: 0,
  Partner: 'No',
  Dependents: 'No',
  tenure: 1,
  PhoneService: 'Yes',
  MultipleLines: 'No',
  InternetService: 'Fiber optic',
  OnlineSecurity: 'No',
  OnlineBackup: 'No',
  DeviceProtection: 'No',
  TechSupport: 'No',
  StreamingTV: 'Yes',
  StreamingMovies: 'Yes',
  Contract: 'Month-to-month',
  PaperlessBilling: 'Yes',
  PaymentMethod: 'Electronic check',
  MonthlyCharges: 100,
  TotalCharges: null, // 留空，交由系統估算
})

export const LOW_RISK_EXAMPLE: Readonly<FormValues> = Object.freeze({
  gender: 'Male',
  SeniorCitizen: 0,
  Partner: 'Yes',
  Dependents: 'Yes',
  tenure: 70,
  PhoneService: 'Yes',
  MultipleLines: 'Yes',
  InternetService: 'No',
  OnlineSecurity: 'No internet service',
  OnlineBackup: 'No internet service',
  DeviceProtection: 'No internet service',
  TechSupport: 'No internet service',
  StreamingTV: 'No internet service',
  StreamingMovies: 'No internet service',
  Contract: 'Two year',
  PaperlessBilling: 'No',
  PaymentMethod: 'Credit card (automatic)',
  MonthlyCharges: 30,
  TotalCharges: 2100,
})

export type ExampleKind = 'high' | 'low'

export function getExample(kind: ExampleKind): FormValues {
  return { ...(kind === 'high' ? HIGH_RISK_EXAMPLE : LOW_RISK_EXAMPLE) }
}
