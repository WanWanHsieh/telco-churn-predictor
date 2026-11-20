import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PredictionResult from '../../components/predict/PredictionResult.vue'
import { makePrediction } from '../fixtures/prediction'

describe('PredictionResult', () => {
  it('顯示機率 1 位小數、等級文字＋圖示與切點說明（AC-1.2）', () => {
    const wrapper = mount(PredictionResult, { props: { result: makePrediction() } })
    expect(wrapper.find('.result__probability').text()).toContain('72.4%')
    const badge = wrapper.find('.risk-badge')
    expect(badge.text()).toContain('▲')
    expect(badge.text()).toContain('高風險')
    expect(badge.classes()).toContain('risk-badge--high')
    expect(wrapper.find('.result__threshold').text()).toBe('機率 >= 60%')
    expect(wrapper.text()).toContain('模型：Keras 神經網路')
  })

  it('切點說明取自回應的 risk_thresholds', () => {
    const result = makePrediction({
      probability: 0.4,
      risk_level: 'medium',
      risk_thresholds: { medium: 0.25, high: 0.55 },
    })
    const wrapper = mount(PredictionResult, { props: { result } })
    expect(wrapper.find('.result__threshold').text()).toBe('機率 25% 至未滿 55%')
    expect(wrapper.find('.risk-badge').text()).toContain('◆')
  })

  it('估算時顯示累計費用註記（AC-1.14）', () => {
    const wrapper = mount(PredictionResult, { props: { result: makePrediction() } })
    expect(wrapper.text()).toContain('累計費用未填寫，已以在網月數 × 月費估算為 $1,234.50。')
  })

  it('非估算時不顯示註記（AC-1.15）', () => {
    const result = makePrediction({ total_charges: { value: 500, is_estimated: false } })
    const wrapper = mount(PredictionResult, { props: { result } })
    expect(wrapper.text()).not.toContain('累計費用未填寫')
  })

  it('有固定免責提示（AC-1.13）', () => {
    const wrapper = mount(PredictionResult, { props: { result: makePrediction() } })
    expect(wrapper.find('.result__disclaimer').text()).toBe(
      '模型以公開範例資料訓練，僅供展示，不可用於真實決策',
    )
  })
})
