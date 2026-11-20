import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

const backend = 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入（ui.md 11）
    AutoImport({ resolvers: [ElementPlusResolver()], dts: 'auto-imports.d.ts' }),
    Components({ resolvers: [ElementPlusResolver()], dts: 'components.d.ts' }),
  ],
  server: {
    port: 5173,
    // 本機開發：把 API 與 Swagger 代理到 backend（design.md 第 7 節）
    proxy: {
      '/api': backend,
      '/docs': backend,
      '/openapi.json': backend,
    },
  },
})
