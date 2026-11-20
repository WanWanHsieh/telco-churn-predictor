// 模型成效頁狀態：一次取得整份成效資料，整頁一起成功或失敗（ui.md 4.2）
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { ApiError, NETWORK_ERROR } from '../api/client'
import { getMetrics, type MetricsResponse } from '../api/metrics'

export type PerformanceStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error'

export const usePerformanceStore = defineStore('performance', () => {
  const status = ref<PerformanceStatus>('idle')
  const data = ref<MetricsResponse | null>(null)
  const error = ref<ApiError | null>(null)

  async function load(): Promise<void> {
    if (status.value === 'loading') return
    status.value = 'loading'
    error.value = null
    try {
      data.value = await getMetrics()
      status.value = 'success'
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError({ code: NETWORK_ERROR, message: '無法連線到伺服器' })
      data.value = null
      // 成效檔不存在（模型尚未訓練）視為空狀態，不是錯誤
      if (apiError.code === 'METRICS_NOT_FOUND') {
        status.value = 'empty'
        return
      }
      error.value = apiError
      status.value = 'error'
    }
  }

  /** 已成功載入過就不重抓（成效資料在服務生命週期內不變） */
  async function ensureLoaded(): Promise<void> {
    if (status.value !== 'success') await load()
  }

  return { status, data, error, load, ensureLoaded }
})
