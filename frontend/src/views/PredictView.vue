<script setup lang="ts">
import PredictForm from '../components/predict/PredictForm.vue'

// T8：表單送出事件（submit）尚未接 API，T9 在此接線並顯示結果。
</script>

<template>
  <section class="predict-view">
    <h1 class="predict-view__title">單筆顧客流失預測</h1>
    <div class="predict-view__layout">
      <PredictForm />
      <aside class="predict-view__result" aria-label="預測結果" aria-live="polite">
        <div class="result-empty">
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
