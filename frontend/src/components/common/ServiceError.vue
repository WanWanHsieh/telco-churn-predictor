<script setup lang="ts">
// 服務錯誤框（ui.md 3.3）：不顯示堆疊或路徑；技術細節預設收合，只給開發者看
import type { ApiError } from '../../api/client'

withDefaults(
  defineProps<{
    error: ApiError
    title?: string
    message?: string
  }>(),
  {
    title: '服務暫時無法使用',
    message: '系統目前無法完成預測，您填寫的資料仍保留。請稍後再試，若持續發生請通知管理者。',
  },
)

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="service-error" role="alert">
    <h2 class="service-error__title">
      <span class="service-error__icon" aria-hidden="true">!</span>{{ title }}
    </h2>
    <p class="service-error__message">{{ message }}</p>
    <el-button type="primary" native-type="button" @click="$emit('retry')">重試</el-button>
    <details class="service-error__details">
      <summary>技術細節</summary>
      <dl>
        <dt>錯誤碼</dt>
        <dd>{{ error.code }}</dd>
        <template v-if="error.status !== null">
          <dt>HTTP 狀態</dt>
          <dd>{{ error.status }}</dd>
        </template>
        <template v-if="error.requestId">
          <dt>Request ID</dt>
          <dd>{{ error.requestId }}</dd>
        </template>
      </dl>
    </details>
  </div>
</template>

<style scoped>
.service-error {
  padding: 24px 16px;
  border: 1px solid var(--risk-medium-border);
  border-radius: 4px;
  background: #fff;
  text-align: center;
}

.service-error__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
}

.service-error__icon {
  display: inline-grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 50%;
  background: var(--risk-medium-text);
  color: #fff;
  font-size: 14px;
}

.service-error__message {
  margin: 8px 0 16px;
  color: var(--el-text-color-secondary);
}

.service-error__details {
  margin-top: 16px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: left;
}

.service-error__details dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 12px;
  margin: 8px 0 0;
}

.service-error__details dd {
  margin: 0;
  word-break: break-all;
}
</style>
