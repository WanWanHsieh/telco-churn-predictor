// 風險等級的顯示資訊（ui.md 3.4 風險等級視覺表）；切點文字一律由 API 回傳的切點產生。
import type { RiskLevel, RiskThresholds } from '../api/predictions'
import { formatPercent } from './format'

export interface RiskMeta {
  label: string
  icon: string
}

export const RISK_META: Record<RiskLevel, RiskMeta> = {
  low: { label: '低風險', icon: '▼' },
  medium: { label: '中風險', icon: '◆' },
  high: { label: '高風險', icon: '▲' },
}

/** 例：高 → "機率 >= 60%"；中 → "機率 30% 至未滿 60%"；低 → "機率 < 30%" */
export function thresholdText(level: RiskLevel, t: RiskThresholds): string {
  const medium = formatPercent(t.medium)
  const high = formatPercent(t.high)
  if (level === 'high') return `機率 >= ${high}`
  if (level === 'medium') return `機率 ${medium} 至未滿 ${high}`
  return `機率 < ${medium}`
}
