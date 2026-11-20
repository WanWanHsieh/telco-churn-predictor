import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, NETWORK_ERROR, postJson, request } from '../../api/client'
import { predict, toRequestBody } from '../../api/predictions'
import { getExample } from '../../domain/examples'
import { jsonResponse, makePrediction } from '../fixtures/prediction'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

async function catchError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError)
    return err as ApiError
  }
  throw new Error('預期拋出 ApiError')
}

describe('api client', () => {
  it('成功時回傳 JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/health')).resolves.toEqual({ ok: true })
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/health')
  })

  it('錯誤格式正規化為 ApiError（含欄位錯誤與 request id）', async () => {
    const body = {
      error: {
        code: 'VALIDATION_ERROR',
        message: '輸入資料有誤',
        details: [{ field: 'tenure', row: null, type: 'out_of_range', reason: '需介於 0–72' }],
        meta: null,
        request_id: 'req-1',
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(body, 422)))
    const error = await catchError(postJson('/predictions', {}))
    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.status).toBe(422)
    expect(error.details[0]?.field).toBe('tenure')
    expect(error.requestId).toBe('req-1')
  })

  it('網路中斷 → NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await catchError(request('/health'))
    expect(error.code).toBe(NETWORK_ERROR)
    expect(error.isNetworkError).toBe(true)
  })

  it('非 JSON 回應 → NETWORK_ERROR', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>Bad Gateway</html>', { status: 502 })),
    )
    const error = await catchError(request('/health'))
    expect(error.code).toBe(NETWORK_ERROR)
    expect(error.status).toBe(502)
  })

  it('非統一格式的錯誤 JSON → NETWORK_ERROR', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'x' }, 500)))
    expect((await catchError(request('/health'))).code).toBe(NETWORK_ERROR)
  })

  it('逾時（10 秒）→ NETWORK_ERROR', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            )
          }),
      ),
    )
    const pending = catchError(request('/health'))
    await vi.advanceTimersByTimeAsync(10_000)
    const error = await pending
    expect(error.code).toBe(NETWORK_ERROR)
    expect(error.message).toBe('請求逾時')
  })
})

describe('predictions api', () => {
  it('TotalCharges 留空時不送出該欄位，交由後端估算', () => {
    const values = { ...getExample('low'), TotalCharges: null }
    const body = toRequestBody(values)
    expect('TotalCharges' in body).toBe(false)
    expect(Object.keys(body)).toHaveLength(18)
  })

  it('只呼叫一次 API 即取得機率與因素（AC-2.6）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(makePrediction()))
    vi.stubGlobal('fetch', fetchMock)
    const result = await predict(getExample('high'))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/predictions')
    expect(init.method).toBe('POST')
    expect(result.top_factors).toHaveLength(5)
  })
})
