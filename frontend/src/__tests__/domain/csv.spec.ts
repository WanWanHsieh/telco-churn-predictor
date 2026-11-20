import { describe, expect, it } from 'vitest'

import { buildResultCsv, escapeCell } from '../../domain/csv'
import { FEATURE_NAMES } from '../../domain/fields'
import { makeBatch, makeRow } from '../fixtures/batch'

describe('結果 CSV（AC-6.4）', () => {
  const batch = makeBatch([makeRow(2, 0.739, 'high'), makeRow(3, 0.12, 'low', 'A,"B"')])
  const csv = buildResultCsv(batch)
  const lines = csv.slice(1).split('\r\n').filter(Boolean)

  it('開頭為 UTF-8 BOM，使用 CRLF', () => {
    expect(csv.charCodeAt(0)).toBe(0xfeff)
    expect(csv).toContain('\r\n')
    expect(csv.replaceAll('\r\n', '')).not.toContain('\n')
  })

  it('表頭含 customerID＋19 欄＋結果欄，筆數一致', () => {
    expect(lines[0]).toBe(
      ['customerID', ...FEATURE_NAMES, '流失機率', '風險等級', '累計費用為估算'].join(','),
    )
    expect(lines).toHaveLength(1 + batch.results.length)
    expect(lines[1]?.endsWith(',73.9%,高風險,是')).toBe(true)
  })

  it('RFC 4180 引號：含逗號或雙引號的值加引號並重複雙引號', () => {
    expect(lines[2]?.startsWith('"A,""B""",')).toBe(true)
    expect(escapeCell('a\nb')).toBe('"a\nb"')
    expect(escapeCell(null)).toBe('')
    expect(escapeCell(12)).toBe('12')
  })

  it('防公式注入：= + - @ 開頭的字串加上單引號，數字不受影響', () => {
    expect(escapeCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`)
    expect(escapeCell('+886')).toBe("'+886")
    expect(escapeCell('@SUM(A1)')).toBe("'@SUM(A1)")
    expect(escapeCell(-3)).toBe('-3')
    expect(escapeCell('Month-to-month')).toBe('Month-to-month')
  })

  it('沒有 customerID 欄時不輸出該欄', () => {
    const noId = buildResultCsv(makeBatch([makeRow(2, 0.5, 'medium', null)], false))
    expect(noId.slice(1).startsWith('gender,')).toBe(true)
  })
})
