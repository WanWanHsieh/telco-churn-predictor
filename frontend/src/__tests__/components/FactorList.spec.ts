import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FactorList from '../../components/predict/FactorList.vue'
import { FEATURE_NAMES } from '../../domain/fields'
import { makePrediction } from '../fixtures/prediction'

const factors = makePrediction().top_factors

describe('FactorList', () => {
  it('依序顯示 5 個因素的中文名稱、方向與數值（AC-2.1）', () => {
    const wrapper = mount(FactorList, { props: { factors } })
    const rows = wrapper.findAll('.factor')
    expect(rows).toHaveLength(5)
    expect(rows.map((r) => r.find('.factor__label').text())).toEqual(factors.map((f) => f.label))
    expect(rows[0]?.find('.factor__direction').text()).toContain('↑')
    expect(rows[0]?.find('.factor__direction').text()).toContain('推高風險')
    expect(rows[2]?.find('.factor__direction').text()).toContain('↓')
    expect(rows[2]?.find('.factor__direction').text()).toContain('拉低風險')
    expect(rows[0]?.find('.factor__value').text()).toBe('+18.3')
    expect(rows[2]?.find('.factor__value').text()).toBe('−9.5')
  })

  it('不顯示內部欄名（AC-2.2）', () => {
    const text = mount(FactorList, { props: { factors } }).text()
    for (const name of FEATURE_NAMES) {
      expect(text).not.toMatch(new RegExp(`\\b${name}\\b`))
    }
  })

  it('長條有 aria-label，且推高向右、拉低向左', () => {
    const wrapper = mount(FactorList, { props: { factors } })
    const bars = wrapper.findAll('.factor__bar')
    expect(bars[0]?.attributes('role')).toBe('img')
    expect(bars[0]?.attributes('aria-label')).toBe(
      '合約類型：月繳，推高風險，影響程度 +18.3 個百分點',
    )
    const up = wrapper.findAll('.factor__fill')[0]?.attributes('style') ?? ''
    const down = wrapper.findAll('.factor__fill')[2]?.attributes('style') ?? ''
    expect(up).toContain('left: 50%')
    expect(up).toContain('width: 50%') // 最大影響值佔滿半邊
    expect(down).toContain('right: 50%')
  })

  it('有非因果說明（AC-2.5）', () => {
    expect(mount(FactorList, { props: { factors } }).text()).toContain('不代表真正的因果關係')
  })
})
