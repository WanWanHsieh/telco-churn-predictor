import { describe, expect, it } from 'vitest'

import {
  formatImpact,
  formatMetric,
  formatMoney,
  formatPercent,
  formatProbability,
} from '../../domain/format'
import { thresholdText } from '../../domain/risk'

describe('format', () => {
  it('機率顯示 1 位小數（AC-1.2）', () => {
    expect(formatProbability(0.724)).toBe('72.4%')
    expect(formatProbability(0.006)).toBe('0.6%')
    expect(formatProbability(1)).toBe('100.0%')
  })

  it('切點百分比整數不帶小數', () => {
    expect(formatPercent(0.3)).toBe('30%')
    expect(formatPercent(0.255)).toBe('25.5%')
  })

  it('指標 3 位小數', () => {
    expect(formatMetric(0.8374)).toBe('0.837')
  })

  it('影響值轉百分點並帶正負號', () => {
    expect(formatImpact(0.183)).toBe('+18.3')
    expect(formatImpact(-0.05)).toBe('−5.0')
    expect(formatImpact(0)).toBe('0.0')
    expect(formatImpact(0.0004)).toBe('0.0')
  })

  it('金額千分位 2 位小數', () => {
    expect(formatMoney(1234.5)).toBe('$1,234.50')
    expect(formatMoney(0)).toBe('$0.00')
  })

  it('切點說明由 API 切點產生，不寫死', () => {
    const t = { medium: 0.3, high: 0.6 }
    expect(thresholdText('high', t)).toBe('機率 >= 60%')
    expect(thresholdText('medium', t)).toBe('機率 30% 至未滿 60%')
    expect(thresholdText('low', t)).toBe('機率 < 30%')
    expect(thresholdText('low', { medium: 0.25, high: 0.5 })).toBe('機率 < 25%')
  })
})
