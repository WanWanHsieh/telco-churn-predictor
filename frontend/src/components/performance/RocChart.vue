<script setup lang="ts">
// ROC 曲線（AC-3.2）：兩模型疊圖＋隨機基準對角線；實線／虛線＋不同標記，不只靠顏色
import {
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import { computed } from 'vue'
import { Line } from 'vue-chartjs'

import type { ModelResult } from '../../api/metrics'
import { formatMetric } from '../../domain/format'

ChartJS.register(LineElement, PointElement, LinearScale, Legend, Tooltip)

const props = defineProps<{ models: ModelResult[] }>()

const STYLE = {
  keras_mlp: { color: '#2563eb', dash: [] as number[], point: 'circle' as const },
  logistic_regression: { color: '#6b7280', dash: [8, 4], point: 'triangle' as const },
}

function points(m: ModelResult) {
  return m.roc_curve.fpr.map((x, i) => ({ x, y: m.roc_curve.tpr[i] ?? 0 }))
}

function legendLabel(m: ModelResult): string {
  return `${m.display_name}（AUC ${formatMetric(m.metrics.roc_auc)}）`
}

const chartData = computed<ChartData<'line', { x: number; y: number }[]>>(() => ({
  datasets: [
    ...props.models.map((m) => ({
      label: legendLabel(m),
      data: points(m),
      borderColor: STYLE[m.key].color,
      backgroundColor: STYLE[m.key].color,
      borderDash: STYLE[m.key].dash,
      borderWidth: 2,
      pointStyle: STYLE[m.key].point,
      pointRadius: (ctx: { dataIndex: number }) => (ctx.dataIndex % 20 === 0 ? 4 : 0),
      tension: 0,
    })),
    {
      label: '隨機猜測',
      data: [
        { x: 0, y: 0 },
        { x: 1, y: 1 },
      ],
      borderColor: '#9ca3af',
      backgroundColor: '#9ca3af',
      borderDash: [2, 4],
      borderWidth: 1,
      pointRadius: 0,
    },
  ],
}))

const options: ChartOptions<'line'> = {
  responsive: true,
  maintainAspectRatio: true,
  aspectRatio: 1,
  animation: false,
  scales: {
    x: {
      type: 'linear',
      min: 0,
      max: 1,
      title: { display: true, text: '偽陽性率（False Positive Rate）' },
      ticks: { font: { size: 12 } },
    },
    y: {
      type: 'linear',
      min: 0,
      max: 1,
      title: { display: true, text: '真陽性率（True Positive Rate）' },
      ticks: { font: { size: 12 } },
    },
  },
  plugins: {
    legend: { position: 'bottom', labels: { usePointStyle: true, font: { size: 12 } } },
    tooltip: { mode: 'nearest', intersect: false },
  },
}

const ariaLabel = computed(
  () => `ROC 曲線：${props.models.map(legendLabel).join('、')}，對角線為隨機猜測基準`,
)
</script>

<template>
  <figure class="roc">
    <figcaption class="roc__title">ROC 曲線（測試集）</figcaption>
    <div class="roc__canvas" role="img" :aria-label="ariaLabel">
      <Line :data="chartData" :options="options" />
    </div>
    <el-collapse class="roc__table">
      <el-collapse-item title="資料表檢視" name="table">
        <table class="roc__data">
          <thead>
            <tr>
              <th scope="col">偽陽性率</th>
              <th v-for="m in models" :key="m.key" scope="col">{{ m.display_name }} 真陽性率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(x, i) in models[0]?.roc_curve.fpr ?? []" :key="i" v-show="i % 10 === 0">
              <td>{{ x.toFixed(2) }}</td>
              <td v-for="m in models" :key="m.key">{{ (m.roc_curve.tpr[i] ?? 0).toFixed(3) }}</td>
            </tr>
          </tbody>
        </table>
      </el-collapse-item>
    </el-collapse>
  </figure>
</template>

<style scoped>
.roc {
  margin: 0;
}

.roc__title {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.roc__canvas {
  position: relative;
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
}

.roc__table {
  margin-top: 12px;
}

.roc__data {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.roc__data th,
.roc__data td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  text-align: right;
}
</style>
