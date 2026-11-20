// 單筆預測的表單狀態（T8）；送出狀態與 API 結果由 T9 補上。
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { applyDependencies } from '../domain/dependencies'
import { getExample, type ExampleKind } from '../domain/examples'
import {
  createEmptyValues,
  type FeatureName,
  type FieldErrors,
  type FieldValue,
  type FormValues,
} from '../domain/fields'
import { validateForm } from '../domain/validation'

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
  }
})
