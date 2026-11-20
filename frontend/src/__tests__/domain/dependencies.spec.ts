import { describe, expect, it } from 'vitest'

import { applyDependencies, getLockState } from '../../domain/dependencies'
import { createEmptyValues, type FormValues } from '../../domain/fields'

const ADDONS = [
  'OnlineSecurity',
  'OnlineBackup',
  'DeviceProtection',
  'TechSupport',
  'StreamingTV',
  'StreamingMovies',
] as const

function withValues(patch: Partial<FormValues>): FormValues {
  return { ...createEmptyValues(), ...patch }
}

describe('applyDependencies', () => {
  it('PhoneService=No 時 MultipleLines 鎖定為 No phone service（AC-1.5）', () => {
    const result = applyDependencies(withValues({ PhoneService: 'No' }))
    expect(result.MultipleLines).toBe('No phone service')
    expect(getLockState('MultipleLines', result)).toBe('locked')
  })

  it('InternetService=No 時 6 個附加服務鎖定為 No internet service（AC-1.6）', () => {
    const result = applyDependencies(withValues({ InternetService: 'No' }))
    for (const name of ADDONS) {
      expect(result[name]).toBe('No internet service')
      expect(getLockState(name, result)).toBe('locked')
    }
  })

  it('鎖定時會覆蓋使用者先前選的值', () => {
    const result = applyDependencies(withValues({ PhoneService: 'No', MultipleLines: 'Yes' }))
    expect(result.MultipleLines).toBe('No phone service')
  })

  it('改回「有」時清空被鎖定的欄位，不保留舊值', () => {
    const locked = applyDependencies(withValues({ PhoneService: 'No', InternetService: 'No' }))
    const back = applyDependencies({ ...locked, PhoneService: 'Yes', InternetService: 'DSL' })
    expect(back.MultipleLines).toBeNull()
    for (const name of ADDONS) expect(back[name]).toBeNull()
  })

  it('來源為有時，保留使用者已選的 Yes／No', () => {
    const result = applyDependencies(
      withValues({
        PhoneService: 'Yes',
        MultipleLines: 'Yes',
        InternetService: 'DSL',
        TechSupport: 'No',
      }),
    )
    expect(result.MultipleLines).toBe('Yes')
    expect(result.TechSupport).toBe('No')
  })

  it('不修改傳入的物件', () => {
    const input = withValues({ PhoneService: 'No' })
    applyDependencies(input)
    expect(input.MultipleLines).toBeNull()
  })
})

describe('getLockState', () => {
  it('來源未選時為 waiting，選了「有」為 free', () => {
    expect(getLockState('MultipleLines', createEmptyValues())).toBe('waiting')
    expect(getLockState('TechSupport', createEmptyValues())).toBe('waiting')
    expect(getLockState('MultipleLines', withValues({ PhoneService: 'Yes' }))).toBe('free')
  })

  it('沒有連動的欄位永遠是 free', () => {
    expect(getLockState('gender', createEmptyValues())).toBe('free')
    expect(getLockState('Contract', createEmptyValues())).toBe('free')
  })
})
