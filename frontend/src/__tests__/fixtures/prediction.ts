// 測試用的預測回應（結構同 design.md 6.5.3）
import type { PredictionResponse } from '../../api/predictions'

export function makePrediction(overrides: Partial<PredictionResponse> = {}): PredictionResponse {
  return {
    probability: 0.724,
    risk_level: 'high',
    risk_thresholds: { medium: 0.3, high: 0.6 },
    model: {
      name: 'keras_mlp',
      display_name: 'Keras 神經網路',
      version: '20261120-a1b2c3d4',
      trained_at: '2026-11-20T08:00:00Z',
    },
    total_charges: { value: 1234.5, is_estimated: true },
    top_factors: [
      { feature: 'Contract', label: '合約類型：月繳', direction: 'increase', impact: 0.183 },
      { feature: 'tenure', label: '在網月數：1 個月', direction: 'increase', impact: 0.142 },
      {
        feature: 'OnlineSecurity',
        label: '網路安全服務：有',
        direction: 'decrease',
        impact: -0.095,
      },
      {
        feature: 'PaymentMethod',
        label: '付款方式：電子支票',
        direction: 'increase',
        impact: 0.061,
      },
      { feature: 'TechSupport', label: '技術支援服務：無', direction: 'increase', impact: 0.033 },
    ],
    explanation: { method: 'integrated_gradients', baseline_probability: 0.231 },
    ...overrides,
  }
}

/** 建立 fetch 的假回應 */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-test' },
  })
}
