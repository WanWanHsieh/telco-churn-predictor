// 19 個特徵欄位定義（ui.md 3.2）。送出值一律為資料集原始值，畫面顯示「中文（原始值）」。

export const FEATURE_NAMES = [
  'gender',
  'SeniorCitizen',
  'Partner',
  'Dependents',
  'tenure',
  'PhoneService',
  'MultipleLines',
  'InternetService',
  'OnlineSecurity',
  'OnlineBackup',
  'DeviceProtection',
  'TechSupport',
  'StreamingTV',
  'StreamingMovies',
  'Contract',
  'PaperlessBilling',
  'PaymentMethod',
  'MonthlyCharges',
  'TotalCharges',
] as const

export type FeatureName = (typeof FEATURE_NAMES)[number]

/** 表單內的值：選擇型為原始值字串（SeniorCitizen 為 0/1 數字），數值型為 number，未填為 null */
export type FieldValue = string | number | null
export type FormValues = Record<FeatureName, FieldValue>
export type FieldErrors = Partial<Record<FeatureName, string>>

export type SectionId = 'A' | 'B' | 'C' | 'D'

export interface FieldOption {
  /** 送出值（資料集原始值） */
  value: string | number
  /** 中文名稱 */
  zh: string
  /** 畫面顯示：中文（原始值） */
  text: string
}

export interface NumberConfig {
  precision: number
  step: number
  prefix?: string
  suffix?: string
}

export interface FieldDef {
  name: FeatureName
  /** 中文標籤 */
  label: string
  section: SectionId
  control: 'radio' | 'select' | 'number'
  options: readonly FieldOption[]
  required: boolean
  /** 必填空白時的訊息 */
  requiredMessage: string
  /** 欄位下方固定小字 */
  hint?: string
  number?: NumberConfig
}

export const SECTIONS: readonly { id: SectionId; title: string }[] = [
  { id: 'A', title: '基本資料' },
  { id: 'B', title: '電話與網路服務' },
  { id: 'C', title: '合約與付款' },
  { id: 'D', title: '費用' },
]

export const RANGES = {
  tenure: { min: 0, max: 72 },
  MonthlyCharges: { min: 0, max: 200 },
  TotalCharges: { min: 0, max: 10000 },
} as const

export function opt(zh: string, value: string | number): FieldOption {
  return { value, zh, text: `${zh}（${value}）` }
}

const YES_NO = [opt('有', 'Yes'), opt('無', 'No')] as const

function radio(
  name: FeatureName,
  label: string,
  section: SectionId,
  options: readonly FieldOption[],
  requiredMessage: string,
): FieldDef {
  return { name, label, section, control: 'radio', options, required: true, requiredMessage }
}

function addon(name: FeatureName, label: string, requiredMessage: string): FieldDef {
  return radio(name, label, 'B', YES_NO, requiredMessage)
}

export const FIELDS: readonly FieldDef[] = [
  radio('gender', '性別', 'A', [opt('女', 'Female'), opt('男', 'Male')], '請選擇性別'),
  radio(
    'SeniorCitizen',
    '是否為年長者（65 歲以上）',
    'A',
    [opt('否', 0), opt('是', 1)],
    '請選擇是否為年長者',
  ),
  radio('Partner', '有無配偶', 'A', YES_NO, '請選擇有無配偶'),
  radio('Dependents', '有無撫養對象', 'A', YES_NO, '請選擇有無撫養對象'),
  {
    name: 'tenure',
    label: '在網月數',
    section: 'A',
    control: 'number',
    options: [],
    required: true,
    requiredMessage: '請輸入在網月數',
    number: { precision: 0, step: 1, suffix: '個月' },
  },
  radio('PhoneService', '電話服務', 'B', YES_NO, '請選擇是否有電話服務'),
  radio('MultipleLines', '多線電話', 'B', YES_NO, '請選擇是否有多線電話'),
  radio(
    'InternetService',
    '網路服務',
    'B',
    [opt('DSL', 'DSL'), opt('光纖', 'Fiber optic'), opt('無', 'No')],
    '請選擇網路服務類型',
  ),
  addon('OnlineSecurity', '線上安全服務', '請選擇是否有線上安全服務'),
  addon('OnlineBackup', '線上備份服務', '請選擇是否有線上備份服務'),
  addon('DeviceProtection', '裝置保護服務', '請選擇是否有裝置保護服務'),
  addon('TechSupport', '技術支援服務', '請選擇是否有技術支援服務'),
  addon('StreamingTV', '串流電視', '請選擇是否有串流電視'),
  addon('StreamingMovies', '串流電影', '請選擇是否有串流電影'),
  {
    name: 'Contract',
    label: '合約類型',
    section: 'C',
    control: 'select',
    options: [opt('月繳', 'Month-to-month'), opt('一年約', 'One year'), opt('兩年約', 'Two year')],
    required: true,
    requiredMessage: '請選擇合約類型',
  },
  radio(
    'PaperlessBilling',
    '電子帳單',
    'C',
    [opt('是', 'Yes'), opt('否', 'No')],
    '請選擇是否使用電子帳單',
  ),
  {
    name: 'PaymentMethod',
    label: '付款方式',
    section: 'C',
    control: 'select',
    options: [
      opt('電子支票', 'Electronic check'),
      opt('郵寄支票', 'Mailed check'),
      opt('銀行自動轉帳', 'Bank transfer (automatic)'),
      opt('信用卡自動扣款', 'Credit card (automatic)'),
    ],
    required: true,
    requiredMessage: '請選擇付款方式',
  },
  {
    name: 'MonthlyCharges',
    label: '月費',
    section: 'D',
    control: 'number',
    options: [],
    required: true,
    requiredMessage: '請輸入月費',
    number: { precision: 2, step: 1, prefix: '$' },
  },
  {
    name: 'TotalCharges',
    label: '累計費用（選填）',
    section: 'D',
    control: 'number',
    options: [],
    required: false,
    requiredMessage: '',
    hint: '不填寫時，系統會以「在網月數 × 月費」估算',
    number: { precision: 2, step: 1, prefix: '$' },
  },
]

const FIELD_MAP = new Map<FeatureName, FieldDef>(FIELDS.map((f) => [f.name, f]))

export function getField(name: FeatureName): FieldDef {
  const field = FIELD_MAP.get(name)
  if (!field) throw new Error(`未知欄位：${name}`)
  return field
}

export function fieldsOfSection(section: SectionId): FieldDef[] {
  return FIELDS.filter((f) => f.section === section)
}

export function createEmptyValues(): FormValues {
  return Object.fromEntries(FEATURE_NAMES.map((n) => [n, null])) as FormValues
}
