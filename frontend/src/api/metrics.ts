// 模型成效 API（GET /model/metrics）
import { request } from './client'
import type { components } from './schema.gen'

export type MetricsResponse = components['schemas']['MetricsResponse']
export type ModelResult = components['schemas']['ModelResult']
export type ModelMetrics = components['schemas']['ModelMetrics']
export type ConfusionMatrixData = components['schemas']['ConfusionMatrix']
export type DatasetInfo = components['schemas']['DatasetInfo']
export type ImbalanceExperimentRow = components['schemas']['ImbalanceExperimentRow']

export function getMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>('/model/metrics')
}
