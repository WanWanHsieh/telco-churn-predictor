import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '../App.vue'

describe('App', () => {
  it('renders the title', () => {
    const wrapper = mount(App)
    expect(wrapper.find('h1').text()).toBe('電信客戶流失預測')
  })
})
