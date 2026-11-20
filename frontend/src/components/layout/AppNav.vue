<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { NAV_ITEMS } from '../../router'

// 「API 文件」連結：建置期變數，預設 /docs（design.md 第 7 節）
const docsUrl = (import.meta.env.VITE_API_DOCS_URL as string | undefined) || '/docs'

const route = useRoute()
const menuOpen = ref(false)
const toggleRef = ref<HTMLButtonElement | null>(null)

// Esc 收合選單後，焦點回到漢堡按鈕
async function onEsc(): Promise<void> {
  if (!menuOpen.value) return
  menuOpen.value = false
  await nextTick()
  toggleRef.value?.focus()
}

// 換頁後收合手機選單
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
  },
)
</script>

<template>
  <header class="app-nav" @keydown.esc="onEsc">
    <div class="app-nav__bar">
      <RouterLink class="app-nav__brand" to="/">
        <strong>顧客流失預測</strong>
        <span class="app-nav__sub">Telco Churn Predictor</span>
      </RouterLink>

      <button
        ref="toggleRef"
        class="app-nav__toggle"
        type="button"
        aria-controls="app-nav-menu"
        :aria-expanded="menuOpen"
        :aria-label="menuOpen ? '收合主選單' : '展開主選單'"
        @click="menuOpen = !menuOpen"
      >
        <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
          <path
            d="M4 6h16M4 12h16M4 18h16"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            fill="none"
          />
        </svg>
      </button>

      <nav
        id="app-nav-menu"
        class="app-nav__menu"
        :class="{ 'is-open': menuOpen }"
        aria-label="主要導覽"
      >
        <ul>
          <li v-for="item in NAV_ITEMS" :key="item.to">
            <RouterLink class="app-nav__link" :to="item.to">{{ item.label }}</RouterLink>
          </li>
          <li>
            <a class="app-nav__link" :href="docsUrl" target="_blank" rel="noopener noreferrer">
              API 文件<span class="sr-only">（另開新分頁）</span>
            </a>
          </li>
        </ul>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.app-nav {
  position: relative;
  z-index: 100;
  border-bottom: 1px solid var(--el-border-color);
  background: #fff;
}

.app-nav__bar {
  display: flex;
  max-width: 1280px;
  align-items: center;
  justify-content: space-between;
  margin: 0 auto;
  padding: 0 16px;
  flex-wrap: wrap;
}

.app-nav__brand {
  display: flex;
  min-height: 56px;
  align-items: baseline;
  gap: 8px;
  color: var(--el-text-color-primary);
  text-decoration: none;
}

.app-nav__brand strong {
  font-size: 18px;
}

.app-nav__sub {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.app-nav__toggle {
  display: none;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #fff;
  color: var(--el-text-color-primary);
  cursor: pointer;
}

.app-nav__menu ul {
  display: flex;
  margin: 0;
  padding: 0;
  gap: 8px;
  list-style: none;
}

.app-nav__link {
  display: flex;
  min-height: 56px;
  align-items: center;
  padding: 0 12px;
  border-bottom: 3px solid transparent;
  color: var(--el-text-color-primary);
  text-decoration: none;
}

.app-nav__link:hover {
  color: var(--el-color-primary);
}

/* 目前頁面：底線＋粗體，不只靠顏色（RouterLink 自動加 aria-current="page"） */
.app-nav__link[aria-current='page'] {
  border-bottom-color: var(--el-color-primary);
  color: var(--el-color-primary);
  font-weight: 700;
}

@media (max-width: 767px) {
  .app-nav__brand {
    min-height: 56px;
  }

  .app-nav__sub {
    display: none;
  }

  .app-nav__toggle {
    display: inline-flex;
  }

  .app-nav__menu {
    display: none;
    width: 100%;
    padding-bottom: 8px;
  }

  .app-nav__menu.is-open {
    display: block;
  }

  .app-nav__menu ul {
    flex-direction: column;
    gap: 0;
  }

  .app-nav__link {
    min-height: 44px;
    border-bottom: 0;
    border-left: 3px solid transparent;
  }

  .app-nav__link[aria-current='page'] {
    border-left-color: var(--el-color-primary);
  }
}
</style>
