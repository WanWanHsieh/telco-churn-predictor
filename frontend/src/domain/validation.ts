// 前端驗證（ui.md 3.2；範圍與後端一致，見 design.md 6.2）。
import { getLockState } from './dependencies'
import {
  FIELDS,
  FEATURE_NAMES,
  RANGES,
  getField,
  type FeatureName,
  type FieldErrors,
  type FormValues,
} from './fields'

export const MESSAGES = {
  tenure: '在網月數需為 0 至 72 的整數',
  monthlyCharges: '月費需介於 0 至 200 之間',
  totalChargesInvalid: '累計費用需為 0 以上的數字',
  totalChargesTooLarge: '累計費用不可超過 10,000',
  totalChargesEstimateTooLarge: '估算累計費用超過上限，請手動填寫',
} as const

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === ''
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * TotalCharges 留空時系統以 tenure × MonthlyCharges 估算；估算值（四捨五入 2 位）超過上限視為錯誤。
 * tenure 或 MonthlyCharges 本身有錯時不重複報這條。
 */
function estimatedTotalError(values: FormValues): string | null {
  if (validateField('tenure', values) || validateField('MonthlyCharges', values)) return null
  const estimate = Math.round(Number(values.tenure) * Number(values.MonthlyCharges) * 100) / 100
  return estimate > RANGES.TotalCharges.max ? MESSAGES.totalChargesEstimateTooLarge : null
}

/** 單一欄位驗證；通過回傳 null。被連動鎖定的欄位不驗證。 */
export function validateField(name: FeatureName, values: FormValues): string | null {
  if (getLockState(name, values) === 'locked') return null
  const field = getField(name)
  const value = values[name]

  switch (name) {
    case 'tenure': {
      if (isEmpty(value)) return field.requiredMessage
      const { min, max } = RANGES.tenure
      return isFiniteNumber(value) && Number.isInteger(value) && value >= min && value <= max
        ? null
        : MESSAGES.tenure
    }
    case 'MonthlyCharges': {
      if (isEmpty(value)) return field.requiredMessage
      const { min, max } = RANGES.MonthlyCharges
      return isFiniteNumber(value) && value >= min && value <= max ? null : MESSAGES.monthlyCharges
    }
    case 'TotalCharges': {
      if (isEmpty(value)) return estimatedTotalError(values) // 選填；空白時檢查系統估算值是否超過上限
      if (!isFiniteNumber(value) || value < RANGES.TotalCharges.min) {
        return MESSAGES.totalChargesInvalid
      }
      return value > RANGES.TotalCharges.max ? MESSAGES.totalChargesTooLarge : null
    }
    default: {
      if (isEmpty(value)) return field.requiredMessage
      const allowed = field.options.some((o) => o.value === value)
      return allowed ? null : field.requiredMessage
    }
  }
}

/** 全表單驗證，只回傳有錯的欄位 */
export function validateForm(values: FormValues): FieldErrors {
  const errors: FieldErrors = {}
  for (const field of FIELDS) {
    const message = validateField(field.name, values)
    if (message) errors[field.name] = message
  }
  return errors
}

/** 依畫面順序列出有錯誤的欄位 */
export function errorFieldsInOrder(errors: FieldErrors): FeatureName[] {
  return FEATURE_NAMES.filter((n) => errors[n])
}
