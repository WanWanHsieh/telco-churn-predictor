import { defineConfig, mergeConfig } from 'vitest/config'

import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.spec.ts'],
      // unplugin 會在 SFC 注入 element-plus 的 CSS import，需由 Vite 轉換才能在 Node 中載入
      server: { deps: { inline: [/element-plus/] } },
    },
  }),
)
