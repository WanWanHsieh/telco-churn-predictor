import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PAGE_SIZE, useBatchStore } from '../../stores/batch'
import { makeBatch, makeRow } from '../fixtures/batch'
import { jsonResponse } from '../fixtures/prediction'

const csvFile = () => new File(['a,b\n1,2\n'], 'list.csv', { type: 'text/csv' })

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

async function loaded(
  rows = [
    makeRow(2, 0.2, 'low'),
    makeRow(3, 0.9, 'high'),
    makeRow(4, 0.45, 'medium'),
    makeRow(5, 0.9, 'high'),
  ],
) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(makeBatch(rows))))
  const store = useBatchStore()
  store.selectFile(csvFile())
  await store.submit()
  return store
}

describe('batch store', () => {
  it('非 .csv 檔由前端先擋下', () => {
    const store = useBatchStore()
    store.selectFile(new File(['x'], 'list.xlsx'))
    expect(store.file).toBeNull()
    expect(store.fileError).toBe('not_csv')
  })

  it('成功後進入結果階段，預設依機率降冪，同值依列號（AC-6.2）', async () => {
    const store = await loaded()
    expect(store.stage).toBe('result')
    expect(store.sortedRows.map((r) => r.row)).toEqual([3, 5, 4, 2])
  })

  it('篩選與排序即時生效（AC-6.3）', async () => {
    const store = await loaded()
    store.setFilter('high')
    expect(store.sortedRows.map((r) => r.row)).toEqual([3, 5])
    store.setFilter('all')
    store.setSort('probability', 'ascending')
    expect(store.sortedRows.map((r) => r.row)).toEqual([2, 4, 3, 5])
    store.setSort('risk_level', 'descending')
    expect(store.sortedRows[0]?.risk_level).toBe('high')
    expect(store.sortedRows.at(-1)?.risk_level).toBe('low')
  })

  it('分頁每頁 20 筆，篩選後回到第 1 頁', async () => {
    const rows = Array.from({ length: 45 }, (_, i) => makeRow(i + 2, (i % 10) / 10, 'low'))
    const store = await loaded(rows)
    expect(store.pagedRows).toHaveLength(PAGE_SIZE)
    store.page = 3
    expect(store.pagedRows).toHaveLength(5)
    store.setFilter('low')
    expect(store.page).toBe(1)
  })

  it('API 錯誤時回到上傳階段並保留檔案，不顯示結果（AC-6.7）', async () => {
    const body = {
      error: {
        code: 'INVALID_ROWS',
        message: 'x',
        details: [{ field: 'tenure', row: 7, type: 'out_of_range', reason: 'tenure 需為 0 至 72' }],
        meta: { total_errors: 25, invalid_row_count: 12 },
        request_id: 'r',
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, 422)))
    const store = useBatchStore()
    store.selectFile(csvFile())
    await store.submit()
    expect(store.stage).toBe('upload')
    expect(store.response).toBeNull()
    expect(store.file?.name).toBe('list.csv')
    expect(store.error?.code).toBe('INVALID_ROWS')
    expect(store.error?.metaNumber('total_errors')).toBe(25)
  })
})
