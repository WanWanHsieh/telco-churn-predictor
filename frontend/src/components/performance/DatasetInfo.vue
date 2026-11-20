<script setup lang="ts">
// 資料說明區（AC-3.3）：筆數、流失比例、決策門檻、訓練日期
import { computed } from 'vue'

import type { MetricsResponse } from '../../api/metrics'
import { formatPercent } from '../../domain/format'

const props = defineProps<{ metrics: MetricsResponse; compact?: boolean }>()

const n = (x: number) => x.toLocaleString('en-US')
const trainedDate = computed(() => props.metrics.trained_at.slice(0, 10))

const items = computed(() => {
  const d = props.metrics.dataset
  return [
    { label: '訓練集筆數', value: `${n(d.train_size)}（另有驗證集 ${n(d.validation_size)} 筆）` },
    { label: '測試集筆數', value: n(d.test_size) },
    { label: '測試集流失比例', value: formatPercent(d.test_churn_rate) },
    { label: '決策門檻值', value: props.metrics.decision_threshold.toFixed(2) },
    { label: '模型訓練日期', value: trainedDate.value },
  ]
})
</script>

<template>
  <el-descriptions class="dataset-info" :column="compact ? 1 : 3" border title="資料說明">
    <el-descriptions-item v-for="item in items" :key="item.label" :label="item.label">
      <span class="dataset-info__value">{{ item.value }}</span>
    </el-descriptions-item>
  </el-descriptions>
</template>

<style scoped>
.dataset-info__value {
  font-variant-numeric: tabular-nums;
}
</style>
