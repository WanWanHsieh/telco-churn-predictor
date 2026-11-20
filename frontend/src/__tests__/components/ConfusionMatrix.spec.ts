import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConfusionMatrix from '../../components/performance/ConfusionMatrix.vue'

const matrix = { tn: 700, fp: 300, fn: 90, tp: 310 }

describe('ConfusionMatrix', () => {
  it('4 格含數量、佔比與意義文字（AC-3.2）', () => {
    const wrapper = mount(ConfusionMatrix, { props: { matrix, modelName: 'Keras 神經網路' } })
    const tp = wrapper.find('[data-cell="tp"]')
    expect(tp.find('.cm__count').text()).toBe('310')
    expect(tp.find('.cm__share').text()).toBe('22.1%')
    expect(tp.text()).toContain('實際流失、預測流失')
    expect(wrapper.find('[data-cell="fp"]').text()).toContain('實際未流失、預測流失')
    expect(wrapper.find('[data-cell="fn"]').text()).toContain('實際流失、預測未流失')
    expect(wrapper.find('[data-cell="tn"]').text()).toContain('700')
    expect(wrapper.text()).toContain('混淆矩陣（Keras 神經網路，測試集）')
  })

  it('手機版格內只留數量，意義改為格外圖例', () => {
    const wrapper = mount(ConfusionMatrix, {
      props: { matrix, modelName: 'Keras 神經網路', compact: true },
    })
    expect(wrapper.find('[data-cell="tp"] .cm__meaning').exists()).toBe(false)
    const legend = wrapper.findAll('.cm__legend li').map((li) => li.text())
    expect(legend).toContain('實際流失、預測流失：310')
    expect(legend).toHaveLength(4)
  })
})
