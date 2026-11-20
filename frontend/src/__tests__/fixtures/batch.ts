// 測試用的批次預測回應（結構同 design.md 6.5.5）
import type { BatchResponse, BatchRow } from '../../api/batch'
import type { RiskLevel } from '../../api/predictions'
import { getExample } from '../../domain/examples'

export function makeRow(
  row: number,
  probability: number,
  riskLevel: RiskLevel,
  customerId: string | null = `C-${row}`,
): BatchRow {
  return {
    row,
    customer_id: customerId,
    probability,
    risk_level: riskLevel,
    total_charges_estimated: row % 2 === 0,
    input: { ...getExample('high'), TotalCharges: null } as unknown as BatchRow['input'],
  }
}

export function makeBatch(rows: BatchRow[], hasCustomerId = true): BatchResponse {
  const count = (level: RiskLevel) => rows.filter((r) => r.risk_level === level).length
  return {
    summary: {
      total: rows.length,
      high: count('high'),
      medium: count('medium'),
      low: count('low'),
      estimated_total_charges: rows.filter((r) => r.total_charges_estimated).length,
    },
    risk_thresholds: { medium: 0.3, high: 0.6 },
    model: {
      name: 'keras_mlp',
      display_name: 'Keras 神經網路',
      version: '20261120-a1b2c3d4',
      trained_at: '2026-11-20T08:00:00Z',
    },
    has_customer_id: hasCustomerId,
    ignored_columns: [],
    results: rows,
  }
}
