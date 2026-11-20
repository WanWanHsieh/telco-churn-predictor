import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import App from '../App.vue'
import { createAppRouter } from '../router'

describe('App', () => {
  it('renders the shell and the predict page title', async () => {
    const router = createAppRouter(createMemoryHistory())
    router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
    expect(wrapper.find('h1').text()).toBe('單筆顧客流失預測')
    expect(wrapper.find('nav').exists()).toBe(true)
    expect(wrapper.find('footer').text()).toContain('僅供展示')
  })
})
