// 系統資訊 API（GET /meta）：批次上限等畫面文案用的數值
import { request } from './client'
import type { components } from './schema.gen'

export type MetaResponse = components['schemas']['MetaResponse']
export type BatchLimits = components['schemas']['BatchLimits']

export function getMeta(): Promise<MetaResponse> {
  return request<MetaResponse>('/meta')
}

/** 5242880 → "5 MB" */
export function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024)
  return `${Number.isInteger(mb) ? mb : mb.toFixed(1)} MB`
}
