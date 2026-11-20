import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MetricsTable from '../../components/performance/MetricsTable.vue'
import { makeMetrics } from '../fixtures/metrics'

const m = makeMetrics()

function cell(wrapper: ReturnType<typeof mount>, model: string, metric: string) {
  return wrapper.find(
    `td[data-model="${model}"][data-metric="${metric}"], tr[data-model="${model}"] td[data-metric="${metric}"]`,
  )
}

describe('MetricsTable', () => {
  it('兩模型五指標皆顯示 3 位小數（AC-3.1）', () => {
    const wrapper = mount(MetricsTable, { props: { models: m.models, dataset: m.dataset } })
    for (const metric of ['roc_auc', 'precision', 'recall', 'f1', 'accuracy']) {
      expect(cell(wrapper, 'keras_mlp', metric).exists()).toBe(true)
      expect(cell(wrapper, 'logistic_regression', metric).exists()).toBe(true)
    }
    expect(cell(wrapper, 'keras_mlp', 'roc_auc').text()).toBe('0.790')
    expect(cell(wrapper, 'logistic_regression', 'roc_auc').text()).toBe('0.810')
    expect(wrapper.text()).toContain('邏輯迴歸（基準）')
  })

  it('較佳者粗體，相同時皆不粗體', () => {
    const wrapper = mount(MetricsTable, { props: { models: m.models, dataset: m.dataset } })
    expect(cell(wrapper, 'logistic_regression', 'roc_auc').classes()).toContain('is-best')
    expect(cell(wrapper, 'keras_mlp', 'roc_auc').classes()).not.toContain('is-best')
    expect(cell(wrapper, 'keras_mlp', 'precision').classes()).toContain('is-best')
    expect(cell(wrapper, 'keras_mlp', 'recall').classes()).not.toContain('is-best')
    expect(cell(wrapper, 'logistic_regression', 'recall').classes()).not.toContain('is-best')
  })

  it('Accuracy 說明的比例由 API 計算（AC-3.4）', () => {
    const wrapper = mount(MetricsTable, { props: { models: m.models, dataset: m.dataset } })
    expect(wrapper.find('[data-testid="accuracy-note"]').text()).toBe(
      '資料約 30% 為流失，若全部猜「不流失」就有約 70% 的 Accuracy，所以本專案以 ROC-AUC 與 Recall 為主要指標。',
    )
  })

  it('手機版轉置為指標 × 模型', () => {
    const wrapper = mount(MetricsTable, {
      props: { models: m.models, dataset: m.dataset, compact: true },
    })
    expect(wrapper.find('[data-layout="metrics-by-models"]').exists()).toBe(true)
    expect(wrapper.findAll('tbody tr')).toHaveLength(5)
    expect(cell(wrapper, 'keras_mlp', 'f1').text()).toBe('0.600')
  })
})

describe('MetricsTable 顯示名稱', () => {
  it('API 名稱已含「基準」時不重複加註', () => {
    const models = makeMetrics().models.map((x) =>
      x.key === 'logistic_regression' ? { ...x, display_name: '邏輯迴歸（基準）' } : x,
    )
    const wrapper = mount(MetricsTable, { props: { models, dataset: m.dataset } })
    expect(wrapper.text()).toContain('邏輯迴歸（基準）')
    expect(wrapper.text()).not.toContain('（基準）（基準）')
  })
})
