<script setup lang="ts">
// 階段 A／B：選擇檔案、開始預測（處理中時上傳區與按鈕 disabled，AC-6.10）
import type { UploadFile } from 'element-plus'
import { computed } from 'vue'

import { formatBytes } from '../../api/meta'
import { useBatchStore } from '../../stores/batch'

const store = useBatchStore()
const processing = computed(() => store.stage === 'processing')

const limitText = computed(() =>
  store.limits
    ? `檔案格式：CSV，上限 ${formatBytes(store.limits.max_file_bytes)} 或 ${store.limits.max_rows.toLocaleString('en-US')} 列`
    : '檔案格式：CSV',
)

function onChange(uploadFile: UploadFile): void {
  store.selectFile(uploadFile.raw ?? null)
}

function fileSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`
}
</script>

<template>
  <div class="batch-upload">
    <el-upload
      drag
      accept=".csv,text/csv"
      :limit="1"
      :auto-upload="false"
      :show-file-list="false"
      :disabled="processing"
      :on-change="onChange"
      :on-exceed="(files: File[]) => store.selectFile(files[0] ?? null)"
    >
      <p class="batch-upload__text">將 CSV 檔拖曳到此，或按一下選擇檔案</p>
      <p class="batch-upload__limit">{{ limitText }}</p>
    </el-upload>

    <div v-if="store.file" class="batch-upload__file" data-testid="selected-file">
      <span class="batch-upload__name">{{ store.file.name }}</span>
      <span class="batch-upload__size">{{ fileSize(store.file.size) }}</span>
      <el-button link type="primary" :disabled="processing" @click="store.selectFile(null)">
        移除
      </el-button>
    </div>

    <div class="batch-upload__actions">
      <el-button
        type="primary"
        size="large"
        :disabled="!store.file || processing"
        :loading="processing"
        @click="store.submit()"
      >
        {{ processing ? '預測中…' : '開始預測' }}
      </el-button>
    </div>

    <div v-if="processing" class="batch-upload__progress" role="status">
      <p>正在預測，請稍候…</p>
      <el-progress :percentage="100" :indeterminate="true" :show-text="false" :duration="2" />
    </div>
  </div>
</template>

<style scoped>
.batch-upload__text {
  margin: 0;
  font-size: 15px;
}

.batch-upload__limit {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.batch-upload__file {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}

.batch-upload__name {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.batch-upload__size {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.batch-upload__actions {
  margin-top: 16px;
}

.batch-upload__progress {
  margin-top: 16px;
}

.batch-upload__progress p {
  margin: 0 0 8px;
}
</style>
