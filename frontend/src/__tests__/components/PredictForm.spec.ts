import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import PredictForm from '../../components/predict/PredictForm.vue'
import { getExample } from '../../domain/examples'
import {
  ADVANCED_DEFAULTS,
  BASIC_FIELDS,
  FEATURE_NAMES,
  createInitialValues,
  type FeatureName,
} from '../../domain/fields'
import { usePredictionStore } from '../../stores/prediction'

let pinia: Pinia
let wrapper: VueWrapper
let store: ReturnType<typeof usePredictionStore>

function mountForm() {
  wrapper = mount(PredictForm, { attachTo: document.body, global: { plugins: [pinia] } })
}

function radios(name: FeatureName) {
  return wrapper.findAll<HTMLInputElement>(`#field-${name} input[type="radio"]`)
}

async function pick(name: FeatureName, value: string | number) {
  await wrapper.find(`#field-${name} input[value="${value}"]`).setValue()
}

// el-form-item 的錯誤訊息以 100ms debounce 顯示／隱藏
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 150))
  await flushPromises()
}

async function submit() {
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  await settle()
}

function errorText(name: FeatureName): string {
  return wrapper.find(`[data-field="${name}"] .el-form-item__error`).text()
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  store = usePredictionStore()
  mountForm()
})

afterEach(() => {
  wrapper.unmount()
  document.body.innerHTML = ''
})

describe('欄位呈現（AC-1.1）', () => {
  it('基本欄位在前且只有這 6 欄標必填；其餘 13 欄在進階欄位，TotalCharges 附說明', () => {
    const items = wrapper.findAll('[data-field]')
    const advanced = FEATURE_NAMES.filter((n) => !BASIC_FIELDS.includes(n))
    expect(items.map((i) => i.attributes('data-field'))).toEqual([...BASIC_FIELDS, ...advanced])
    expect(
      wrapper.findAll('[data-field].is-required').map((i) => i.attributes('data-field')),
    ).toEqual([...BASIC_FIELDS])
    expect(advanced).toHaveLength(13)
    const total = wrapper.find('[data-field="TotalCharges"]')
    expect(total.text()).toContain('累計費用（選填）')
    expect(total.text()).toContain('不填寫時，系統會以「在網月數 × 月費」估算')
    expect(wrapper.text()).toContain('只要填寫標示 * 的基本欄位即可預測')
  })

  it('進階欄位預設收合，按下切換後展開', async () => {
    const toggle = wrapper.find('.advanced-toggle')
    expect(toggle.text()).toContain('進階欄位（選填，13 欄）')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-field="gender"]').isVisible()).toBe(false)
    expect(wrapper.find('[data-field="Contract"]').isVisible()).toBe(true)
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-field="gender"]').isVisible()).toBe(true)
  })

  it('每個欄位有中文標籤，英文原始名為輔助文字', () => {
    const gender = wrapper.find('[data-field="gender"]')
    expect(gender.text()).toContain('性別')
    expect(gender.find('.field-en').text()).toBe('gender')
  })

  it('選項顯示「中文（原始值）」，送出值為資料集原始值', () => {
    expect(radios('gender').map((r) => r.element.value)).toEqual(['Female', 'Male'])
    expect(wrapper.find('[data-field="gender"]').text()).toContain('女（Female）')
    expect(radios('SeniorCitizen').map((r) => r.element.value)).toEqual(['0', '1'])
    expect(radios('InternetService').map((r) => r.element.value)).toEqual([
      'DSL',
      'Fiber optic',
      'No',
    ])
    expect(wrapper.find('[data-field="InternetService"]').text()).toContain('光纖（Fiber optic）')
  })

  it('選擇型欄位選了值之後，store 內是原始值（含 SeniorCitizen 為數字）', async () => {
    await pick('SeniorCitizen', 1)
    await pick('InternetService', 'Fiber optic')
    expect(store.values.SeniorCitizen).toBe(1)
    expect(store.values.InternetService).toBe('Fiber optic')
  })

  it('初始：基本欄位未填、進階欄位帶預設值；TechSupport 等網路服務選了才可選', () => {
    expect(store.values).toEqual(createInitialValues())
    for (const name of BASIC_FIELDS) expect(store.values[name]).toBeNull()
    expect(radios('TechSupport').every((r) => r.element.disabled)).toBe(true)
    expect(wrapper.find('[data-field="TechSupport"]').text()).toContain('請先選擇網路服務')
  })
})

describe('連動（AC-1.5、1.6）', () => {
  it('PhoneService=No 時 MultipleLines 鎖定，改回 Yes 回到預設值', async () => {
    await pick('PhoneService', 'No')
    const locked = radios('MultipleLines')
    expect(locked).toHaveLength(1)
    expect(locked[0]!.element.value).toBe('No phone service')
    expect(locked[0]!.element.checked).toBe(true)
    expect(locked[0]!.element.disabled).toBe(true)
    const item = wrapper.find('[data-field="MultipleLines"]')
    expect(item.text()).toContain('自動設定')
    expect(item.text()).toContain('無電話服務時不適用')
    expect(store.values.MultipleLines).toBe('No phone service')

    await pick('PhoneService', 'Yes')
    expect(store.values.MultipleLines).toBe('No')
    expect(radios('MultipleLines').map((r) => r.element.value)).toEqual(['Yes', 'No'])
    expect(radios('MultipleLines').every((r) => !r.element.disabled)).toBe(true)
    expect(radios('MultipleLines').find((r) => r.element.checked)?.element.value).toBe('No')
  })

  it('InternetService=No 時 6 個附加服務鎖定，改回 DSL 清空', async () => {
    await pick('InternetService', 'No')
    for (const name of [
      'OnlineSecurity',
      'OnlineBackup',
      'DeviceProtection',
      'TechSupport',
      'StreamingTV',
      'StreamingMovies',
    ] as const) {
      expect(store.values[name]).toBe('No internet service')
      expect(radios(name)[0]!.element.disabled).toBe(true)
      expect(wrapper.find(`[data-field="${name}"]`).text()).toContain('自動設定')
    }
    await pick('InternetService', 'DSL')
    expect(store.values.TechSupport).toBeNull()
    expect(store.values.OnlineSecurity).toBe('No')
    expect(radios('TechSupport').every((r) => !r.element.disabled)).toBe(true)
  })

  it('鎖定欄位有 aria-describedby 指向說明文字', async () => {
    await pick('PhoneService', 'No')
    const group = wrapper.find('#field-MultipleLines [role="radiogroup"]')
    const id = group.attributes('aria-describedby')
    expect(id).toBe('hint-MultipleLines')
    expect(wrapper.find(`#${id}`).text()).toBe('無電話服務時不適用')
  })
})

describe('驗證與送出（AC-1.7）', () => {
  it('空表單按預測：只有 6 個基本欄位報錯、進階欄位不展開、焦點移到第一個基本欄位', async () => {
    await submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(Object.keys(store.errors).sort()).toEqual([...BASIC_FIELDS].sort())
    expect(errorText('tenure')).toContain('請輸入在網月數')
    expect(errorText('MonthlyCharges')).toContain('請輸入月費')
    expect(wrapper.find('.el-alert').text()).toContain('有 6 個欄位需要修正，請查看標示的欄位')
    expect(wrapper.find('.advanced-toggle').attributes('aria-expanded')).toBe('false')
    const active = document.activeElement as HTMLElement
    expect(active.closest('#field-Contract')).not.toBeNull()
  })

  it('只填 6 個基本欄位即可送出，進階欄位以預設值補齊 19 欄', async () => {
    store.setValue('Contract', 'Month-to-month')
    store.setValue('tenure', 12)
    store.setValue('MonthlyCharges', 70)
    store.setValue('InternetService', 'Fiber optic')
    store.setValue('PaymentMethod', 'Electronic check')
    store.setValue('TechSupport', 'No')
    await flushPromises()
    await submit()
    const emitted = wrapper.emitted('submit')
    expect(emitted).toHaveLength(1)
    const values = emitted![0]![0] as Record<string, unknown>
    expect(Object.keys(values)).toHaveLength(19)
    for (const [name, value] of Object.entries(ADVANCED_DEFAULTS)) {
      expect(values[name]).toBe(value)
    }
    expect(values.TotalCharges).toBeNull()
  })

  it('錯誤訊息帶「!」圖示（不只靠顏色）', async () => {
    await submit()
    expect(wrapper.find('[data-field="Contract"] .field-error__icon').text()).toBe('!')
  })

  it.each([
    ['tenure', 80, '在網月數需為 0 至 72 的整數'],
    ['tenure', 10.5, '在網月數需為 0 至 72 的整數'],
    ['MonthlyCharges', 250, '月費需介於 0 至 200 之間'],
    ['TotalCharges', -5, '累計費用需為 0 以上的數字'],
    ['TotalCharges', 10001, '累計費用不可超過 10,000'],
  ] as const)('%s=%s 時不送出並顯示訊息', async (name, value, message) => {
    store.loadExample('high')
    store.setValue(name, value)
    await flushPromises()
    await submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(errorText(name)).toContain(message)
    expect(wrapper.find('.el-alert').text()).toContain('有 1 個欄位需要修正')
    expect((document.activeElement as HTMLElement).closest(`#field-${name}`)).not.toBeNull()
  })

  it('TotalCharges 留空可送出，送出整組 19 欄值', async () => {
    store.loadExample('high')
    await flushPromises()
    await submit()
    const emitted = wrapper.emitted('submit')
    expect(emitted).toHaveLength(1)
    const values = emitted![0]![0] as Record<string, unknown>
    expect(Object.keys(values)).toHaveLength(19)
    expect(values.TotalCharges).toBeNull()
    expect(wrapper.find('.el-alert').exists()).toBe(false)
  })

  it('按過預測後修正欄位，錯誤與摘要即時更新', async () => {
    await submit()
    expect(wrapper.find('.el-alert').text()).toContain('6')
    const internet = '[data-field="InternetService"] .el-form-item__error'
    expect(wrapper.find(internet).exists()).toBe(true)
    await pick('InternetService', 'DSL')
    await settle()
    expect(wrapper.find(internet).exists()).toBe(false)
    expect(store.errorCount).toBe(5)
  })

  it('錯誤全部修正後摘要消失，不顯示「有 0 個欄位」', async () => {
    store.loadExample('high')
    store.setValue('tenure', 80)
    await flushPromises()
    await submit()
    expect(wrapper.find('.el-alert').text()).toContain('有 1 個欄位需要修正')
    store.setValue('tenure', 5)
    await flushPromises()
    await settle()
    expect(store.errorCount).toBe(0)
    expect(store.showSummary).toBe(false)
    expect(wrapper.find('.el-alert').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('有 0 個欄位')
  })

  it('TotalCharges 留空且估算超過上限：不送出並顯示訊息', async () => {
    store.loadExample('high')
    store.setValue('tenure', 72)
    store.setValue('MonthlyCharges', 150)
    await flushPromises()
    await submit()
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(errorText('TotalCharges')).toContain('估算累計費用超過上限，請手動填寫')
    // 錯誤在進階欄位時自動展開，錯誤看得到
    const toggle = wrapper.find('.advanced-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-field="TotalCharges"]').isVisible()).toBe(true)

    // 手動收合後改基本欄位（錯誤欄位沒變），不會又自動展開
    await toggle.trigger('click')
    store.setValue('Contract', 'One year')
    await flushPromises()
    expect(toggle.attributes('aria-expanded')).toBe('false')
  })

  it('收合按鈕的 aria-controls 指到所有進階卡片', () => {
    const ids = wrapper.find('.advanced-toggle').attributes('aria-controls')!.split(' ')
    expect(ids.length).toBeGreaterThan(1)
    for (const id of ids) expect(wrapper.find(`#${id}`).exists()).toBe(true)
    expect(wrapper.find(`#${ids[0]} [data-field="gender"]`).exists()).toBe(true)
  })

  it('輸入欄位：在 tenure 輸入框打字後，值寫入 store', async () => {
    const input = wrapper.find<HTMLInputElement>('#field-tenure input')
    await input.setValue('12')
    await input.trigger('change')
    expect(store.values.tenure).toBe(12)
  })
})

describe('載入範例與清除', () => {
  it('載入範例走連動、填入表單、不自動預測', async () => {
    const buttons = wrapper.findAll('button').filter((b) => b.text().includes('範例'))
    expect(buttons.map((b) => b.text())).toEqual(['高風險範例', '低風險範例'])
    await buttons[1]!.trigger('click')
    expect(store.values).toEqual(getExample('low'))
    expect(radios('TechSupport')[0]!.element.value).toBe('No internet service')
    expect(radios('TechSupport')[0]!.element.disabled).toBe(true)
    expect(wrapper.emitted('submit')).toBeUndefined()

    await buttons[0]!.trigger('click')
    expect(store.values).toEqual(getExample('high'))
    expect(radios('MultipleLines').map((r) => r.element.value)).toEqual(['Yes', 'No'])
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('載入範例會清掉驗證錯誤', async () => {
    await submit()
    expect(wrapper.find('.el-form-item__error').exists()).toBe(true)
    await wrapper.findAll('button')[0]!.trigger('click')
    await settle()
    expect(wrapper.find('.el-alert').exists()).toBe(false)
    expect(wrapper.find('.el-form-item__error').exists()).toBe(false)
  })

  it('清除會回到初始狀態（基本欄位空白、進階欄位預設值）', async () => {
    store.loadExample('high')
    await flushPromises()
    const clear = wrapper.findAll('button').find((b) => b.text() === '清除')!
    await clear.trigger('click')
    expect(store.values).toEqual(createInitialValues())
  })
})

describe('無障礙與鍵盤（NFR-10）', () => {
  it('number 欄位以 aria-describedby 關聯說明小字與錯誤訊息', async () => {
    const total = () => wrapper.find('#field-TotalCharges input')
    expect(total().attributes('aria-describedby')).toBe('hint-TotalCharges')
    store.loadExample('high')
    store.setValue('TotalCharges', -1)
    await flushPromises()
    await submit()
    await flushPromises()
    expect(total().attributes('aria-describedby')).toBe('hint-TotalCharges error-TotalCharges')
    expect(wrapper.find('#error-TotalCharges').text()).toContain('累計費用需為 0 以上的數字')
    expect(wrapper.find('#field-tenure input').attributes('aria-describedby')).toBeUndefined()
  })

  it('select 與 radio 出錯時 aria-describedby 含錯誤訊息 id', async () => {
    await submit()
    expect(wrapper.find('#field-Contract input').attributes('aria-describedby')).toBe(
      'error-Contract',
    )
    expect(
      wrapper.find('#field-InternetService [role="radiogroup"]').attributes('aria-describedby'),
    ).toBe('error-InternetService')
  })

  it('radio group 以 aria-labelledby 指到欄位標籤', () => {
    const group = wrapper.find('#field-gender [role="radiogroup"]')
    const labelId = group.attributes('aria-labelledby')
    expect(labelId).toBeTruthy()
    expect(wrapper.find(`#${labelId}`).text()).toContain('性別')
  })

  it('所有可操作元素皆為原生控制項，且沒有正的 tabindex（Tab 順序依 DOM 順序）', () => {
    const tabindexes = wrapper
      .findAll('[tabindex]')
      .map((e) => Number(e.attributes('tabindex')))
      .filter((n) => n > 0)
    expect(tabindexes).toEqual([])
    expect(wrapper.findAll('input[type="radio"]').length).toBeGreaterThan(0)
    const submitButton = wrapper.findAll('button').find((b) => b.text() === '預測')!
    expect(submitButton.attributes('type')).toBe('submit')
  })

  it('預測按鈕在 form 內，可用 Enter 送出（原生隱式送出）', () => {
    const form = wrapper.find('form')
    expect(form.find('button[type="submit"]').exists()).toBe(true)
  })
})
