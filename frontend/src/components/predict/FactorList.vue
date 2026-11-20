<script setup lang="ts">
// 前 5 大影響因素（ui.md 3.4 第 3 點）：中文名稱、方向文字＋圖示、以中線為 0 的發散長條
import { computed } from 'vue'

import type { Factor } from '../../api/predictions'
import { formatImpact } from '../../domain/format'

const props = defineProps<{ factors: Factor[] }>()

const DIRECTION = {
  increase: { icon: '↑', text: '推高風險' },
  decrease: { icon: '↓', text: '拉低風險' },
} as const

/** 長條長度相對於最大影響值（半邊寬度的百分比） */
const maxAbs = computed(() => Math.max(...props.factors.map((f) => Math.abs(f.impact)), 1e-9))

function barStyle(f: Factor) {
  const width = `${(Math.abs(f.impact) / maxAbs.value) * 50}%`
  return f.direction === 'increase' ? { left: '50%', width } : { right: '50%', width }
}

function ariaLabel(f: Factor): string {
  return `${f.label}，${DIRECTION[f.direction].text}，影響程度 ${formatImpact(f.impact)} 個百分點`
}
</script>

<template>
  <section class="factors" aria-labelledby="factors-title">
    <h3 id="factors-title" class="factors__title">影響此預測的前 5 大因素</h3>
    <p class="factors__unit">影響程度：對流失機率的影響（百分點）</p>
    <ol class="factors__list">
      <li v-for="(f, i) in factors" :key="f.feature" class="factor" :data-direction="f.direction">
        <span class="factor__rank" aria-hidden="true">{{ i + 1 }}</span>
        <span class="factor__label">{{ f.label }}</span>
        <span class="factor__direction" :class="`factor__direction--${f.direction}`">
          <span aria-hidden="true">{{ DIRECTION[f.direction].icon }}</span>
          {{ DIRECTION[f.direction].text }}
        </span>
        <span class="factor__bar" role="img" :aria-label="ariaLabel(f)">
          <span class="factor__axis" aria-hidden="true" />
          <span
            class="factor__fill"
            :class="`factor__fill--${f.direction}`"
            :style="barStyle(f)"
            aria-hidden="true"
          />
        </span>
        <span class="factor__value">{{ formatImpact(f.impact) }}</span>
      </li>
    </ol>
    <p class="factors__note">這些因素是模型做出判斷的依據，不代表真正的因果關係。</p>
  </section>
</template>

<style scoped>
.factors__title {
  margin: 0;
  font-size: 16px;
}

.factors__unit {
  margin: 4px 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.factors__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.factor {
  display: grid;
  /* 因素名稱＋方向在上、長條＋數值在下：結果欄較窄時名稱不被擠壓 */
  grid-template-columns: 20px minmax(0, 1fr) max-content;
  gap: 4px 8px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.factor__rank {
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}

.factor__label {
  overflow-wrap: anywhere;
}

.factor__direction {
  font-size: 13px;
  white-space: nowrap;
}

.factor__direction--increase {
  color: var(--risk-high-text);
}

.factor__direction--decrease {
  color: var(--risk-low-text);
}

.factor__bar {
  position: relative;
  grid-column: 2 / 3;
  height: 10px;
}

.factor__axis {
  position: absolute;
  top: -3px;
  bottom: -3px;
  left: 50%;
  width: 1px;
  background: var(--el-border-color);
}

.factor__fill {
  position: absolute;
  top: 0;
  bottom: 0;
  border-radius: 2px;
}

.factor__fill--increase {
  background: var(--bar-up);
}

.factor__fill--decrease {
  background: var(--bar-down);
}

.factor__value {
  grid-column: 3 / 4;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.factors__note {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
