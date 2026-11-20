// 批次預測頁狀態（ui.md 5.1）：上傳 → 處理中 → 結果三階段，含篩選、排序、分頁
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { predictBatch, type BatchResponse, type BatchRow } from '../api/batch'
import { ApiError, NETWORK_ERROR } from '../api/client'
import { getMeta, type BatchLimits } from '../api/meta'
import type { RiskLevel } from '../api/predictions'

export type BatchStage = 'upload' | 'processing' | 'result'
export type RiskFilter = 'all' | RiskLevel
export type SortKey = 'probability' | 'risk_level' | 'row'
export type SortOrder = 'ascending' | 'descending'

export const PAGE_SIZE = 20

const RISK_ORDER: Record<RiskLevel, number> = { low: 0, medium: 1, high: 2 }

export const useBatchStore = defineStore('batch', () => {
  const stage = ref<BatchStage>('upload')
  const file = ref<File | null>(null)
  const response = ref<BatchResponse | null>(null)
  const error = ref<ApiError | null>(null)
  /** 前端擋下的檔案錯誤（副檔名不是 .csv） */
  const fileError = ref<string | null>(null)
  const limits = ref<BatchLimits | null>(null)

  const filter = ref<RiskFilter>('all')
  const sortKey = ref<SortKey>('probability')
  const sortOrder = ref<SortOrder>('descending')
  const page = ref(1)

  async function loadLimits(): Promise<void> {
    if (limits.value) return
    try {
      limits.value = (await getMeta()).batch_limits
    } catch {
      limits.value = null // 取不到時文案不顯示數值，不影響上傳
    }
  }

  function selectFile(selected: File | null): void {
    error.value = null
    fileError.value = null
    if (selected && !selected.name.toLowerCase().endsWith('.csv')) {
      file.value = null
      fileError.value = 'not_csv'
      return
    }
    file.value = selected
  }

  async function submit(): Promise<void> {
    if (!file.value || stage.value === 'processing') return
    stage.value = 'processing'
    error.value = null
    try {
      response.value = await predictBatch(file.value)
      filter.value = 'all'
      sortKey.value = 'probability'
      sortOrder.value = 'descending'
      page.value = 1
      stage.value = 'result'
    } catch (err) {
      error.value =
        err instanceof ApiError
          ? err
          : new ApiError({ code: NETWORK_ERROR, message: '無法連線到伺服器' })
      response.value = null
      stage.value = 'upload'
    }
  }

  function restart(): void {
    stage.value = 'upload'
    file.value = null
    response.value = null
    error.value = null
    fileError.value = null
  }

  function setFilter(value: RiskFilter): void {
    filter.value = value
    page.value = 1
  }

  function setSort(key: SortKey, order: SortOrder | null): void {
    sortKey.value = order ? key : 'probability'
    sortOrder.value = order ?? 'descending'
    page.value = 1
  }

  const counts = computed(() => {
    const s = response.value?.summary
    return { all: s?.total ?? 0, high: s?.high ?? 0, medium: s?.medium ?? 0, low: s?.low ?? 0 }
  })

  const sortedRows = computed<BatchRow[]>(() => {
    const rows = response.value?.results ?? []
    const filtered =
      filter.value === 'all' ? rows : rows.filter((r) => r.risk_level === filter.value)
    const sign = sortOrder.value === 'ascending' ? 1 : -1
    const value = (r: BatchRow) =>
      sortKey.value === 'risk_level'
        ? RISK_ORDER[r.risk_level]
        : sortKey.value === 'row'
          ? r.row
          : r.probability
    // 同值依原始列號，排序結果固定
    return [...filtered].sort((a, b) => sign * (value(a) - value(b)) || a.row - b.row)
  })

  const pagedRows = computed(() =>
    sortedRows.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE),
  )

  return {
    stage,
    file,
    response,
    error,
    fileError,
    limits,
    filter,
    sortKey,
    sortOrder,
    page,
    counts,
    sortedRows,
    pagedRows,
    loadLimits,
    selectFile,
    submit,
    restart,
    setFilter,
    setSort,
  }
})
