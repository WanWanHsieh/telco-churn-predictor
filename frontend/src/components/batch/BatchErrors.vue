<script setup lang="ts">
// 批次錯誤（ui.md 5.2，AC-6.6～6.8）：依錯誤碼顯示對應訊息，不顯示結果
import { computed } from 'vue'

import type { ApiError } from '../../api/client'
import { TEMPLATE_URL } from '../../api/batch'

const props = defineProps<{ error: ApiError | null; fileError: string | null }>()
defineEmits<{ retry: [] }>()

const MAX_SHOWN = 20

const kind = computed(() => {
  if (props.fileError) return 'not_csv'
  switch (props.error?.code) {
    case 'UNSUPPORTED_FILE_TYPE':
    case 'FILE_EMPTY':
      return 'not_csv'
    case 'MISSING_COLUMNS':
      return 'missing_columns'
    case 'INVALID_ROWS':
      return 'invalid_rows'
    case 'FILE_TOO_LARGE':
    case 'TOO_MANY_ROWS':
      return 'too_large'
    default:
      return props.error ? 'service' : null
  }
})

const missingColumns = computed(() =>
  (props.error?.details ?? []).map((d) => d.field).filter((f): f is string => !!f),
)

const totalErrors = computed(
  () => props.error?.metaNumber('total_errors') ?? props.error?.details.length ?? 0,
)

const invalidRowCount = computed(
  () =>
    props.error?.metaNumber('invalid_row_count') ??
    new Set((props.error?.details ?? []).map((d) => d.row)).size,
)

const shownDetails = computed(() => (props.error?.details ?? []).slice(0, MAX_SHOWN))
const remaining = computed(() => Math.max(totalErrors.value - shownDetails.value.length, 0))
</script>

<template>
  <div v-if="kind" class="batch-errors" data-testid="batch-errors">
    <el-alert
      v-if="kind === 'not_csv'"
      type="error"
      :closable="false"
      show-icon
      title="這不是有效的 CSV 檔案，請選擇副檔名為 .csv 且有內容的檔案。"
    />

    <el-alert
      v-else-if="kind === 'missing_columns'"
      type="error"
      :closable="false"
      show-icon
      :title="`缺少欄位：${missingColumns.join('、')}。請對照範本補齊後再上傳。`"
    >
      <a :href="TEMPLATE_URL" download>下載範本 CSV</a>
    </el-alert>

    <el-alert
      v-else-if="kind === 'too_large'"
      type="error"
      :closable="false"
      show-icon
      title="檔案超過上限，請拆分後再上傳。"
    />

    <template v-else-if="kind === 'invalid_rows'">
      <el-alert
        type="error"
        :closable="false"
        show-icon
        :title="`有 ${invalidRowCount} 列資料需要修正，整份檔案未進行預測`"
      />
      <table class="batch-errors__table">
        <thead>
          <tr>
            <th scope="col">列號</th>
            <th scope="col">欄位</th>
            <th scope="col">原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(d, i) in shownDetails" :key="i">
            <td>{{ d.row ?? '—' }}</td>
            <td>{{ d.field ?? '—' }}</td>
            <td>{{ d.reason }}</td>
          </tr>
          <tr v-if="remaining > 0" class="batch-errors__more">
            <td colspan="3">另有 {{ remaining }} 筆</td>
          </tr>
        </tbody>
      </table>
    </template>

    <div v-else-if="kind === 'service'" class="batch-errors__service" role="alert">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="服務暫時無法使用"
        description="系統目前無法完成預測，請稍後再試。"
      />
      <el-button type="primary" class="batch-errors__retry" @click="$emit('retry')">
        重試
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.batch-errors {
  margin-top: 16px;
}

.batch-errors__table {
  width: 100%;
  margin-top: 12px;
  border-collapse: collapse;
  font-size: 13px;
}

.batch-errors__table th,
.batch-errors__table td {
  padding: 6px 8px;
  border: 1px solid var(--el-border-color);
  text-align: left;
  overflow-wrap: anywhere;
}

.batch-errors__table th {
  background: var(--el-fill-color-light);
}

.batch-errors__more td {
  color: var(--el-text-color-secondary);
  text-align: center;
}

.batch-errors__retry {
  margin-top: 12px;
}
</style>
