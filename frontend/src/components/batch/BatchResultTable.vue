<script setup lang="ts">
// 結果表格（AC-6.2、6.3）：序號、customerID（有才顯示）、機率、等級；可排序、篩選、分頁
import { computed } from 'vue'

import type { RiskLevel } from '../../api/predictions'
import { formatProbability } from '../../domain/format'
import { RISK_META } from '../../domain/risk'
import { PAGE_SIZE, useBatchStore, type RiskFilter, type SortKey } from '../../stores/batch'
import RiskBadge from '../common/RiskBadge.vue'

const props = defineProps<{ compact?: boolean }>()
const store = useBatchStore()

const FILTERS: { value: RiskFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
]

const hasCustomerId = computed(() => store.response?.has_customer_id ?? false)
const filterLabel = computed(() =>
  store.filter === 'all' ? '' : RISK_META[store.filter as RiskLevel].label,
)

function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
  return store.sortKey === key ? store.sortOrder : 'none'
}

function toggleSort(key: SortKey): void {
  if (store.sortKey !== key) store.setSort(key, 'descending')
  else store.setSort(key, store.sortOrder === 'descending' ? 'ascending' : 'descending')
}

function arrow(key: SortKey): string {
  if (store.sortKey !== key) return '↕'
  return store.sortOrder === 'descending' ? '↓' : '↑'
}

const pageStart = computed(() => (store.page - 1) * PAGE_SIZE)
const paginationLayout = computed(() =>
  props.compact ? 'prev, pager, next' : 'total, prev, pager, next',
)
</script>

<template>
  <div class="batch-table">
    <div class="batch-table__toolbar">
      <el-radio-group
        :model-value="store.filter"
        aria-label="依風險等級篩選"
        @update:model-value="(v: unknown) => store.setFilter(v as RiskFilter)"
      >
        <el-radio-button v-for="f in FILTERS" :key="f.value" :value="f.value">
          {{ f.label }}（{{ store.counts[f.value] }}）
        </el-radio-button>
      </el-radio-group>
      <slot name="actions" />
    </div>

    <el-empty
      v-if="store.sortedRows.length === 0"
      :description="`沒有符合「${filterLabel}」的顧客`"
      data-testid="filter-empty"
    >
      <el-button @click="store.setFilter('all')">清除篩選</el-button>
    </el-empty>

    <template v-else>
      <table class="bt">
        <thead>
          <tr>
            <th scope="col" class="bt__index">序號</th>
            <th v-if="hasCustomerId" scope="col">customerID</th>
            <th scope="col" class="bt__num" :aria-sort="ariaSort('probability')">
              <button type="button" class="bt__sort" @click="toggleSort('probability')">
                流失機率 <span aria-hidden="true">{{ arrow('probability') }}</span>
              </button>
            </th>
            <th scope="col" :aria-sort="ariaSort('risk_level')">
              <button type="button" class="bt__sort" @click="toggleSort('risk_level')">
                風險等級 <span aria-hidden="true">{{ arrow('risk_level') }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in store.pagedRows" :key="r.row" :data-row="r.row">
            <td class="bt__index">{{ pageStart + i + 1 }}</td>
            <td v-if="hasCustomerId" class="bt__id">{{ r.customer_id ?? '—' }}</td>
            <td class="bt__num">{{ formatProbability(r.probability) }}</td>
            <td><RiskBadge :level="r.risk_level" /></td>
          </tr>
        </tbody>
      </table>
      <el-pagination
        v-if="store.sortedRows.length > PAGE_SIZE"
        class="batch-table__pager"
        :small="compact"
        :layout="paginationLayout"
        :page-size="PAGE_SIZE"
        :total="store.sortedRows.length"
        :current-page="store.page"
        @update:current-page="(p: number) => (store.page = p)"
      />
    </template>
  </div>
</template>

<style scoped>
.batch-table__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.bt {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-variant-numeric: tabular-nums;
}

.bt th,
.bt td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  text-align: left;
}

.bt thead th {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.bt__num {
  text-align: right !important;
}

.bt__index {
  width: 56px;
  color: var(--el-text-color-secondary);
}

.bt__id {
  overflow-wrap: anywhere;
}

.bt__sort {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.batch-table__pager {
  justify-content: center;
  margin-top: 12px;
}
</style>
