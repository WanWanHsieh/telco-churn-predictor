// 電話／網路連動規則（AC-1.5、1.6）：純函式，不依賴 Vue。
import { opt, type FeatureName, type FieldOption, type FormValues } from './fields'

export interface DependencyRule {
  source: FeatureName
  /** 來源欄位為此值時鎖定目標欄位 */
  lockWhen: string
  lockedOption: FieldOption
  targets: readonly FeatureName[]
  /** 鎖定時欄位下方說明 */
  lockedHint: string
  /** 來源尚未選擇時的提示 */
  waitingHint: string
}

export const NO_PHONE_SERVICE = 'No phone service'
export const NO_INTERNET_SERVICE = 'No internet service'

export const DEPENDENCY_RULES: readonly DependencyRule[] = [
  {
    source: 'PhoneService',
    lockWhen: 'No',
    lockedOption: opt('無電話服務', NO_PHONE_SERVICE),
    targets: ['MultipleLines'],
    lockedHint: '無電話服務時不適用',
    waitingHint: '請先選擇電話服務',
  },
  {
    source: 'InternetService',
    lockWhen: 'No',
    lockedOption: opt('無網路服務', NO_INTERNET_SERVICE),
    targets: [
      'OnlineSecurity',
      'OnlineBackup',
      'DeviceProtection',
      'TechSupport',
      'StreamingTV',
      'StreamingMovies',
    ],
    lockedHint: '無網路服務時不適用',
    waitingHint: '請先選擇網路服務',
  },
]

/** locked：被鎖定為固定值；waiting：來源尚未選擇而停用；free：可自由選擇 */
export type LockState = 'locked' | 'waiting' | 'free'

export function ruleFor(name: FeatureName): DependencyRule | undefined {
  return DEPENDENCY_RULES.find((r) => r.targets.includes(name))
}

export function getLockState(name: FeatureName, values: FormValues): LockState {
  const rule = ruleFor(name)
  if (!rule) return 'free'
  const source = values[rule.source]
  if (source === rule.lockWhen) return 'locked'
  if (source === null || source === undefined || source === '') return 'waiting'
  return 'free'
}

/**
 * 依連動規則整理整組表單值，回傳新物件（不修改輸入）。
 * - 來源為鎖定條件：目標設為固定值
 * - 否則若目標仍是舊的固定值：清回未選（改回「有」不保留舊值）
 */
export function applyDependencies(values: FormValues): FormValues {
  const next: FormValues = { ...values }
  for (const rule of DEPENDENCY_RULES) {
    const locked = next[rule.source] === rule.lockWhen
    for (const target of rule.targets) {
      if (locked) {
        next[target] = rule.lockedOption.value
      } else if (next[target] === rule.lockedOption.value) {
        next[target] = null
      }
    }
  }
  return next
}
