// 單筆預測 API（POST /predictions）
import type { FormValues } from '../domain/fields'
import { postJson } from './client'
import type { components } from './schema.gen'

export type PredictionResponse = components['schemas']['PredictionResponse']
export type Factor = components['schemas']['Factor']
export type RiskLevel = PredictionResponse['risk_level']
export type RiskThresholds = components['schemas']['RiskThresholds']

/** 送出前移除空白的選填欄位（TotalCharges 留空 → 不帶，由後端估算） */
export function toRequestBody(values: FormValues): Record<string, string | number> {
  const body: Record<string, string | number> = {}
  for (const [name, value] of Object.entries(values)) {
    if (value !== null && value !== '') body[name] = value
  }
  return body
}

export function predict(values: FormValues): Promise<PredictionResponse> {
  return postJson<PredictionResponse>('/predictions', toRequestBody(values))
}
