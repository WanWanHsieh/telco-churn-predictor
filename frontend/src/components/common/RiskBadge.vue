<script setup lang="ts">
// 風險等級徽章：圖示＋文字＋顏色，不只靠顏色辨識（NFR-10）
import { computed } from 'vue'

import type { RiskLevel } from '../../api/predictions'
import { RISK_META } from '../../domain/risk'

const props = defineProps<{ level: RiskLevel }>()

const meta = computed(() => RISK_META[props.level])
</script>

<template>
  <span class="risk-badge" :class="`risk-badge--${level}`" :data-level="level">
    <span class="risk-badge__icon" aria-hidden="true">{{ meta.icon }}</span>
    {{ meta.label }}
  </span>
</template>

<style scoped>
.risk-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border: 1px solid;
  border-radius: 4px;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
}

.risk-badge--low {
  border-color: var(--risk-low-border);
  background: var(--risk-low-bg);
  color: var(--risk-low-text);
}

.risk-badge--medium {
  border-color: var(--risk-medium-border);
  background: var(--risk-medium-bg);
  color: var(--risk-medium-text);
}

.risk-badge--high {
  border-color: var(--risk-high-border);
  background: var(--risk-high-bg);
  color: var(--risk-high-text);
}
</style>
