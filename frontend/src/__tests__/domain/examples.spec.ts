import { describe, expect, it } from 'vitest'

import { applyDependencies } from '../../domain/dependencies'
import { HIGH_RISK_EXAMPLE, LOW_RISK_EXAMPLE, getExample } from '../../domain/examples'
import { FEATURE_NAMES, FIELDS } from '../../domain/fields'
import { validateForm } from '../../domain/validation'

describe('範例資料（design.md 6.7）', () => {
  it('高風險範例 19 欄完整相等（design.md 6.7）', () => {
    expect({ ...HIGH_RISK_EXAMPLE }).toEqual({
      gender: 'Female',
      SeniorCitizen: 0,
      Partner: 'No',
      Dependents: 'No',
      tenure: 1,
      PhoneService: 'Yes',
      MultipleLines: 'No',
      InternetService: 'Fiber optic',
      OnlineSecurity: 'No',
      OnlineBackup: 'No',
      DeviceProtection: 'No',
      TechSupport: 'No',
      StreamingTV: 'Yes',
      StreamingMovies: 'Yes',
      Contract: 'Month-to-month',
      PaperlessBilling: 'Yes',
      PaymentMethod: 'Electronic check',
      MonthlyCharges: 100,
      TotalCharges: null,
    })
  })

  it('低風險範例 19 欄完整相等（design.md 6.7）', () => {
    expect({ ...LOW_RISK_EXAMPLE }).toEqual({
      gender: 'Male',
      SeniorCitizen: 0,
      Partner: 'Yes',
      Dependents: 'Yes',
      tenure: 70,
      PhoneService: 'Yes',
      MultipleLines: 'Yes',
      InternetService: 'No',
      OnlineSecurity: 'No internet service',
      OnlineBackup: 'No internet service',
      DeviceProtection: 'No internet service',
      TechSupport: 'No internet service',
      StreamingTV: 'No internet service',
      StreamingMovies: 'No internet service',
      Contract: 'Two year',
      PaperlessBilling: 'No',
      PaymentMethod: 'Credit card (automatic)',
      MonthlyCharges: 30,
      TotalCharges: 2100,
    })
  })

  it('高風險範例與後端 core 的 high_risk_example.json 一致（該檔刻意省略 TotalCharges）', async () => {
    // 專案未安裝 @types/node，以變數模組名動態載入 node:fs（測試在 Node 執行）
    const fsModule = 'node:fs'
    const { readFileSync } = (await import(/* @vite-ignore */ fsModule)) as {
      readFileSync: (path: string, encoding: string) => string
    }
    // vitest 在 frontend/ 執行，fixture 在 repo 根目錄的 core/ 下
    const cwd = (globalThis as unknown as { process: { cwd: () => string } }).process.cwd()
    const path = `${cwd}/../core/tests/fixtures/high_risk_example.json`
    const fixture = JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>
    expect('TotalCharges' in fixture).toBe(false)
    expect({ ...HIGH_RISK_EXAMPLE, TotalCharges: undefined }).toEqual({
      ...fixture,
      TotalCharges: undefined,
    })
  })

  it.each(['high', 'low'] as const)('%s 範例含 19 欄、通過驗證、連動一致', (kind) => {
    const example = getExample(kind)
    expect(Object.keys(example).sort()).toEqual([...FEATURE_NAMES].sort())
    expect(validateForm(example)).toEqual({})
    expect(applyDependencies(example)).toEqual(example)
  })

  it.each(['high', 'low'] as const)('%s 範例的選項值都是資料集合法值', (kind) => {
    const example = getExample(kind)
    for (const f of FIELDS.filter((x) => x.options.length > 0)) {
      const locked = ['No phone service', 'No internet service'].includes(String(example[f.name]))
      if (!locked) expect(f.options.map((o) => o.value)).toContain(example[f.name])
    }
  })

  it('getExample 回傳副本，不會改到常數', () => {
    const copy = getExample('high')
    copy.tenure = 99
    expect(HIGH_RISK_EXAMPLE.tenure).toBe(1)
  })
})
