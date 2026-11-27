<script setup lang="ts">
// 預測結果卡片（ui.md 3.4）：機率與等級、機率尺、前 5 因素、估算註記、免責
import type { PredictionResponse } from '../../api/predictions'
import { formatMoney, formatProbability } from '../../domain/format'
import { thresholdText } from '../../domain/risk'
import RiskBadge from '../common/RiskBadge.vue'
import FactorList from './FactorList.vue'
import ProbabilityScale from './ProbabilityScale.vue'

// defaultedCount：送出時仍為預設值的進階欄位數（0 則不顯示註記）
withDefaults(defineProps<{ result: PredictionResponse; defaultedCount?: number }>(), {
  defaultedCount: 0,
})
</script>

<template>
  <article class="result">
    <header class="result__header">
      <h2 id="result-title" class="result__title" tabindex="-1">預測結果</h2>
      <span class="result__model">模型：{{ result.model.display_name }}</span>
    </header>

    <div class="result__main">
      <p class="result__probability">
        流失機率 <strong>{{ formatProbability(result.probability) }}</strong>
      </p>
      <div class="result__level">
        <RiskBadge :level="result.risk_level" />
        <span class="result__threshold">
          {{ thresholdText(result.risk_level, result.risk_thresholds) }}
        </span>
      </div>
      <ProbabilityScale :probability="result.probability" :thresholds="result.risk_thresholds" />
    </div>

    <el-alert
      v-if="result.total_charges.is_estimated"
      class="result__estimate"
      type="info"
      :closable="false"
      show-icon
      :title="`累計費用未填寫，已以在網月數 × 月費估算為 ${formatMoney(result.total_charges.value)}。`"
    />

    <el-alert
      v-if="defaultedCount > 0"
      class="result__estimate result__defaulted"
      type="info"
      :closable="false"
      show-icon
      :title="`有 ${defaultedCount} 個進階欄位與預設值（資料集中最常見的值）相同；填得越完整，預測越貼近實際。`"
    />

    <FactorList :factors="result.top_factors" />

    <p class="result__disclaimer">模型以公開範例資料訓練，僅供展示，不可用於真實決策</p>
  </article>
</template>

<style scoped>
.result {
  padding: 20px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #fff;
  box-shadow: var(--el-box-shadow-light);
}

.result__header {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: baseline;
  justify-content: space-between;
}

.result__title {
  margin: 0;
  font-size: 18px;
}

.result__title:focus {
  outline: none;
}

.result__title:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}

.result__model {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.result__main {
  margin: 16px 0 20px;
}

.result__probability {
  margin: 0;
  font-size: 16px;
}

.result__probability strong {
  font-size: 40px;
  font-variant-numeric: tabular-nums;
}

.result__level {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.result__threshold {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.result__estimate {
  margin-bottom: 16px;
}

.result__disclaimer {
  margin: 16px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 767px) {
  .result__probability strong {
    font-size: 32px;
  }
}
</style>
