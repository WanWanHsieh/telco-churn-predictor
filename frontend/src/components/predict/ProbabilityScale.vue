<script setup lang="ts">
// 機率尺（ui.md 3.4）：0–100% 三段，切點刻度與指針；文字標示不靠顏色
import { computed } from 'vue'

import type { RiskThresholds } from '../../api/predictions'
import { formatPercent, formatProbability } from '../../domain/format'

const props = defineProps<{ probability: number; thresholds: RiskThresholds }>()

const pct = (x: number) => `${Math.min(Math.max(x, 0), 1) * 100}%`
const label = computed(
  () =>
    `機率尺：目前 ${formatProbability(props.probability)}，` +
    `低風險未滿 ${formatPercent(props.thresholds.medium)}，` +
    `高風險 ${formatPercent(props.thresholds.high)} 以上`,
)
</script>

<template>
  <div class="scale" role="img" :aria-label="label">
    <div class="scale__track">
      <span class="scale__seg scale__seg--low" :style="{ width: pct(thresholds.medium) }" />
      <span
        class="scale__seg scale__seg--medium"
        :style="{ width: pct(thresholds.high - thresholds.medium) }"
      />
      <span class="scale__seg scale__seg--high" :style="{ flex: 1 }" />
      <span class="scale__pointer" :style="{ left: pct(probability) }" aria-hidden="true">▼</span>
    </div>
    <div class="scale__ticks" aria-hidden="true">
      <span class="scale__tick" style="left: 0">0%</span>
      <span class="scale__tick" :style="{ left: pct(thresholds.medium) }">
        {{ formatPercent(thresholds.medium) }}
      </span>
      <span class="scale__tick" :style="{ left: pct(thresholds.high) }">
        {{ formatPercent(thresholds.high) }}
      </span>
      <span class="scale__tick scale__tick--end" style="left: 100%">100%</span>
    </div>
    <div class="scale__legend" aria-hidden="true">
      <span>低</span>
      <span>中</span>
      <span>高</span>
    </div>
  </div>
</template>

<style scoped>
.scale {
  margin-top: 20px;
}

.scale__track {
  position: relative;
  display: flex;
  height: 12px;
  overflow: visible;
  border-radius: 4px;
}

.scale__seg--low {
  background: var(--risk-low-bg);
  border: 1px solid var(--risk-low-border);
}

.scale__seg--medium {
  background: var(--risk-medium-bg);
  border: 1px solid var(--risk-medium-border);
}

.scale__seg--high {
  background: var(--risk-high-bg);
  border: 1px solid var(--risk-high-border);
}

.scale__pointer {
  position: absolute;
  top: -16px;
  transform: translateX(-50%);
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1;
}

.scale__ticks {
  position: relative;
  height: 18px;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.scale__tick {
  position: absolute;
  transform: translateX(-50%);
}

.scale__tick:first-child {
  transform: none;
}

.scale__tick--end {
  transform: translateX(-100%);
}

.scale__legend {
  display: flex;
  justify-content: space-between;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
