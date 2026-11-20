import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getExample } from '../../domain/examples'
import { usePredictionStore } from '../../stores/prediction'
import PredictView from '../../views/PredictView.vue'
import { jsonResponse, makePrediction } from '../fixtures/prediction'

let pinia: Pinia
let wrapper: VueWrapper

// el-form-item 的錯誤訊息以 100ms debounce 顯示
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 150))
  await flushPromises()
}

function mountView() {
  wrapper = mount(PredictView, { attachTo: document.body, global: { plugins: [pinia] } })
  const store = usePredictionStore()
  store.loadExample('high')
  return store
}

async function submit() {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})

afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

describe('PredictView', () => {
  it('預測中按鈕 disabled 且 loading，結果區顯示骨架（AC-1.10）', async () => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending.promise))
    mountView()
    await submit()

    const button = wrapper.find('button[type="submit"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.classes()).toContain('is-loading')
    expect(button.text()).toContain('預測中')
    expect(wrapper.find('[data-testid="result-skeleton"]').exists()).toBe(true)
    expect(wrapper.find('aside').attributes('aria-busy')).toBe('true')

    pending.resolve(jsonResponse(makePrediction()))
    await flushPromises()
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  it('成功後顯示結果，只呼叫一次 API（AC-1.2、2.6）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(makePrediction()))
    vi.stubGlobal('fetch', fetchMock)
    mountView()
    await submit()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.result__probability').text()).toContain('72.4%')
    expect(wrapper.findAll('.factor')).toHaveLength(5)
  })

  it('重新預測時舊結果淡化不清空', async () => {
    const second = deferred<Response>()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(makePrediction()))
      .mockReturnValueOnce(second.promise)
    vi.stubGlobal('fetch', fetchMock)
    mountView()
    await submit()
    await submit()
    expect(wrapper.find('.result-wrap').classes()).toContain('result-wrap--stale')
    expect(wrapper.find('.result__probability').exists()).toBe(true)
    second.resolve(jsonResponse(makePrediction({ probability: 0.1, risk_level: 'low' })))
    await flushPromises()
    expect(wrapper.find('.result-wrap').classes()).not.toContain('result-wrap--stale')
    expect(wrapper.find('.result__probability').text()).toContain('10.0%')
  })

  it.each([
    [
      '503',
      () =>
        Promise.resolve(
          jsonResponse(
            {
              error: {
                code: 'MODEL_UNAVAILABLE',
                message: '模型暫時無法使用',
                details: [],
                meta: null,
                request_id: 'r',
              },
            },
            503,
          ),
        ),
    ],
    ['網路中斷', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('%s：顯示「服務暫時無法使用」並保留表單，重試可重送（AC-1.9）', async (_name, failure) => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(failure)
      .mockResolvedValueOnce(jsonResponse(makePrediction()))
    vi.stubGlobal('fetch', fetchMock)
    const store = mountView()
    await submit()

    expect(wrapper.text()).toContain('服務暫時無法使用')
    expect(wrapper.text()).toContain('您填寫的資料仍保留')
    expect(store.values).toEqual(getExample('high'))

    const retry = wrapper.findAll('button').find((b) => b.text() === '重試')
    await retry?.trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1].body as string)).toEqual(
      JSON.parse(fetchMock.mock.calls[0]?.[1].body as string),
    )
    expect(wrapper.find('.result__probability').exists()).toBe(true)
  })

  it('API 422 的欄位錯誤顯示在對應欄位下方（AC-1.8）', async () => {
    const body = {
      error: {
        code: 'VALIDATION_ERROR',
        message: '輸入資料有誤',
        details: [
          {
            field: 'TotalCharges',
            row: null,
            type: 'out_of_range',
            reason: '累計費用估算值為 14,400.00，超過上限 10,000，請手動填寫累計費用',
          },
        ],
        meta: null,
        request_id: 'r',
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, 422)))
    mountView()
    await submit()
    await settle()
    expect(wrapper.find('[data-field="TotalCharges"] .el-form-item__error').text()).toContain(
      '超過上限 10,000',
    )
    expect(wrapper.find('.result__probability').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('服務暫時無法使用')
  })
})
