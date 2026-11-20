import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'

export default defineConfigWithVueTs(
  {
    name: 'app/ignores',
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'src/api/schema.gen.ts',
      'auto-imports.d.ts',
      'components.d.ts',
    ],
  },
  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  skipFormatting,
)
