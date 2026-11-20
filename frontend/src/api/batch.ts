// 批次預測 API（POST /predictions/batch、GET /predictions/batch/template）
import { BATCH_TIMEOUT_MS, request } from './client'
import type { components } from './schema.gen'

export type BatchResponse = components['schemas']['BatchResponse']
export type BatchRow = components['schemas']['BatchRow']
export type BatchSummary = components['schemas']['BatchSummary']

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/** 範本 CSV 的下載網址（瀏覽器直接下載，含 BOM 與兩筆範例） */
export const TEMPLATE_URL = `${API_BASE_URL}/predictions/batch/template`
export const TEMPLATE_FILENAME = 'churn_batch_template.csv'

export function predictBatch(file: File): Promise<BatchResponse> {
  const form = new FormData()
  form.append('file', file, file.name)
  // 不手動設定 Content-Type，讓瀏覽器帶上 multipart boundary
  return request<BatchResponse>('/predictions/batch', {
    method: 'POST',
    body: form,
    timeoutMs: BATCH_TIMEOUT_MS,
  })
}
