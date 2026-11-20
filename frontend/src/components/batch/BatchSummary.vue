<script setup lang="ts">
// 摘要 4 卡（AC-6.5）：總筆數與各風險筆數，風險以徽章（圖示＋文字）呈現
import type { BatchSummary } from '../../api/batch'
import type { RiskLevel } from '../../api/predictions'
import RiskBadge from '../common/RiskBadge.vue'

defineProps<{ summary: BatchSummary }>()

const LEVELS: RiskLevel[] = ['high', 'medium', 'low']
</script>

<template>
  <ul class="batch-summary" aria-label="預測摘要">
    <li class="batch-summary__card" data-card="total">
      <span class="batch-summary__label">總筆數</span>
      <strong class="batch-summary__value">{{ summary.total.toLocaleString('en-US') }}</strong>
    </li>
    <li v-for="level in LEVELS" :key="level" class="batch-summary__card" :data-card="level">
      <RiskBadge :level="level" />
      <strong class="batch-summary__value">{{ summary[level].toLocaleString('en-US') }} 筆</strong>
    </li>
  </ul>
  <p v-if="summary.estimated_total_charges > 0" class="batch-summary__note">
    其中
    {{ summary.estimated_total_charges.toLocaleString('en-US') }} 筆的累計費用未填寫，已以在網月數 ×
    月費估算。
  </p>
</template>

<style scoped>
.batch-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.batch-summary__card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
  padding: 12px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #fff;
}

.batch-summary__label {
  color: var(--el-text-color-secondary);
  font-size: 15px;
  font-weight: 600;
}

.batch-summary__value {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
}

.batch-summary__note {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

@media (max-width: 767px) {
  .batch-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
