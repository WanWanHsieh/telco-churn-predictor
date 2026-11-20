<script setup lang="ts">
// 白話說明（AC-3.5）：依 imbalance_strategy 選文案，數字一律取自 API，合計 3 句內
import { computed } from 'vue'

import type { MetricsResponse } from '../../api/metrics'
import { formatPercent } from '../../domain/format'

const props = defineProps<{ metrics: MetricsResponse }>()

/** 機器學習慣用的預設判定門檻（概念說明用，不是指標數字） */
const DEFAULT_THRESHOLD = 0.5

const sentences = computed(() => {
  const m = props.metrics
  const rate = formatPercent(m.dataset.test_churn_rate)
  const recall = formatPercent(m.target_recall)
  const threshold = m.decision_threshold.toFixed(2)
  const first =
    m.imbalance_strategy === 'class_weight'
      ? `流失顧客只佔約 ${rate}，訓練時提高流失樣本的權重，避免模型只學會猜「不流失」。`
      : `流失顧客只佔約 ${rate}，模型照原始比例訓練，再調整判定門檻來抓出更多流失顧客。`
  return [
    first,
    `決策門檻 ${threshold} 是在驗證集上找出、能抓到至少 ${recall} 流失顧客的門檻（固定 ${DEFAULT_THRESHOLD} 會漏掉較多）。`,
    '測試集只用來評估，不參與門檻選擇，所以上面的數字代表模型面對新資料的表現。',
  ]
})
</script>

<template>
  <el-card class="imbalance-note" shadow="never">
    <h2 class="imbalance-note__title">如何處理類別不平衡、為什麼選這個門檻</h2>
    <p v-for="s in sentences" :key="s" class="imbalance-note__text">{{ s }}</p>
  </el-card>
</template>

<style scoped>
.imbalance-note {
  background: var(--el-fill-color-light);
}

.imbalance-note__title {
  margin: 0 0 8px;
  font-size: 16px;
}

.imbalance-note__text {
  margin: 4px 0 0;
}
</style>
