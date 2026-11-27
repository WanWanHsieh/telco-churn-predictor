<script setup lang="ts">
import { nextTick, onMounted, onUpdated, ref, watch } from 'vue'

import { getLockState, ruleFor } from '../../domain/dependencies'
import type { ExampleKind } from '../../domain/examples'
import {
  FEATURE_NAMES,
  advancedSections,
  basicFields,
  getField,
  isBasicField,
  type FeatureName,
  type FieldDef,
  type FieldOption,
  type FieldValue,
  type FormValues,
} from '../../domain/fields'
import { errorFieldsInOrder } from '../../domain/validation'
import { usePredictionStore } from '../../stores/prediction'

// 驗證通過後送出整組表單值；呼叫 API 由上層（T9）處理
const emit = defineEmits<{ submit: [values: FormValues] }>()
// 送出中：按鈕 loading、所有欄位暫時 disabled，避免中途修改（ui.md 3.3）
const props = withDefaults(defineProps<{ loading?: boolean }>(), { loading: false })

const store = usePredictionStore()
const rootRef = ref<HTMLElement | null>(null)

interface FieldBlock {
  key: string
  title: string
  fields: FieldDef[]
  advanced: boolean
}

// 基本欄位一個區塊；其餘欄位依原區塊分組，收在「進階欄位」裡（預設收合）
const advancedBlocks = advancedSections().map((s) => ({
  key: s.id,
  title: s.title,
  fields: s.fields,
  advanced: true,
}))
const blocks: FieldBlock[] = [
  { key: 'basic', title: '基本欄位', fields: basicFields(), advanced: false },
  ...advancedBlocks,
]
const firstAdvancedKey = advancedBlocks[0]?.key
const advancedFieldCount = advancedBlocks.reduce((n, b) => n + b.fields.length, 0)
const advancedOpen = ref(false)
/** 收合按鈕控制的所有進階卡片 id（aria-controls 可列多個） */
const advancedIds = advancedBlocks.map((b) => advancedId(b.key)).join(' ')

function advancedId(key: string): string {
  return `advanced-${key}`
}

// 進階欄位「出現新的錯誤」時（例如累計費用估算超限、API 回 422）自動展開；
// 錯誤欄位沒變時不重複展開，使用者手動收合後改基本欄位不會又被打開
watch(
  () =>
    FEATURE_NAMES.filter((n) => store.errors[n] && !isBasicField(n))
      .sort()
      .join(','),
  (now, before) => {
    if (now && now !== before) advancedOpen.value = true
  },
)

function lockState(name: FeatureName) {
  return getLockState(name, store.values)
}

/** 被鎖定時只顯示固定值（無電話服務／無網路服務） */
function optionsOf(field: FieldDef): readonly FieldOption[] {
  if (lockState(field.name) === 'locked') {
    const rule = ruleFor(field.name)
    if (rule) return [rule.lockedOption]
  }
  return field.options
}

function hintOf(field: FieldDef): string | undefined {
  const rule = ruleFor(field.name)
  const state = lockState(field.name)
  if (rule && state === 'locked') return rule.lockedHint
  if (rule && state === 'waiting') return rule.waitingHint
  return field.hint
}

function hintId(name: FeatureName): string {
  return `hint-${name}`
}

function errorId(name: FeatureName): string {
  return `error-${name}`
}

/** 欄位說明小字與錯誤訊息的 id，供 aria-describedby 關聯到輸入元件 */
function describedBy(field: FieldDef): string | undefined {
  const ids: string[] = []
  if (hintOf(field)) ids.push(hintId(field.name))
  if (store.errors[field.name]) ids.push(errorId(field.name))
  return ids.length > 0 ? ids.join(' ') : undefined
}

/** el-select／el-input-number 不會把 aria-describedby 傳到內部 input，渲染後直接設在 input 上 */
function syncDescribedBy(): void {
  for (const name of FEATURE_NAMES) {
    const field = getField(name)
    if (field.control === 'radio') continue
    const input = rootRef.value?.querySelector(`#field-${name} input`)
    if (!input) continue
    const ids = describedBy(field)
    if (ids) input.setAttribute('aria-describedby', ids)
    else input.removeAttribute('aria-describedby')
  }
}

onMounted(syncDescribedBy)
onUpdated(syncDescribedBy)

function onChange(name: FeatureName, value: FieldValue | undefined): void {
  store.setValue(name, value)
}

function loadExample(kind: ExampleKind): void {
  store.loadExample(kind)
}

function onClear(): void {
  store.reset()
  ElMessage({ message: '已清除', type: 'success', duration: 3000 })
}

/** 驗證失敗時，把焦點移到畫面順序第一個有錯、且可操作的欄位 */
async function focusFirstError(): Promise<void> {
  await nextTick()
  for (const name of errorFieldsInOrder(store.errors)) {
    const el = rootRef.value?.querySelector<HTMLElement>(`#field-${name} input:not([disabled])`)
    if (el) {
      el.focus()
      return
    }
  }
}

async function onSubmit(): Promise<void> {
  if (props.loading) return
  if (!store.validate()) {
    await focusFirstError()
    return
  }
  emit('submit', store.payload())
}
</script>

<template>
  <div ref="rootRef" class="predict-form">
    <div class="predict-form__intro">
      <p class="predict-form__required-note">只要填寫標示 * 的基本欄位即可預測</p>
      <div class="predict-form__examples" role="group" aria-label="載入範例">
        <span class="predict-form__examples-label">載入範例：</span>
        <el-button native-type="button" plain :disabled="loading" @click="loadExample('high')"
          >高風險範例</el-button
        >
        <el-button native-type="button" plain :disabled="loading" @click="loadExample('low')"
          >低風險範例</el-button
        >
      </div>
    </div>

    <el-alert
      v-if="store.showSummary"
      class="predict-form__summary"
      type="error"
      show-icon
      :title="`有 ${store.errorCount} 個欄位需要修正，請查看標示的欄位`"
      @close="store.dismissSummary()"
    />

    <el-form label-position="top" novalidate @submit.prevent="onSubmit">
      <template v-for="block in blocks" :key="block.key">
        <button
          v-if="block.key === firstAdvancedKey"
          type="button"
          class="advanced-toggle"
          :aria-controls="advancedIds"
          :aria-expanded="advancedOpen"
          @click="advancedOpen = !advancedOpen"
        >
          <span class="advanced-toggle__title">
            <span aria-hidden="true">{{ advancedOpen ? '▾' : '▸' }}</span>
            進階欄位（選填，{{ advancedFieldCount }} 欄）
          </span>
          <span class="advanced-toggle__hint">未修改時，以資料集中最常見的值帶入</span>
        </button>
        <el-card
          v-show="!block.advanced || advancedOpen"
          :id="block.advanced ? advancedId(block.key) : undefined"
          class="form-section"
          :class="{ 'form-section--advanced': block.advanced }"
          shadow="never"
        >
          <template #header>
            <h2 class="form-section__title">{{ block.title }}</h2>
          </template>
          <el-row :gutter="16">
            <el-col v-for="field in block.fields" :key="field.name" :xs="24" :sm="12">
              <el-form-item
                :required="field.required && !block.advanced"
                :error="store.errors[field.name]"
                :data-field="field.name"
              >
                <template #label>
                  <span>{{ field.label }}</span>
                  <span class="field-en" lang="en">{{ field.name }}</span>
                  <span v-if="lockState(field.name) === 'locked'" class="field-auto">自動設定</span>
                </template>

                <div :id="`field-${field.name}`" class="field-control">
                  <el-radio-group
                    v-if="field.control === 'radio'"
                    class="field-radio"
                    :model-value="store.values[field.name] ?? undefined"
                    :disabled="loading || lockState(field.name) !== 'free'"
                    :aria-describedby="describedBy(field)"
                    @update:model-value="(v: unknown) => onChange(field.name, v as FieldValue)"
                  >
                    <el-radio-button v-for="o in optionsOf(field)" :key="o.value" :value="o.value">
                      {{ o.text }}
                    </el-radio-button>
                  </el-radio-group>

                  <el-select
                    v-else-if="field.control === 'select'"
                    placeholder="請選擇"
                    :disabled="loading"
                    :model-value="store.values[field.name] ?? undefined"
                    @update:model-value="(v: FieldValue) => onChange(field.name, v)"
                  >
                    <el-option
                      v-for="o in field.options"
                      :key="o.value"
                      :label="o.text"
                      :value="o.value"
                    />
                  </el-select>

                  <el-input-number
                    v-else
                    class="field-number"
                    controls-position="right"
                    :disabled="loading"
                    :model-value="(store.values[field.name] as number | null) ?? undefined"
                    :precision="field.number?.precision"
                    :step="field.number?.step"
                    :value-on-clear="null"
                    @update:model-value="(v: number | null | undefined) => onChange(field.name, v)"
                  >
                    <template v-if="field.number?.prefix" #prefix>{{
                      field.number.prefix
                    }}</template>
                    <template v-if="field.number?.suffix" #suffix>{{
                      field.number.suffix
                    }}</template>
                  </el-input-number>
                </div>

                <p v-if="hintOf(field)" :id="hintId(field.name)" class="field-hint">
                  {{ hintOf(field) }}
                </p>

                <template #error="{ error }">
                  <div :id="errorId(field.name)" class="el-form-item__error field-error">
                    <span class="field-error__icon" aria-hidden="true">!</span>{{ error }}
                  </div>
                </template>
              </el-form-item>
            </el-col>
          </el-row>
        </el-card>
      </template>

      <div class="form-actions">
        <el-button native-type="button" size="large" plain :disabled="loading" @click="onClear">
          清除
        </el-button>
        <el-button
          type="primary"
          size="large"
          native-type="submit"
          :loading="loading"
          :disabled="loading"
        >
          {{ loading ? '預測中…' : '預測' }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.predict-form {
  min-width: 0;
}

.predict-form__intro {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 12px;
}

.predict-form__required-note {
  margin: 0;
  color: var(--el-text-color-secondary);
}

.predict-form__examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.predict-form__examples .el-button {
  margin-left: 0;
}

.predict-form__summary {
  margin-bottom: 12px;
}

.advanced-toggle {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 4px 16px;
  width: 100%;
  margin-bottom: 16px;
  padding: 12px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  background: var(--el-bg-color);
  color: var(--el-text-color-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.advanced-toggle:hover {
  border-color: var(--el-color-primary-light-5);
}

.advanced-toggle:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.advanced-toggle__title {
  display: inline-flex;
  gap: 8px;
  font-weight: 500;
}

.advanced-toggle__hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.form-section {
  margin-bottom: 16px;
}

.form-section__title {
  font-size: 16px;
}

.field-en {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 400;
}

.field-auto {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 4px;
  background: #e5e7eb;
  color: var(--el-text-color-primary);
  font-size: 12px;
}

.field-control {
  width: 100%;
}

.field-hint {
  width: 100%;
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}

/* 沿用 Element 的錯誤樣式類別，但改為文件流內，避免蓋住欄位說明文字 */
.field-error {
  position: static;
  padding-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--risk-high-text);
}

.field-error__icon {
  display: inline-flex;
  width: 14px;
  height: 14px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--risk-high-text);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

.field-number {
  width: 100%;
}

.field-control :deep(.el-select) {
  width: 100%;
}

/* 單選按鈕：各自獨立、間距 8px、換行，觸控高度 >= 44px（手機） */
.field-radio {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.field-radio :deep(.el-radio-button__inner) {
  min-height: 32px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  box-shadow: none;
}

.field-radio :deep(.el-radio-button.is-active .el-radio-button__inner) {
  border-color: var(--el-color-primary);
  box-shadow: none;
}

.field-radio :deep(.el-radio-button__original-radio:focus-visible + .el-radio-button__inner) {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.form-actions .el-button {
  margin-left: 0;
}

@media (max-width: 767px) {
  .field-radio :deep(.el-radio-button__inner),
  .form-actions .el-button {
    min-height: 44px;
  }

  /* 手機：預測按鈕固定在表單底部、全寬 */
  .form-actions {
    position: sticky;
    bottom: 0;
    z-index: 10;
    margin: 0 -16px;
    padding: 8px 16px;
    border-top: 1px solid var(--el-border-color);
    background: #fff;
  }

  .form-actions .el-button--primary {
    flex: 1;
  }
}
</style>
