import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import AppFooter from '../../components/layout/AppFooter.vue'
import AppNav from '../../components/layout/AppNav.vue'
import { createAppRouter } from '../../router'

async function mountNav(path = '/') {
  const router = createAppRouter(createMemoryHistory())
  router.push(path)
  await router.isReady()
  const wrapper = mount(AppNav, { global: { plugins: [router] } })
  return { wrapper, router }
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('AppNav', () => {
  it('列出三個頁面與 API 文件連結', async () => {
    const { wrapper } = await mountNav()
    const links = wrapper.findAll('nav a')
    expect(links.map((l) => l.text().replace('（另開新分頁）', ''))).toEqual([
      '單筆預測',
      '模型成效',
      '批次預測',
      'API 文件',
    ])
    expect(links.slice(0, 3).map((l) => l.attributes('href'))).toEqual([
      '/',
      '/performance',
      '/batch',
    ])
  })

  it('目前頁面的導覽項有 aria-current="page"，其他沒有', async () => {
    const { wrapper } = await mountNav('/performance')
    const current = wrapper.findAll('nav a[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]!.text()).toBe('模型成效')
  })

  it('切換頁面後 aria-current 跟著移動', async () => {
    const { wrapper, router } = await mountNav('/')
    await router.push('/batch')
    expect(wrapper.find('nav a[aria-current="page"]').text()).toBe('批次預測')
  })

  it('API 文件連結預設 /docs，新分頁開啟並帶 noopener', async () => {
    const { wrapper } = await mountNav()
    const docs = wrapper.findAll('nav a').at(-1)!
    expect(docs.attributes('href')).toBe('/docs')
    expect(docs.attributes('target')).toBe('_blank')
    expect(docs.attributes('rel')).toContain('noopener')
  })

  it('API 文件連結使用 VITE_API_DOCS_URL', async () => {
    vi.stubEnv('VITE_API_DOCS_URL', 'https://example.test/docs')
    const { wrapper } = await mountNav()
    expect(wrapper.findAll('nav a').at(-1)!.attributes('href')).toBe('https://example.test/docs')
  })

  it('漢堡按鈕切換選單並同步 aria-expanded', async () => {
    const { wrapper } = await mountNav()
    const toggle = wrapper.find('button.app-nav__toggle')
    const menu = wrapper.find('#app-nav-menu')
    expect(toggle.attributes('aria-controls')).toBe('app-nav-menu')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(menu.classes()).not.toContain('is-open')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(menu.classes()).toContain('is-open')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
  })

  it('按 Esc 收合後焦點回到漢堡按鈕', async () => {
    const router = createAppRouter(createMemoryHistory())
    router.push('/')
    await router.isReady()
    const wrapper = mount(AppNav, { attachTo: document.body, global: { plugins: [router] } })
    const toggle = wrapper.find<HTMLButtonElement>('button.app-nav__toggle')
    await toggle.trigger('click')
    wrapper.find<HTMLAnchorElement>('nav a').element.focus()
    await wrapper.find('header').trigger('keydown', { key: 'Escape' })
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(toggle.element)
    wrapper.unmount()
  })

  it('按 Esc 與換頁都會收合選單', async () => {
    const { wrapper, router } = await mountNav()
    const toggle = wrapper.find('button.app-nav__toggle')
    await toggle.trigger('click')
    await wrapper.find('header').trigger('keydown', { key: 'Escape' })
    expect(toggle.attributes('aria-expanded')).toBe('false')

    await toggle.trigger('click')
    await router.push('/batch')
    expect(toggle.attributes('aria-expanded')).toBe('false')
  })
})

describe('AppFooter', () => {
  it('顯示免責文字（AC-1.13）', () => {
    const wrapper = mount(AppFooter)
    expect(wrapper.text()).toBe('模型以公開範例資料訓練，僅供展示，不可用於真實決策')
  })
})
