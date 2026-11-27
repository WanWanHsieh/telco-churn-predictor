import { describe, expect, it } from 'vitest'

import { applyDependencies } from '../../domain/dependencies'
import { getExample } from '../../domain/examples'
import { FEATURE_NAMES, FIELDS, getField, type FormValues } from '../../domain/fields'
import { errorFieldsInOrder, validateField, validateForm } from '../../domain/validation'

function valid(patch: Partial<FormValues> = {}): FormValues {
  return { ...getExample('low'), ...patch }
}

describe('validateForm', () => {
  it('空表單：18 個必填欄位都有錯，TotalCharges 不算錯（AC-1.7）', () => {
    const errors = validateForm(
      Object.fromEntries(FEATURE_NAMES.map((n) => [n, null])) as FormValues,
    )
    // 空表單時 6 個網路附加服務與 MultipleLines 為 waiting（未鎖定），仍需必填
    expect(Object.keys(errors)).toHaveLength(18)
    expect(errors.TotalCharges).toBeUndefined()
  })

  it('必填訊息符合 ui.md', () => {
    const errors = validateForm(
      Object.fromEntries(FEATURE_NAMES.map((n) => [n, null])) as FormValues,
    )
    expect(errors.gender).toBe('請選擇性別')
    expect(errors.tenure).toBe('請輸入在網月數')
    expect(errors.MonthlyCharges).toBe('請輸入月費')
    expect(errors.Contract).toBe('請選擇合約類型')
  })

  it('兩組範例皆無錯誤', () => {
    expect(validateForm(getExample('high'))).toEqual({})
    expect(validateForm(getExample('low'))).toEqual({})
  })

  it('被連動鎖定的欄位不觸發必填錯誤', () => {
    const values = applyDependencies(valid({ PhoneService: 'No', MultipleLines: null }))
    expect(validateForm(values).MultipleLines).toBeUndefined()
  })

  it('每個欄位的必填訊息都有定義', () => {
    for (const f of FIELDS.filter((x) => x.required)) expect(f.requiredMessage).not.toBe('')
  })
})

describe('tenure', () => {
  it.each([-1, 73, 10.5, Number.NaN])('%s 不合法', (v) => {
    expect(validateField('tenure', valid({ tenure: v }))).toBe('在網月數需為 0 至 72 的整數')
  })
  it.each([0, 1, 72])('%s 合法', (v) => {
    expect(validateField('tenure', valid({ tenure: v }))).toBeNull()
  })
  it('字串不合法', () => {
    expect(validateField('tenure', valid({ tenure: '10' }))).toBe('在網月數需為 0 至 72 的整數')
  })
})

describe('MonthlyCharges', () => {
  it.each([-0.01, 200.01, Number.NaN])('%s 不合法', (v) => {
    expect(validateField('MonthlyCharges', valid({ MonthlyCharges: v }))).toBe(
      '月費需介於 0 至 200 之間',
    )
  })
  it.each([0, 99.99, 200])('%s 合法', (v) => {
    expect(validateField('MonthlyCharges', valid({ MonthlyCharges: v }))).toBeNull()
  })
})

describe('TotalCharges（選填）', () => {
  it('空白不算錯誤', () => {
    expect(validateField('TotalCharges', valid({ TotalCharges: null }))).toBeNull()
  })
  it('負數不合法', () => {
    expect(validateField('TotalCharges', valid({ TotalCharges: -1 }))).toBe(
      '累計費用需為 0 以上的數字',
    )
  })
  it('非數字不合法', () => {
    expect(validateField('TotalCharges', valid({ TotalCharges: 'abc' }))).toBe(
      '累計費用需為 0 以上的數字',
    )
  })
  it('超過 10,000 不合法，邊界 10,000 與 0 合法', () => {
    expect(validateField('TotalCharges', valid({ TotalCharges: 10000.01 }))).toBe(
      '累計費用不可超過 10,000',
    )
    expect(validateField('TotalCharges', valid({ TotalCharges: 10000 }))).toBeNull()
    expect(validateField('TotalCharges', valid({ TotalCharges: 0 }))).toBeNull()
  })
})

describe('TotalCharges 留空時的估算上限', () => {
  const EST = '估算累計費用超過上限，請手動填寫'
  it('tenure × MonthlyCharges > 10,000 時報錯', () => {
    expect(
      validateField('TotalCharges', valid({ TotalCharges: null, tenure: 72, MonthlyCharges: 150 })),
    ).toBe(EST)
    expect(
      validateForm(valid({ TotalCharges: null, tenure: 72, MonthlyCharges: 150 })).TotalCharges,
    ).toBe(EST)
  })
  it('剛好 10,000 與略低於上限不算錯，略高於上限報錯', () => {
    expect(
      validateField('TotalCharges', valid({ TotalCharges: null, tenure: 50, MonthlyCharges: 200 })),
    ).toBeNull()
    expect(
      validateField('TotalCharges', valid({ TotalCharges: null, tenure: 1, MonthlyCharges: 200 })),
    ).toBeNull()
    expect(
      validateField(
        'TotalCharges',
        valid({ TotalCharges: null, tenure: 51, MonthlyCharges: 196.07 }),
      ),
    ).toBeNull()
    expect(
      validateField(
        'TotalCharges',
        valid({ TotalCharges: null, tenure: 51, MonthlyCharges: 196.08 }),
      ),
    ).toBe(EST)
  })
  it('tenure 或 MonthlyCharges 本身有錯時不重複報這條', () => {
    expect(
      validateField(
        'TotalCharges',
        valid({ TotalCharges: null, tenure: null, MonthlyCharges: 200 }),
      ),
    ).toBeNull()
    expect(
      validateField('TotalCharges', valid({ TotalCharges: null, tenure: 80, MonthlyCharges: 200 })),
    ).toBeNull()
    expect(
      validateField('TotalCharges', valid({ TotalCharges: null, tenure: 72, MonthlyCharges: 250 })),
    ).toBeNull()
  })
  it('手填 TotalCharges 時不套用估算規則', () => {
    expect(
      validateField('TotalCharges', valid({ TotalCharges: 5000, tenure: 72, MonthlyCharges: 200 })),
    ).toBeNull()
  })
})

describe('選擇型欄位', () => {
  it('不在選項內的值視為未選', () => {
    expect(validateField('Contract', valid({ Contract: 'Weekly' }))).toBe('請選擇合約類型')
  })
  it('SeniorCitizen 的 0 是合法值（不被當成空白）', () => {
    expect(validateField('SeniorCitizen', valid({ SeniorCitizen: 0 }))).toBeNull()
    expect(getField('SeniorCitizen').options.map((o) => o.value)).toEqual([0, 1])
  })
})

describe('errorFieldsInOrder', () => {
  it('依畫面順序排列：基本欄位在前，進階欄位在後', () => {
    expect(errorFieldsInOrder({ gender: 'y', tenure: 'z', Contract: 'x' })).toEqual([
      'Contract',
      'tenure',
      'gender',
    ])
  })
})
