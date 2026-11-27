<script setup lang="ts">
import { nextTick, ref } from 'vue'

import ServiceError from '../components/common/ServiceError.vue'
import PredictForm from '../components/predict/PredictForm.vue'
import PredictionResult from '../components/predict/PredictionResult.vue'
import type { FormValues } from '../domain/fields'
import { usePredictionStore } from '../stores/prediction'

const store = usePredictionStore()
const resultRef = ref<HTMLElement | null>(null)

const isMobile = () => window.matchMedia?.('(max-width: 767px)').matches ?? false

/** 成功後在手機上捲到結果並聚焦標題（桌機結果已在右側可見） */
async function revealResult(): Promise<void> {
  if (store.status !== 'success' || !isMobile()) return
  await nextTick()
  resultRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  resultRef.value?.querySelector<HTMLElement>('#result-title')?.focus({ preventScroll: true })
}

async function onSubmit(values: FormValues): Promise<void> {
  await store.submit(values)
  await revealResult()
}

async function onRetry(): Promise<void> {
  await store.retry()
  await revealResult()
}
</script>

<template>
  <section class="predict-view">
    <h1 class="predict-view__title">單筆顧客流失預測</h1>
    <div class="predict-view__layout">
      <PredictForm :loading="store.loading" @submit="onSubmit" />
      <aside
        ref="resultRef"
        class="predict-view__result"
        aria-label="預測結果"
        aria-live="polite"
        :aria-busy="store.loading"
      >
        <div
          v-if="store.result && store.status !== 'error'"
          class="result-wrap"
          :class="{ 'result-wrap--stale': store.loading }"
        >
          <PredictionResult :result="store.result" :defaulted-count="store.defaultedCount" />
        </div>
        <div v-else-if="store.loading" class="result-skeleton" data-testid="result-skeleton">
          <el-skeleton animated :rows="2" />
          <el-skeleton animated :rows="5" class="result-skeleton__factors" />
        </div>
        <ServiceError
          v-else-if="store.status === 'error' && store.serviceError"
          :error="store.serviceError"
          @retry="onRetry"
        />
        <div v-else class="result-empty">
          <h2 class="result-empty__title">尚未預測</h2>
          <p class="result-empty__text">
            填寫左側顧客資料後，按『預測』查看流失機率與主要影響因素。
          </p>
          <p class="result-empty__sub">或按上方『載入範例』快速體驗</p>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.predict-view__title {
  margin-bottom: 16px;
  font-size: 22px;
}

.predict-view__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.predict-view__result {
  min-width: 0;
}

.result-wrap {
  transition: opacity 0.2s;
}

.result-wrap--stale {
  opacity: 0.5;
}

.result-skeleton {
  padding: 20px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #fff;
}

.result-skeleton__factors {
  margin-top: 24px;
}

@media (prefers-reduced-motion: reduce) {
  .result-wrap {
    transition: none;
  }
}

.result-empty {
  padding: 32px 16px;
  border: 2px dashed var(--el-border-color);
  border-radius: 4px;
  background: #fff;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.result-empty__title {
  color: var(--el-text-color-primary);
  font-size: 18px;
}

.result-empty__text {
  margin: 8px 0 0;
}

.result-empty__sub {
  margin: 8px 0 0;
  font-size: 12px;
}

@media (max-width: 767px) {
  .result-empty {
    padding: 12px;
  }

  .result-empty__title {
    display: inline;
    font-size: 14px;
  }

  .result-empty__text,
  .result-empty__sub {
    display: none;
  }

  .result-empty__title::after {
    content: '：填寫資料後按『預測』查看結果';
    font-weight: 400;
  }
}

@media (min-width: 1024px) {
  .predict-view__layout {
    grid-template-columns: minmax(0, 58fr) minmax(0, 42fr);
  }

  .predict-view__result {
    position: sticky;
    top: 16px;
  }
}
</style>
