import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PerformanceView from '../../views/PerformanceView.vue'
import { makeMetrics } from '../fixtures/metrics'
import { jsonResponse } from '../fixtures/prediction'

let wrapper: VueWrapper

function mountView() {
  // Chart.js 需要 canvas，jsdom 沒有；ROC 圖以替身元件測試版面
  wrapper = mount(PerformanceView, {
    global: {
      plugins: [createPinia()],
      stubs: { RocChart: { template: '<div class="roc-stub" />' } },
    },
  })
}

function errorBody(code: string, status: number) {
  return jsonResponse(
    { error: { code, message: 'x', details: [], meta: null, request_id: 'r' } },
    status,
  )
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

describe('PerformanceView', () => {
  it('載入中顯示骨架', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    mountView()
    expect(wrapper.find('[data-testid="perf-skeleton"]').exists()).toBe(true)
  })

  it('成功時顯示資料說明 5 項、指標表、混淆矩陣與白話說明，數字皆來自 API（AC-3.3、3.5、3.6）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(makeMetrics())))
    mountView()
    await flushPromises()
    const text = wrapper.text()
    for (const label of [
      '訓練集筆數',
      '測試集筆數',
      '測試集流失比例',
      '決策門檻值',
      '模型訓練日期',
    ]) {
      expect(text).toContain(label)
    }
    expect(text).toContain('1,000')
    expect(text).toContain('0.41')
    expect(text).toContain('2026-01-02')
    expect(wrapper.find('[data-cell="tp"]').text()).toContain('310')
    expect(wrapper.find('.roc-stub').exists()).toBe(true)
    const note = wrapper.findAll('.imbalance-note__text')
    expect(note.length).toBeLessThanOrEqual(3)
    expect(note[1]?.text()).toContain('0.41')
    expect(note[1]?.text()).toContain('80%')
  })

  it('404 顯示「尚無成效資料」（AC-3.7）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errorBody('METRICS_NOT_FOUND', 404)))
    mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('尚無成效資料')
    expect(wrapper.text()).not.toContain('無法載入模型成效')
  })

  it('錯誤時顯示友善訊息，重試後成功（AC-3.7）', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorBody('INTERNAL_ERROR', 500))
      .mockResolvedValueOnce(jsonResponse(makeMetrics()))
    vi.stubGlobal('fetch', fetchMock)
    mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('無法載入模型成效')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '重試')
      ?.trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('指標比較')
  })
})
