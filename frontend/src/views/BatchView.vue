<script setup lang="ts">
// 批次預測頁（ui.md 第 5 節）：同一頁三階段（上傳 → 處理中 → 結果）
import { ElMessage } from 'element-plus'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { TEMPLATE_FILENAME, TEMPLATE_URL } from '../api/batch'
import BatchErrors from '../components/batch/BatchErrors.vue'
import BatchResultTable from '../components/batch/BatchResultTable.vue'
import BatchSummary from '../components/batch/BatchSummary.vue'
import BatchUpload from '../components/batch/BatchUpload.vue'
import { buildResultCsv, downloadText } from '../domain/csv'
import { useBatchStore } from '../stores/batch'

const store = useBatchStore()

const compact = ref(false)
let media: MediaQueryList | undefined
const syncCompact = () => (compact.value = media?.matches ?? false)

onMounted(() => {
  media = window.matchMedia?.('(max-width: 767px)')
  syncCompact()
  media?.addEventListener?.('change', syncCompact)
  void store.loadLimits()
})
onBeforeUnmount(() => media?.removeEventListener?.('change', syncCompact))

const RESULT_FILENAME = 'churn_batch_result.csv'

function downloadResult(): void {
  if (!store.response) return
  downloadText(buildResultCsv(store.response), RESULT_FILENAME)
  ElMessage.success({ message: `已下載 ${RESULT_FILENAME}`, duration: 3000 })
}
</script>

<template>
  <section class="batch-view">
    <h1 class="batch-view__title">批次預測</h1>

    <template v-if="store.stage !== 'result'">
      <p class="batch-view__lead">
        上傳顧客名單 CSV，一次取得每位顧客的流失風險。欄位需與單筆預測相同（共 19 欄），可另加
        customerID 欄位以便對照。
      </p>
      <p class="batch-view__template">
        <a :href="TEMPLATE_URL" :download="TEMPLATE_FILENAME" class="batch-view__link">
          下載範本 CSV
        </a>
      </p>
      <el-card shadow="never">
        <BatchUpload />
        <BatchErrors :error="store.error" :file-error="store.fileError" @retry="store.submit()" />
      </el-card>
    </template>

    <template v-else-if="store.response">
      <BatchSummary :summary="store.response.summary" />
      <el-card shadow="never">
        <BatchResultTable :compact="compact">
          <template #actions>
            <div class="batch-view__actions">
              <el-button type="primary" @click="downloadResult">下載結果 CSV</el-button>
              <el-button @click="store.restart()">重新上傳</el-button>
            </div>
          </template>
        </BatchResultTable>
      </el-card>
    </template>

    <p class="batch-view__privacy">上傳的內容不會被儲存</p>
  </section>
</template>

<style scoped>
.batch-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 960px;
  margin: 0 auto;
}

.batch-view__title {
  margin: 0;
  font-size: 22px;
}

.batch-view__lead,
.batch-view__template {
  margin: 0;
}

.batch-view__link {
  color: var(--el-color-primary);
}

.batch-view__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.batch-view__privacy {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
