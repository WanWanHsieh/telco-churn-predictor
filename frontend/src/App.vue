<script setup lang="ts">
import AppFooter from './components/layout/AppFooter.vue'
import AppNav from './components/layout/AppNav.vue'
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要內容</a>
    <AppNav />
    <main id="main-content" class="app-main" tabindex="-1">
      <RouterView />
    </main>
    <AppFooter />
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  flex-direction: column;
}

.app-main {
  width: 100%;
  max-width: 1280px;
  flex: 1;
  margin: 0 auto;
  padding: 16px;
}

.app-main:focus {
  outline: none;
}

.skip-link {
  position: absolute;
  top: -48px;
  left: 8px;
  z-index: 3000;
  padding: 8px 12px;
  background: #fff;
  color: var(--el-color-primary);
  border-radius: 4px;
}

.skip-link:focus {
  top: 8px;
}
</style>
