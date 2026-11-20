<script setup lang="ts">
// 模型成效頁（ui.md 第 4 節）：載入骨架、錯誤、404 空狀態
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import ServiceError from '../components/common/ServiceError.vue'
import ConfusionMatrix from '../components/performance/ConfusionMatrix.vue'
import DatasetInfo from '../components/performance/DatasetInfo.vue'
import ImbalanceNote from '../components/performance/ImbalanceNote.vue'
import MetricsTable from '../components/performance/MetricsTable.vue'
import RocChart from '../components/performance/RocChart.vue'
import { usePerformanceStore } from '../stores/performance'

const store = usePerformanceStore()

// 手機版：描述區 1 欄、指標表轉置、混淆矩陣圖例移到格外
const compact = ref(false)
let media: MediaQueryList | undefined
const syncCompact = () => (compact.value = media?.matches ?? false)

onMounted(() => {
  media = window.matchMedia?.('(max-width: 767px)')
  syncCompact()
  media?.addEventListener?.('change', syncCompact)
  void store.ensureLoaded()
})
onBeforeUnmount(() => media?.removeEventListener?.('change', syncCompact))

const primary = computed(
  () =>
    store.data?.models.find((m) => m.key === store.data?.primary_model) ?? store.data?.models[0],
)
</script>

<template>
  <section class="perf" :aria-busy="store.status === 'loading'">
    <h1 class="perf__title">模型成效</h1>
    <p class="perf__lead">模型在訓練時從未看過的測試資料上的表現，並與簡單的基準模型比較。</p>

    <div v-if="store.status === 'loading' || store.status === 'idle'" data-testid="perf-skeleton">
      <el-skeleton animated :rows="3" />
      <div class="perf__charts">
        <el-skeleton-item variant="rect" class="perf__chart-skeleton" />
        <el-skeleton-item variant="rect" class="perf__chart-skeleton" />
      </div>
    </div>

    <el-empty
      v-else-if="store.status === 'empty'"
      description="尚無成效資料：請先執行訓練指令產生模型成效後再查看（指令請見 README）。"
    />

    <ServiceError
      v-else-if="store.status === 'error' && store.error"
      :error="store.error"
      title="無法載入模型成效"
      message="成效資料暫時取不到，請稍後再試。"
      @retry="store.load()"
    />

    <template v-else-if="store.data">
      <DatasetInfo :metrics="store.data" :compact="compact" />
      <el-card shadow="never" class="perf__block">
        <MetricsTable
          :models="store.data.models"
          :dataset="store.data.dataset"
          :compact="compact"
        />
      </el-card>
      <div class="perf__charts">
        <el-card shadow="never">
          <RocChart :models="store.data.models" />
        </el-card>
        <el-card v-if="primary" shadow="never">
          <ConfusionMatrix
            :matrix="primary.confusion_matrix"
            :model-name="primary.display_name"
            :compact="compact"
          />
        </el-card>
      </div>
      <ImbalanceNote :metrics="store.data" />
    </template>
  </section>
</template>

<style scoped>
.perf {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.perf__title {
  margin: 0;
  font-size: 22px;
}

.perf__lead {
  margin: -8px 0 0;
  color: var(--el-text-color-secondary);
}

.perf__charts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.perf__chart-skeleton {
  width: 100%;
  height: 360px;
}

@media (min-width: 1024px) {
  .perf__charts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
