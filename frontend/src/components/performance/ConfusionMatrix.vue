<script setup lang="ts">
// 混淆矩陣（AC-3.2）：HTML 2×2，顏色只表示數量深淺，意義靠文字；手機改為格外圖例
import { computed } from 'vue'

import type { ConfusionMatrixData } from '../../api/metrics'
import { formatPercent } from '../../domain/format'

const props = defineProps<{ matrix: ConfusionMatrixData; modelName: string; compact?: boolean }>()

type CellKey = keyof ConfusionMatrixData

const MEANING: Record<CellKey, string> = {
  tn: '實際未流失、預測未流失',
  fp: '實際未流失、預測流失',
  fn: '實際流失、預測未流失',
  tp: '實際流失、預測流失',
}

const total = computed(() => props.matrix.tn + props.matrix.fp + props.matrix.fn + props.matrix.tp)
const max = computed(() =>
  Math.max(props.matrix.tn, props.matrix.fp, props.matrix.fn, props.matrix.tp),
)

function cell(key: CellKey) {
  const count = props.matrix[key]
  return {
    key,
    count,
    share: total.value ? formatPercent(count / total.value) : '0%',
    meaning: MEANING[key],
    // 數量越多底色越深（藍色系，與風險色分開）
    alpha: max.value ? 0.08 + (count / max.value) * 0.5 : 0.08,
  }
}

const rows = computed(() => [
  { label: '實際未流失', cells: [cell('tn'), cell('fp')] },
  { label: '實際流失', cells: [cell('fn'), cell('tp')] },
])
</script>

<template>
  <figure class="cm">
    <figcaption class="cm__title">混淆矩陣（{{ modelName }}，測試集）</figcaption>
    <table class="cm__table">
      <thead>
        <tr>
          <th scope="col"><span class="cm__axis">實際 ＼ 預測</span></th>
          <th scope="col">預測未流失</th>
          <th scope="col">預測流失</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.label">
          <th scope="row">{{ row.label }}</th>
          <td
            v-for="c in row.cells"
            :key="c.key"
            class="cm__cell"
            :data-cell="c.key"
            :style="{ backgroundColor: `rgba(37, 99, 235, ${c.alpha.toFixed(2)})` }"
          >
            <strong class="cm__count">{{ c.count.toLocaleString('en-US') }}</strong>
            <span class="cm__share">{{ c.share }}</span>
            <span v-if="!compact" class="cm__meaning">{{ c.meaning }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <ul v-if="compact" class="cm__legend">
      <li v-for="key in ['tn', 'fp', 'fn', 'tp'] as CellKey[]" :key="key">
        {{ MEANING[key] }}：{{ matrix[key].toLocaleString('en-US') }}
      </li>
    </ul>
  </figure>
</template>

<style scoped>
.cm {
  margin: 0;
}

.cm__title {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.cm__table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-variant-numeric: tabular-nums;
}

.cm__table th,
.cm__table td {
  padding: 10px 8px;
  border: 1px solid var(--el-border-color);
  text-align: center;
}

.cm__table thead th,
.cm__table th[scope='row'] {
  background: var(--el-fill-color-light);
  font-size: 13px;
  font-weight: 600;
}

.cm__axis {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.cm__cell {
  height: 96px;
}

.cm__count {
  display: block;
  font-size: 22px;
}

.cm__share {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.cm__meaning {
  display: block;
  margin-top: 4px;
  font-size: 12px;
}

.cm__legend {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
