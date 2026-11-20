// 單筆預測的表單狀態（T8）與送出狀態、API 結果（T9）。
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, NETWORK_ERROR } from '../api/client'
import { predict, type PredictionResponse } from '../api/predictions'
import { applyDependencies } from '../domain/dependencies'
import { getExample, type ExampleKind } from '../domain/examples'
import {
  createEmptyValues,
  FEATURE_NAMES,
  type FeatureName,
  type FieldErrors,
  type FieldValue,
  type FormValues,
} from '../domain/fields'
import { validateForm } from '../domain/validation'

export type SubmitStatus = 'idle' | 'loading' | 'success' | 'error'

export const usePredictionStore = defineStore('prediction', () => {
  const values = ref<FormValues>(createEmptyValues())
  const errors = ref<FieldErrors>({})
  /** 是否按過「預測」；之後欄位變更即時重驗 */
  const attempted = ref(false)
  const showSummary = ref(false)

  const errorCount = computed(() => Object.keys(errors.value).length)

  function setValue(name: FeatureName, value: FieldValue | undefined): void {
    values.value = applyDependencies({ ...values.value, [name]: value ?? null })
    if (attempted.value) {
      errors.value = validateForm(values.value)
      // 錯誤全部修正後，摘要一併消失
      if (errorCount.value === 0) showSummary.value = false
    }
  }

  function resetValidation(): void {
    errors.value = {}
    attempted.value = false
    showSummary.value = false
  }

  /** 載入範例：走同一連動邏輯，清掉驗證狀態，不自動預測 */
  function loadExample(kind: ExampleKind): void {
    values.value = applyDependencies(getExample(kind))
    resetValidation()
  }

  function reset(): void {
    values.value = createEmptyValues()
    resetValidation()
  }

  /** 驗證整張表單；有錯時顯示摘要並回傳 false */
  function validate(): boolean {
    attempted.value = true
    errors.value = validateForm(values.value)
    showSummary.value = errorCount.value > 0
    return errorCount.value === 0
  }

  function dismissSummary(): void {
    showSummary.value = false
  }

  function payload(): FormValues {
    return { ...values.value }
  }

  // ---- 送出狀態與 API 結果（T9） ----
  const status = ref<SubmitStatus>('idle')
  const result = ref<PredictionResponse | null>(null)
  const serviceError = ref<ApiError | null>(null)
  /** 最近一次送出的資料，供「重試」重送同一組 */
  const lastSubmitted = ref<FormValues | null>(null)
  const loading = computed(() => status.value === 'loading')

  /** 把 API 422 的欄位錯誤放到對應欄位下方（AC-1.8） */
  function applyServerErrors(error: ApiError): boolean {
    const mapped: FieldErrors = {}
    for (const detail of error.details) {
      const field = detail.field as FeatureName | null
      if (field && (FEATURE_NAMES as readonly string[]).includes(field) && !mapped[field]) {
        mapped[field] = detail.reason
      }
    }
    if (Object.keys(mapped).length === 0) return false
    attempted.value = true
    errors.value = mapped
    showSummary.value = true
    return true
  }

  async function submit(formValues: FormValues): Promise<void> {
    if (status.value === 'loading') return // 進行中不重複送出，避免兩個回應互相覆蓋
    lastSubmitted.value = formValues
    status.value = 'loading'
    serviceError.value = null
    try {
      result.value = await predict(formValues)
      status.value = 'success'
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError({ code: NETWORK_ERROR, message: '無法連線到伺服器' })
      if (apiError.status === 422 && applyServerErrors(apiError)) {
        result.value = null
        status.value = 'idle'
        return
      }
      serviceError.value = apiError
      status.value = 'error'
    }
  }

  async function retry(): Promise<void> {
    if (lastSubmitted.value) await submit(lastSubmitted.value)
  }

  return {
    values,
    errors,
    attempted,
    showSummary,
    errorCount,
    setValue,
    loadExample,
    reset,
    validate,
    dismissSummary,
    payload,
    status,
    result,
    serviceError,
    loading,
    submit,
    retry,
  }
})
