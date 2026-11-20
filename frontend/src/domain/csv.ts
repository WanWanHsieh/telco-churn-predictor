// 批次結果 CSV（AC-6.4，design.md 6.5.5）：customerID＋19 欄＋流失機率＋風險等級＋累計費用為估算；
// UTF-8 BOM（Excel 不亂碼）、CRLF、RFC 4180 引號
import type { BatchResponse } from '../api/batch'
import { FEATURE_NAMES } from './fields'
import { formatProbability } from './format'
import { RISK_META } from './risk'

const BOM = '﻿'

/** RFC 4180：含逗號、雙引號、換行時加引號，內部雙引號重複一次 */
export function escapeCell(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined) return ''
  let text = String(value)
  // 防 CSV 公式注入：使用者上傳的字串若以 = + - @ 開頭，Excel 會當成公式執行；數字不處理
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function buildResultCsv(response: BatchResponse): string {
  const header = [
    ...(response.has_customer_id ? ['customerID'] : []),
    ...FEATURE_NAMES,
    '流失機率',
    '風險等級',
    '累計費用為估算',
  ]
  const lines = response.results.map((row) => {
    const input = row.input as Record<string, string | number | null | undefined>
    return [
      ...(response.has_customer_id ? [row.customer_id] : []),
      ...FEATURE_NAMES.map((name) => input[name]),
      formatProbability(row.probability),
      RISK_META[row.risk_level].label,
      row.total_charges_estimated ? '是' : '否',
    ]
      .map(escapeCell)
      .join(',')
  })
  return BOM + [header.join(','), ...lines].join('\r\n') + '\r\n'
}

/** 觸發瀏覽器下載（不經伺服器） */
export function downloadText(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
