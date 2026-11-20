<script setup lang="ts">
// 指標比較表（AC-3.1、3.4）：較佳者粗體（不靠顏色）、主要指標標籤、手機轉置
import { computed } from 'vue'

import type { DatasetInfo, ModelMetrics, ModelResult } from '../../api/metrics'
import { formatMetric, formatPercent } from '../../domain/format'

const props = defineProps<{ models: ModelResult[]; dataset: DatasetInfo; compact?: boolean }>()

interface MetricColumn {
  key: keyof ModelMetrics
  label: string
  primary?: boolean
}

const COLUMNS: MetricColumn[] = [
  { key: 'roc_auc', label: 'ROC-AUC', primary: true },
  { key: 'precision', label: 'Precision' },
  { key: 'recall', label: 'Recall', primary: true },
  { key: 'f1', label: 'F1' },
  { key: 'accuracy', label: 'Accuracy' },
]

/** 基準模型列在前（邏輯迴歸），主模型在後 */
const ordered = computed(() =>
  [...props.models].sort((a, b) =>
    a.key === 'logistic_regression' ? -1 : b.key === 'logistic_regression' ? 1 : 0,
  ),
)

function displayName(m: ModelResult): string {
  // API 的顯示名稱可能已含「基準」字樣，避免重複
  if (m.key !== 'logistic_regression' || m.display_name.includes('基準')) return m.display_name
  return `${m.display_name}（基準）`
}

/** 以顯示的 3 位小數比較；相同時皆不粗體 */
function isBest(m: ModelResult, key: keyof ModelMetrics): boolean {
  const values = props.models.map((x) => formatMetric(x.metrics[key]))
  const mine = formatMetric(m.metrics[key])
  const others = values.filter((v) => v !== mine)
  return others.length > 0 && others.every((v) => Number(mine) > Number(v))
}

const accuracyNote = computed(
  () =>
    `資料約 ${formatPercent(props.dataset.test_churn_rate)} 為流失，若全部猜「不流失」就有約 ` +
    `${formatPercent(props.dataset.majority_class_accuracy)} 的 Accuracy，所以本專案以 ROC-AUC 與 Recall 為主要指標。`,
)
</script>

<template>
  <div class="metrics-table">
    <h2 class="metrics-table__title">指標比較</h2>

    <!-- 桌機：列＝模型、欄＝指標 -->
    <div v-if="!compact" class="metrics-table__scroll">
      <table class="mt" data-layout="models-by-metrics">
        <thead>
          <tr>
            <th scope="col">模型</th>
            <th v-for="c in COLUMNS" :key="c.key" scope="col">
              {{ c.label }}
              <el-tag v-if="c.primary" size="small" type="info" class="mt__tag">主要指標</el-tag>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in ordered" :key="m.key" :data-model="m.key">
            <th scope="row">{{ displayName(m) }}</th>
            <td
              v-for="c in COLUMNS"
              :key="c.key"
              :class="{ 'is-best': isBest(m, c.key) }"
              :data-metric="c.key"
            >
              {{ formatMetric(m.metrics[c.key]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 手機：列＝指標、欄＝模型 -->
    <table v-else class="mt" data-layout="metrics-by-models">
      <thead>
        <tr>
          <th scope="col">指標</th>
          <th v-for="m in ordered" :key="m.key" scope="col">{{ displayName(m) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in COLUMNS" :key="c.key">
          <th scope="row">
            {{ c.label }}
            <el-tag v-if="c.primary" size="small" type="info" class="mt__tag">主要指標</el-tag>
          </th>
          <td
            v-for="m in ordered"
            :key="m.key"
            :class="{ 'is-best': isBest(m, c.key) }"
            :data-model="m.key"
            :data-metric="c.key"
          >
            {{ formatMetric(m.metrics[c.key]) }}
          </td>
        </tr>
      </tbody>
    </table>

    <p class="metrics-table__hint">粗體為該指標較佳者</p>
    <p class="metrics-table__note" data-testid="accuracy-note">{{ accuracyNote }}</p>
  </div>
</template>

<style scoped>
.metrics-table__title {
  margin: 0 0 12px;
  font-size: 16px;
}

.metrics-table__scroll {
  overflow-x: auto;
}

.mt {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-variant-numeric: tabular-nums;
}

.mt th,
.mt td {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  text-align: right;
}

.mt th[scope='row'],
.mt thead th:first-child {
  text-align: left;
}

.mt thead th {
  background: var(--el-fill-color-light);
  font-weight: 600;
  white-space: nowrap;
}

.mt td.is-best {
  font-weight: 700;
}

.mt__tag {
  margin-left: 4px;
}

.metrics-table__hint,
.metrics-table__note {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
