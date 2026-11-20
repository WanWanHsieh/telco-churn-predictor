// 共用 HTTP 客戶端：統一逾時、錯誤正規化（design.md 6.3 錯誤格式）。
import type { components } from './schema.gen'

export type ErrorDetail = components['schemas']['ErrorDetail']

/** 網路中斷、逾時、非 JSON 回應時使用的前端錯誤碼 */
export const NETWORK_ERROR = 'NETWORK_ERROR'

export const DEFAULT_TIMEOUT_MS = 10_000
export const BATCH_TIMEOUT_MS = 60_000

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

/** 所有 API 失敗都正規化成這個型別，畫面只依 code 判斷 */
export class ApiError extends Error {
  readonly code: string
  readonly status: number | null
  readonly details: ErrorDetail[]
  readonly requestId: string | null
  /** 補充資訊（例如上限值、錯誤總數） */
  readonly meta: Record<string, unknown>

  constructor(options: {
    code: string
    message: string
    status?: number | null
    details?: ErrorDetail[]
    requestId?: string | null
    meta?: Record<string, unknown> | null
  }) {
    super(options.message)
    this.name = 'ApiError'
    this.code = options.code
    this.status = options.status ?? null
    this.details = options.details ?? []
    this.requestId = options.requestId ?? null
    this.meta = options.meta ?? {}
  }

  /** 讀取 meta 中的數值欄位，不存在或不是數字時回 null */
  metaNumber(key: string): number | null {
    const value = this.meta[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }

  get isNetworkError(): boolean {
    return this.code === NETWORK_ERROR
  }
}

interface ErrorEnvelope {
  error: {
    code: string
    message: string
    details?: ErrorDetail[]
    meta?: Record<string, unknown> | null
    request_id?: string
  }
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false
  const error = (body as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

function networkError(message: string, status: number | null = null): ApiError {
  return new ApiError({ code: NETWORK_ERROR, message, status })
}

export interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: BodyInit | null
  headers?: Record<string, string>
  timeoutMs?: number
}

/** 送出請求並回傳解析後的 JSON；任何失敗都拋 ApiError */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      body: options.body ?? null,
      headers: { Accept: 'application/json', ...options.headers },
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timer)
    const timedOut = err instanceof DOMException && err.name === 'AbortError'
    throw networkError(timedOut ? '請求逾時' : '無法連線到伺服器')
  }

  // 讀取本體也受同一個逾時保護（標頭送達後伺服器卡住時不會無限等待）
  let body: unknown
  try {
    body = await response.json()
  } catch (err) {
    const timedOut = err instanceof DOMException && err.name === 'AbortError'
    throw networkError(timedOut ? '請求逾時' : '伺服器回應格式錯誤', response.status)
  } finally {
    clearTimeout(timer)
  }

  if (response.ok) return body as T

  if (isErrorEnvelope(body)) {
    throw new ApiError({
      code: body.error.code,
      message: body.error.message,
      status: response.status,
      details: body.error.details ?? [],
      requestId: body.error.request_id ?? response.headers.get('X-Request-ID'),
      meta: body.error.meta ?? null,
    })
  }
  throw networkError('伺服器回應格式錯誤', response.status)
}

/** 以 JSON 本體 POST */
export function postJson<T>(path: string, payload: unknown, timeoutMs?: number): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
    timeoutMs,
  })
}
