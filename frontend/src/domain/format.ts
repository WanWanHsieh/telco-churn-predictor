// 畫面數字格式（ui.md 3.4、4.x）：機率 1 位、指標 3 位、影響值百分點、金額。

/** 0.724 → "72.4%" */
export function formatProbability(p: number): string {
  return `${(p * 100).toFixed(1)}%`
}

/** 切點用：0.3 → "30%"（整數不顯示小數） */
export function formatPercent(p: number): string {
  const value = Math.round(p * 1000) / 10
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)}%`
}

/** 成效指標：0.83740 → "0.837" */
export function formatMetric(x: number): string {
  return x.toFixed(3)
}

/** 機率影響值（帶正負號）轉百分點：0.183 → "+18.3"、-0.05 → "−5.0" */
export function formatImpact(impact: number): string {
  const points = Math.abs(impact * 100).toFixed(1)
  if (points === '0.0') return '0.0'
  return `${impact > 0 ? '+' : '−'}${points}`
}

/** 金額：1234.5 → "$1,234.50" */
export function formatMoney(amount: number): string {
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
