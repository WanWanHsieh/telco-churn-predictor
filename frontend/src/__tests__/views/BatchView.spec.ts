import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TEMPLATE_URL } from '../../api/batch'
import { useBatchStore } from '../../stores/batch'
import BatchView from '../../views/BatchView.vue'
import { makeBatch, makeRow } from '../fixtures/batch'
import { jsonResponse } from '../fixtures/prediction'

let wrapper: VueWrapper
const meta = { batch_limits: { max_file_bytes: 5242880, max_rows: 10000 } }

function errorResponse(code: string, status: number, extra: Record<string, unknown> = {}) {
  return jsonResponse(
    { error: { code, message: 'x', details: [], meta: null, request_id: 'r', ...extra } },
    status,
  )
}

/** fetch 替身：/meta 回上限，其餘交給 batchResponse */
function stubFetch(batchResponse: () => Promise<Response>) {
  const fn = vi.fn((url: string) =>
    url.endsWith('/meta') ? Promise.resolve(jsonResponse(meta)) : batchResponse(),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

async function mountWithFile() {
  const pinia = createPinia()
  setActivePinia(pinia)
  wrapper = mount(BatchView, { global: { plugins: [pinia] } })
  await flushPromises()
  const store = useBatchStore()
  store.selectFile(new File(['a\n1\n'], 'list.csv', { type: 'text/csv' }))
  await flushPromises()
  return store
}

function button(text: string) {
  return wrapper.findAll('button').find((b) => b.text().includes(text))
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

describe('BatchView', () => {
  it('可下載範本、顯示上限與隱私註記（AC-6.1、6.8、6.11）', async () => {
    stubFetch(() => new Promise(() => {}))
    await mountWithFile()
    const link = wrapper.find(`a[href="${TEMPLATE_URL}"]`)
    expect(link.exists()).toBe(true)
    expect(link.attributes('download')).toBe('churn_batch_template.csv')
    expect(wrapper.text()).toContain('上限 5 MB 或 10,000 列')
    expect(wrapper.text()).toContain('上傳的內容不會被儲存')
  })

  it('處理中按鈕 loading 且 disabled，上傳區 disabled（AC-6.10）', async () => {
    stubFetch(() => new Promise(() => {}))
    await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    const submit = button('預測中')
    expect(submit?.attributes('disabled')).toBeDefined()
    expect(submit?.classes()).toContain('is-loading')
    expect(wrapper.find('.el-upload').classes()).toContain('is-disabled')
  })

  it('成功後顯示摘要 4 卡、表格含 customerID 且預設依機率降冪（AC-6.2、6.5）', async () => {
    const rows = [makeRow(2, 0.2, 'low'), makeRow(3, 0.9, 'high'), makeRow(4, 0.45, 'medium')]
    stubFetch(() => Promise.resolve(jsonResponse(makeBatch(rows))))
    await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.batch-summary__card')).toHaveLength(4)
    expect(wrapper.find('[data-card="high"]').text()).toContain('1 筆')
    expect(wrapper.find('thead').text()).toContain('customerID')
    expect(wrapper.findAll('tbody tr').map((tr) => tr.attributes('data-row'))).toEqual([
      '3',
      '4',
      '2',
    ])
  })

  it('沒有 customerID 欄時不顯示該欄', async () => {
    stubFetch(() =>
      Promise.resolve(jsonResponse(makeBatch([makeRow(2, 0.5, 'medium', null)], false))),
    )
    await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    expect(wrapper.find('thead').text()).not.toContain('customerID')
  })

  it('篩選無資料顯示空狀態，可清除篩選（AC-6.3）', async () => {
    stubFetch(() => Promise.resolve(jsonResponse(makeBatch([makeRow(2, 0.1, 'low')]))))
    const store = await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    store.setFilter('high')
    await flushPromises()
    expect(wrapper.find('[data-testid="filter-empty"]').text()).toContain(
      '沒有符合「高風險」的顧客',
    )
    await button('清除篩選')?.trigger('click')
    expect(store.filter).toBe('all')
  })

  it.each([
    [
      'MISSING_COLUMNS',
      422,
      {
        details: [
          { field: 'Contract', row: null, type: 'missing_column', reason: 'x' },
          { field: 'tenure', row: null, type: 'missing_column', reason: 'x' },
        ],
      },
      '缺少欄位：Contract、tenure',
    ],
    ['FILE_TOO_LARGE', 413, {}, '檔案超過上限'],
    ['TOO_MANY_ROWS', 413, {}, '檔案超過上限'],
    ['UNSUPPORTED_FILE_TYPE', 415, {}, '這不是有效的 CSV 檔案'],
    ['FILE_EMPTY', 400, {}, '這不是有效的 CSV 檔案'],
    ['MODEL_UNAVAILABLE', 503, {}, '服務暫時無法使用'],
  ])('%s 顯示對應訊息且不顯示結果（AC-6.6、6.8）', async (code, status, extra, expected) => {
    stubFetch(() => Promise.resolve(errorResponse(code, status, extra)))
    await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="batch-errors"]').text()).toContain(expected)
    expect(wrapper.find('.batch-summary').exists()).toBe(false)
  })

  it('資料列錯誤列出前 20 筆並顯示「另有 N 筆」（AC-6.7）', async () => {
    const details = Array.from({ length: 20 }, (_, i) => ({
      field: 'tenure',
      row: i + 2,
      type: 'out_of_range',
      reason: `第 ${i + 2} 列 tenure 超出範圍`,
    }))
    stubFetch(() =>
      Promise.resolve(
        errorResponse('INVALID_ROWS', 422, {
          details,
          meta: { total_errors: 26, invalid_row_count: 24 },
        }),
      ),
    )
    await mountWithFile()
    await button('開始預測')?.trigger('click')
    await flushPromises()
    const errors = wrapper.find('[data-testid="batch-errors"]')
    expect(errors.text()).toContain('有 24 列資料需要修正，整份檔案未進行預測')
    expect(errors.findAll('tbody tr')).toHaveLength(21)
    expect(errors.text()).toContain('另有 6 筆')
  })
})
